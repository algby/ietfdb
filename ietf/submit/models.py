import re
import datetime

from django.db import models

from ietf.person.models import Person
from ietf.group.models import Group
from ietf.name.models import DraftSubmissionStateName
from ietf.utils.accesstoken import generate_random_key, generate_access_token


def parse_email_line(line):
    """Split line on the form 'Some Name <email@example.com>'"""
    m = re.match("([^<]+) <([^>]+)>$", line)
    if m:
        return dict(name=m.group(1), email=m.group(2))
    else:
        return dict(name=line, email="")

class Submission(models.Model):
    state = models.ForeignKey(DraftSubmissionStateName)
    remote_ip = models.CharField(max_length=100, blank=True)

    access_key = models.CharField(max_length=255, default=generate_random_key)
    auth_key = models.CharField(max_length=255, blank=True)

    # draft metadata
    name = models.CharField(max_length=255, db_index=True)
    group = models.ForeignKey(Group, null=True, blank=True)
    title = models.CharField(max_length=255, blank=True)
    abstract = models.TextField(blank=True)
    rev = models.CharField(max_length=3, blank=True)
    pages = models.IntegerField(null=True, blank=True)
    authors = models.TextField(blank=True, help_text="List of author names and emails, one author per line, e.g. \"John Doe &lt;john@example.org&gt;\"")
    note = models.TextField(blank=True)
    replaces = models.CharField(max_length=255, blank=True)

    first_two_pages = models.TextField(blank=True)
    file_types = models.CharField(max_length=50, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    document_date = models.DateField(null=True, blank=True)
    submission_date = models.DateField(default=datetime.date.today)

    submitter = models.CharField(max_length=255, blank=True, help_text="Name and email of submitter, e.g. \"John Doe &lt;john@example.org&gt;\"")

    idnits_message = models.TextField(blank=True)

    def __unicode__(self):
        return u"%s-%s" % (self.name, self.rev)

    def authors_parsed(self):
        res = []
        for line in self.authors.replace("\r", "").split("\n"):
            line = line.strip()
            if line:
                res.append(parse_email_line(line))
        return res

    def submitter_parsed(self):
        return parse_email_line(self.submitter)

    def access_token(self):
        return generate_access_token(self.access_key)


class SubmissionEvent(models.Model):
    submission = models.ForeignKey(Submission)
    time = models.DateTimeField(default=datetime.datetime.now)
    by = models.ForeignKey(Person, null=True, blank=True)
    desc = models.TextField()

    def __unicode__(self):
        return u"%s %s by %s at %s" % (self.submission.name, self.desc, self.by.plain_name() if self.by else "(unknown)", self.time)

    class Meta:
        ordering = ("-time", "-id")


class Preapproval(models.Model):
    """Pre-approved draft submission name."""
    name = models.CharField(max_length=255, db_index=True)
    by = models.ForeignKey(Person)
    time = models.DateTimeField(default=datetime.datetime.now)

    def __unicode__(self):
        return self.name
