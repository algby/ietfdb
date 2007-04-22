from django.db import models
from ietf.idtracker.models import PersonOrOrgInfo

class LiaisonPurpose(models.Model):
    purpose_id = models.AutoField(primary_key=True)
    purpose_text = models.CharField(blank=True, maxlength=50)
    def __str__(self):
	return self.purpose_text
    class Meta:
        db_table = 'liaison_purpose'
    class Admin:
	pass

# poc is sometimes a PersonOrOrgInfo and sometimes not.
# This makes django raise DoesNotExist / PersonOrOrgInfo matching query does not exist
# todo: helper function to get the poc info
class FromBodies(models.Model):
    from_id = models.AutoField(primary_key=True)
    body_name = models.CharField(blank=True, maxlength=35)
    poc = models.IntegerField()
    #poc = models.ForeignKey(PersonOrOrgInfo, db_column='poc', raw_id_admin=True)
    is_liaison_manager = models.BooleanField()
    other_sdo = models.BooleanField()
    email_priority = models.IntegerField(null=True, blank=True)
    def __str__(self):
	return self.body_name
    class Meta:
        db_table = 'from_bodies'
    class Admin:
	pass

# Todo: helper function to look up from_id in FromBodes
# and Acronyms.
class LiaisonDetail(models.Model):
    detail_id = models.AutoField(primary_key=True)
    person_or_org_tag = models.ForeignKey(PersonOrOrgInfo, db_column='person_or_org_tag', raw_id_admin=True)
    submitted_date = models.DateField(null=True, blank=True)
    last_modified_date = models.DateField(null=True, blank=True)
    # If from the IETF, from_id is the acronym_id of the source.
    # If to the IETF, it's from FromBodies
    # There's assumed to be no overlap between the index values
    # of the two tables.
    from_id = models.IntegerField(null=True, blank=True)
    to_body = models.CharField(blank=True, maxlength=255)
    title = models.CharField(blank=True, maxlength=255)
    response_contact = models.CharField(blank=True, maxlength=255)
    technical_contact = models.CharField(blank=True, maxlength=255)
    purpose_text = models.TextField(blank=True, db_column='purpose')
    body = models.TextField(blank=True)
    deadline_date = models.DateField(null=True, blank=True)
    cc1 = models.TextField(blank=True)
    # unclear why cc2 is a CharField, but it's always
    # either NULL or blank.
    cc2 = models.CharField(blank=True, maxlength=50)
    submitter_name = models.CharField(blank=True, maxlength=255)
    submitter_email = models.CharField(blank=True, maxlength=255)
    by_secretariat = models.IntegerField(null=True, blank=True)
    to_poc = models.CharField(blank=True, maxlength=255)
    to_email = models.CharField(blank=True, maxlength=255)
    purpose = models.ForeignKey(LiaisonPurpose)
    replyto = models.CharField(blank=True, maxlength=255)
    def __str__(self):
	return self.title or "<no title>"
    class Meta:
        db_table = 'liaison_detail'
    class Admin:
	pass

class Sdos(models.Model):
    sdo_id = models.AutoField(primary_key=True)
    sdo_name = models.CharField(blank=True, maxlength=255)
    def __str__(self):
	return self.sdo_name
    class Meta:
        db_table = 'sdos'
    class Admin:
	pass

class LiaisonManagers(models.Model):
    person = models.ForeignKey(PersonOrOrgInfo, db_column='person_or_org_tag', raw_id_admin=True)
    email_priority = models.IntegerField(null=True, blank=True, core=True)
    sdo = models.ForeignKey(Sdos, edit_inline=models.TABULAR, num_in_admin=1)
    class Meta:
        db_table = 'liaison_managers'

class LiaisonsInterim(models.Model):
    title = models.CharField(blank=True, maxlength=255)
    submitter_name = models.CharField(blank=True, maxlength=255)
    submitter_email = models.CharField(blank=True, maxlength=255)
    submitted_date = models.DateField(null=True, blank=True)
    from_id = models.IntegerField(null=True, blank=True)
    def __str__(self):
	return self.title
    class Meta:
        db_table = 'liaisons_interim'
    class Admin:
	pass

class Uploads(models.Model):
    file_id = models.AutoField(primary_key=True)
    file_title = models.CharField(blank=True, maxlength=255, core=True)
    person = models.ForeignKey(PersonOrOrgInfo, db_column='person_or_org_tag', raw_id_admin=True)
    file_extension = models.CharField(blank=True, maxlength=10)
    detail = models.ForeignKey(LiaisonDetail, raw_id_admin=True, edit_inline=models.TABULAR, num_in_admin=1)
    def __str__(self):
	return self.file_title
    class Meta:
        db_table = 'uploads'

# empty table
#class SdoChairs(models.Model):
#    sdo = models.ForeignKey(Sdos)
#    person = models.ForeignKey(PersonOrOrgInfo, db_column='person_or_org_tag', raw_id_admin=True)
#    email_priority = models.IntegerField(null=True, blank=True)
#    class Meta:
#        db_table = 'sdo_chairs'
#    class Admin:
#	pass
