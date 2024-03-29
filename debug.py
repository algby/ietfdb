import sys
import time as timeutils
import inspect

try:
    import syslog
    logger = syslog.syslog
except ImportError:                     # import syslog will fail on Windows boxes
    import logging
    logging.basicConfig(filename='tracker.log',level=logging.INFO)
    logger = logging.info

try:
    from pprint import pformat
except ImportError:
    pformat = lambda x: x

import cProfile
import traceback as tb

try:
    from django.conf import settings
    debug = settings.DEBUG
except ImportError:
    debug = True

# A debug decorator, written by Paul Butler, taken from
# http://paulbutler.org/archives/python-debugging-with-decorators/
# Additional functions and decorator functionality added by
# Henrik Levkowetz

__version__ = "0.15"

increment = 2

# Number of times to indent output
# A list is used to force access by reference
_report_indent = [4]
_mark = [ timeutils.clock() ]

def set_indent(i):
    _report_indent[0] = i

def trace(fn):                 # renamed from 'report' by henrik 16 Jun 2011
    """Decorator to print information about a function
    call for use while debugging.
    Prints function name, arguments, and call number
    when the function is called. Prints this information
    again along with the return value when the function
    returns.
    """
    def fix(s,n=36):
        import re
        s = re.sub(r'\\t', ' ', s)
        s = re.sub(r'\s+', ' ', s)
        if len(s) > n+3:
            s = s[:n]+"..."
        return s
    def wrap(fn, *params,**kwargs):
        call = wrap.callcount = wrap.callcount + 1

        indent = ' ' * _report_indent[0]
        fc = "%s.%s(%s)" % (fn.__module__, fn.__name__, ', '.join(
            [fix(repr(a)) for a in params] +
            ["%s = %s" % (a, fix(repr(b))) for a,b in kwargs.items()]
        ))

        if debug:
            sys.stderr.write("%s* %s [#%s]\n" % (indent, fc, call))
        _report_indent[0] += increment
        ret = fn(*params,**kwargs)
        _report_indent[0] -= increment
        if debug:
            sys.stderr.write("%s  %s [#%s] ==> %s\n" % (indent, fc, call, fix(repr(ret))))

        return ret
    wrap.callcount = 0
    if debug:
        from decorator import decorator
        return decorator(wrap, fn)
    else:
        return fn

def mark():
    _mark[0] = timeutils.clock()

def lap(s):
    tau = timeutils.clock() - _mark[0]
    say(">  %s: %.3fs since mark" % (s, tau))

def clock(s):
    lap(s)
    _mark[0] = timeutils.clock()

def time(fn):
    """Decorator to print timing information about a function call.
    """
    def wrap(fn, *params,**kwargs):
        mark = timeutils.clock()

        indent = ' ' * _report_indent[0]
        fc = "%s.%s()" % (fn.__module__, fn.__name__,)

        ret = fn(*params,**kwargs)
        tau = timeutils.clock() - mark
        sys.stderr.write("%s| %s | %.3fs\n" % (indent, fc, tau))

        return ret
    wrap.callcount = 0
    if debug:
        from decorator import decorator
        return decorator(wrap, fn)
    else:
        return fn

def show(name):
    if debug:
        frame = inspect.stack()[1][0]
        value = eval(name, frame.f_globals, frame.f_locals)
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("%s%s: '%s'\n" % (indent, name, value))

def log(name):
    if debug:
        frame = inspect.stack()[1][0]
        value = eval(name, frame.f_globals, frame.f_locals)
        indent = ' ' * (_report_indent[0])
        logger("%s%s: %s" % (indent, name, value))

def pprint(name):
    if debug:
        frame = inspect.stack()[1][0]
        value = eval(name, frame.f_globals, frame.f_locals)
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("%s%s:\n" % (indent, name))
        lines = pformat(value).split('\n')
        for line in lines:
            sys.stderr.write("%s %s\n"%(indent, line))

def dir(name):
    if debug:
        name = "dir(%s)" % name
        frame = inspect.stack()[1][0]
        value = eval(name, frame.f_globals, frame.f_locals)
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("%s%s:\n" % (indent, name))
        lines = pformat(value).split('\n')
        for line in lines:
            sys.stderr.write("%s %s\n"%(indent, line))

def type(name):
    if debug:
        name = "type(%s)" % name
        frame = inspect.stack()[1][0]
        value = eval(name, frame.f_globals, frame.f_locals)
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("%s%s: %s\n" % (indent, name, value))
            
def say(s):
    if debug:
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("%s%s\n" % (indent, s))

def profile(fn):
    def wrapper(*args, **kwargs):
        datafn = fn.__name__ + ".profile" # Name the data file sensibly
        prof = cProfile.Profile()
        retval = prof.runcall(fn, *args, **kwargs)
        prof.dump_stats(datafn)
        return retval
    if debug:
        from decorator import decorator
        return decorator(wrapper, fn)
    else:
        return fn
    
def traceback(levels=None):
    if debug:
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("\n%s---- Stack ----\n" % indent)
        if levels:
            start = -2-levels
        else:
            start = None
        for s in tb.format_stack()[start:-1]:
            sys.stderr.write("%s%s" % (indent, s))
        sys.stderr.write("%s---------------\n" % indent)

def info(name):
    if debug:
        frame = inspect.stack()[1][0]
        value = eval(name, frame.f_globals, frame.f_locals)
        indent = ' ' * (_report_indent[0])
        sys.stderr.write("%s%s: %s %s\n" % (indent, name, value, type(value)))

