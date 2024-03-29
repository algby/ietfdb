import datetime
import re

from django.conf import settings
from django.template.defaultfilters import filesizeformat
from ietf.submit.parsers.base import FileParser


class PlainParser(FileParser):

    def __init__(self, fd):
        super(PlainParser, self).__init__(fd)

    # If some error is found after this method invocation
    # no other file parsing is recommended
    def critical_parse(self):
        super(PlainParser, self).critical_parse()
        self.parse_max_size()
        self.parse_file_charset()
        self.parse_name()
        return self.parsed_info

    def parse_max_size(self):
        if self.fd.size > settings.IDSUBMIT_MAX_PLAIN_DRAFT_SIZE:
            self.parsed_info.add_error('File size is larger than %s' % filesizeformat(settings.IDSUBMIT_MAX_PLAIN_DRAFT_SIZE))
        self.parsed_info.metadata.file_size = self.fd.size
        self.parsed_info.metadata.submission_date = datetime.date.today()

    def parse_file_charset(self):
        import magic
        self.fd.file.seek(0)
        content = self.fd.file.read(4096)
        if hasattr(magic, "open"):
            m = magic.open(magic.MAGIC_MIME)
            m.load()
            filetype = m.buffer(content)
        else:
            m = magic.Magic()
            m.cookie = magic.magic_open(magic.MAGIC_NONE | magic.MAGIC_MIME | magic.MAGIC_MIME_ENCODING)
            magic.magic_load(m.cookie, None)
            filetype = m.from_buffer(content)
        if not 'ascii' in filetype:
            self.parsed_info.add_error('A plain text ASCII document must be submitted.')

    def parse_name(self):
        self.fd.file.seek(0)
        draftre = re.compile('(draft-\S+)')
        revisionre = re.compile('.*-(\d+)$')
        limit = 80
        while limit:
            limit -= 1
            line = self.fd.readline()
            match = draftre.search(line)
            if not match:
                continue
            name = match.group(1)
            name = re.sub('^[^\w]+', '', name)
            name = re.sub('[^\w]+$', '', name)
            name = re.sub('\.txt$', '', name)
            extra_chars = re.sub('[0-9a-z\-]', '', name)
            if extra_chars:
                if len(extra_chars) == 1:
                    self.parsed_info.add_error((u'The name contains a disallowed character: %s ' % (', '.join(set(extra_chars))).decode('ascii','replace')) +
                                                u'(see http://www.ietf.org/id-info/guidelines.html#naming for details).')
                else:
                    self.parsed_info.add_error((u'The name contains disallowed characters: %s ' % (', '.join(set(extra_chars))).decode('ascii','replace')) +
                                                u'(see http://www.ietf.org/id-info/guidelines.html#naming for details).')
            match_revision = revisionre.match(name)
            if match_revision:
                self.parsed_info.metadata.rev = match_revision.group(1)
            else:
                self.parsed_info.add_error(u'The name found on the first page of the document does not contain a revision: "%s"' % (name,))
            name = re.sub('-\d+$', '', name)
            self.parsed_info.metadata.name = name
            return
        self.parsed_info.add_error('The first page of the document does not contain a legitimate name that start with draft-*')
