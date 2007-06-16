import re
from buildbot.steps.shell import ShellCommand
from buildbot.status.builder import SUCCESS, FAILURE, WARNINGS

try:
    import cStringIO
    StringIO = cStringIO.StringIO
except ImportError:
    from StringIO import StringIO

class DjangoTest(ShellCommand):
    name = "django-test"
    command = ["python", "manage.py", "test"]
    description = ["running django-test"]
    descriptionDone = ["django-test"]
    flunkOnFailure = False
    warnOnFailure = True
    flunkingIssues = ["exception", "failure"] # any pyflakes lines like this cause FAILURE

    msgtypes = ("exceptions", "failures", "missing", "skipped", "pass", "diffs", "diff")

    def createSummary(self, log):
        summaries = {}
        typelist = {}
        counts = {}
        m = None
        def count(m):
            if not m in counts:
                counts[m] = 0
            counts[m] += 1

        for type in self.msgtypes:
            typelist[type] = set([])

        for line in StringIO(log.getText()).readlines():
            if re.search("^Traceback ", line):
                m = "exception"
                typelist["exceptions"].add(m)
                count(m)
            if re.search("^Fail \d+ ", line):
                m = "fail_%s" % line.split()[1]
                typelist["failures"].add(m)
                count(m)
            if re.search("^Skipping ", line):
                m = "skipped"
                typelist["skipped"].add(m)
                count(m)
            if re.search("^Diff: +.*", line):
                m = "diffs"
                count(m)
                summaries[m] = []
                typelist["diffs"].add(m)                
                m = "diff_%s" % line.split()[1]
                typelist["diff"].add(m)                
                count(m)
            if re.search("^OK +.* ", line):
                m = "pass_%s" % line.split()[1]
                typelist["pass"].add(m)
                count(m)
            if re.search("^Pass \d+ ", line):
                m = "pass_%s" % line.split()[1]
                typelist["pass"].add(m)
                count(m)
            if re.search("^Miss .*", line):
                m = "missing"
                typelist["missing"].add(m)
                count(m)
            if re.search("^Response count:", line):
                m = None
            if m:
                if not m in summaries:
                    summaries[m] = []
                summaries[m].append(line)

        self.descriptionDone = self.descriptionDone[:]
        for type in self.msgtypes:
            for msg in typelist[type]:
                if counts[msg]:
                    if counts[msg] == 1 and msg.startswith("diff"):
                        difflen = len(summaries[msg])
                        if difflen >= 102:
                            self.descriptionDone.append("%s&nbsp;(long)" % (msg))
                        else:
                            self.descriptionDone.append("%s&nbsp;(%s<i>l</i>)" % (msg, difflen))
                    else:
                        self.descriptionDone.append("%s=%d" % (msg, counts[msg]))
                    self.addCompleteLog(msg, "".join(summaries[msg]))
            self.setProperty("urltest-%s" % type, sum([counts[msg] for msg in typelist[type]]))
        self.setProperty("urltest-total", sum([counts[msg] for msg in counts if msg not in typelist["pass"]]))

    def evaluateCommand(self, cmd):
        if cmd.rc != 0:
            return FAILURE
        for type in self.flunkingIssues:
            try:
                if self.getProperty("urltest-%s" % type):
                    return FAILURE
            except KeyError:
                pass
        if self.getProperty("urltest-total"):
            return WARNINGS
        return SUCCESS