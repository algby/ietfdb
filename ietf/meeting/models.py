# old meeting models can be found in ../proceedings/models.py

import pytz
import datetime
from urlparse import urljoin
import copy
import os
import sys
import re

import debug                            # pyflakes:ignore

from django.db import models
from django.conf import settings
# mostly used by json_dict()
#from django.template.defaultfilters import slugify, date as date_format, time as time_format
from django.template.defaultfilters import date as date_format

from timedeltafield import TimedeltaField

from ietf.doc.models import Document
from ietf.group.models import Group
from ietf.name.models import MeetingTypeName, TimeSlotTypeName, SessionStatusName, ConstraintName, RoomResourceName
from ietf.person.models import Person

countries = pytz.country_names.items()
countries.sort(lambda x,y: cmp(x[1], y[1]))

timezones = [(name, name) for name in pytz.common_timezones]
timezones.sort()


# this is used in models to format dates, as the built-in json serializer
# can not deal with them, and the django provided serializer is inaccessible.
from django.utils import datetime_safe
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"

def fmt_date(o):
    d = datetime_safe.new_date(o)
    return d.strftime(DATE_FORMAT)

class Meeting(models.Model):
    # number is either the number for IETF meetings, or some other
    # identifier for interim meetings/IESG retreats/liaison summits/...
    number = models.CharField(unique=True, max_length=64)
    type = models.ForeignKey(MeetingTypeName)
    # Date is useful when generating a set of timeslot for this meeting, but
    # is not used to determine date for timeslot instances thereafter, as
    # they have their own datetime field.
    date = models.DateField()
    city = models.CharField(blank=True, max_length=255)
    country = models.CharField(blank=True, max_length=2, choices=countries)
    # We can't derive time-zone from country, as there are some that have
    # more than one timezone, and the pytz module doesn't provide timezone
    # lookup information for all relevant city/country combinations.
    time_zone = models.CharField(blank=True, max_length=255, choices=timezones)
    venue_name = models.CharField(blank=True, max_length=255)
    venue_addr = models.TextField(blank=True)
    break_area = models.CharField(blank=True, max_length=255)
    reg_area = models.CharField(blank=True, max_length=255)
    agenda_note = models.TextField(blank=True, help_text="Text in this field will be placed at the top of the html agenda page for the meeting.  HTML can be used, but will not validated.")
    agenda     = models.ForeignKey('Schedule',null=True,blank=True, related_name='+')

    def __unicode__(self):
        if self.type_id == "ietf":
            return "IETF-%s" % (self.number)
        else:
            return self.number

    def time_zone_offset(self):
        # Look at the time of 8 o'clock sunday, rather than 0h sunday, to get
        # the right time after a possible summer/winter time change.
        if self.time_zone:
            return pytz.timezone(self.time_zone).localize(datetime.datetime.combine(self.date, datetime.time(8, 0))).strftime("%z")
        else:
            return ""

    def get_meeting_date (self,offset):
        return self.date + datetime.timedelta(days=offset)

    def end_date(self):
        return self.get_meeting_date(5)

    @classmethod
    def get_first_cut_off(cls):
        date = cls.objects.all().filter(type="ietf").order_by('-date')[0].date
        offset = datetime.timedelta(days=settings.FIRST_CUTOFF_DAYS)
        return date - offset

    @classmethod
    def get_second_cut_off(cls):
        date = cls.objects.all().filter(type="ietf").order_by('-date')[0].date
        offset = datetime.timedelta(days=settings.SECOND_CUTOFF_DAYS)
        return date - offset

    @classmethod
    def get_ietf_monday(cls):
        date = cls.objects.all().filter(type="ietf").order_by('-date')[0].date
        return date + datetime.timedelta(days=-date.weekday(), weeks=1)

    # the various dates are currently computed
    def get_submission_start_date(self):
        return self.date + datetime.timedelta(days=settings.SUBMISSION_START_DAYS)
    def get_submission_cut_off_date(self):
        return self.date + datetime.timedelta(days=settings.SUBMISSION_CUTOFF_DAYS)
    def get_submission_correction_date(self):
        return self.date + datetime.timedelta(days=settings.SUBMISSION_CORRECTION_DAYS)

    def get_schedule_by_name(self, name):
        return self.schedule_set.filter(name=name).first()

    @property
    def sessions_that_can_meet(self):
        return self.session_set.exclude(status__slug='notmeet').exclude(status__slug='disappr').exclude(status__slug='deleted').exclude(status__slug='apprw')

    def sessions_that_can_be_placed(self):
        from django.db.models import Q
        donotplace_groups = Q(group__acronym="edu")
        donotplace_groups |= Q(group__acronym="tools")
        donotplace_groups |= Q(group__acronym="iesg")
        donotplace_groups |= Q(group__acronym="ietf")
        donotplace_groups |= Q(group__acronym="iepg")
        donotplace_groups |= Q(group__acronym="iab")
        return self.sessions_that_can_meet.exclude(donotplace_groups)

    def json_url(self):
        return "/meeting/%s.json" % (self.number, )

    def base_url(self):
        return "/meeting/%s" % (self.number, )

    def json_dict(self, host_scheme):
        # unfortunately, using the datetime aware json encoder seems impossible,
        # so the dates are formatted as strings here.
        agenda_url = ""
        if self.agenda:
            agenda_url = urljoin(host_scheme, self.agenda.base_url())
        return {
            'href':                 urljoin(host_scheme, self.json_url()),
            'name':                 self.number,
            'submission_start_date':   fmt_date(self.get_submission_start_date()),
            'submission_cut_off_date': fmt_date(self.get_submission_cut_off_date()),
            'submission_correction_date': fmt_date(self.get_submission_correction_date()),
            'date':                    fmt_date(self.date),
            'agenda_href':             agenda_url,
            'city':                    self.city,
            'country':                 self.country,
            'time_zone':               self.time_zone,
            'venue_name':              self.venue_name,
            'venue_addr':              self.venue_addr,
            'break_area':              self.break_area,
            'reg_area':                self.reg_area
            }

    def build_timeslices(self):
        days = []          # the days of the meetings
        time_slices = {}   # the times on each day
        slots = {}

        for ts in self.timeslot_set.all():
            if ts.location_id is None:
                continue
            ymd = ts.time.date()
            if ymd not in time_slices:
                time_slices[ymd] = []
                slots[ymd] = []
                days.append(ymd)

            if ymd in time_slices:
                # only keep unique entries
                if [ts.time, ts.time + ts.duration, ts.duration.seconds] not in time_slices[ymd]:
                    time_slices[ymd].append([ts.time, ts.time + ts.duration, ts.duration.seconds])
                    slots[ymd].append(ts)

        days.sort()
        for ymd in time_slices:
            time_slices[ymd].sort()
            slots[ymd].sort(lambda x,y: cmp(x.time, y.time))
        return days,time_slices,slots

    # this functions makes a list of timeslices and rooms, and
    # makes sure that all schedules have all of them.
#    def create_all_timeslots(self):
#        alltimeslots = self.timeslot_set.all()
#        for sched in self.schedule_set.all():
#            ts_hash = {}
#            for ss in sched.scheduledsession_set.all():
#                ts_hash[ss.timeslot] = ss
#            for ts in alltimeslots:
#                if not (ts in ts_hash):
#                    ScheduledSession.objects.create(schedule = sched,
#                                                    timeslot = ts)

    def vtimezone(self):
        if self.time_zone:
            try:
                tzfn = os.path.join(settings.TZDATA_ICS_PATH, self.time_zone + ".ics")
                if os.path.exists(tzfn):
                    with open(tzfn) as tzf:
                        icstext = tzf.read()
                    vtimezone = re.search("(?sm)(\nBEGIN:VTIMEZONE.*\nEND:VTIMEZONE\n)", icstext).group(1).strip()
                    if vtimezone:
                        vtimezone += "\n"
                    return vtimezone
            except IOError:
                pass
        return ''

    def set_official_agenda(self, agenda):
        if self.agenda != agenda:
            self.agenda = agenda
            self.save()

    class Meta:
        ordering = ["-date", ]

class ResourceAssociation(models.Model):
    name = models.ForeignKey(RoomResourceName)
    #url  = models.UrlField()       # not sure what this was for.
    icon = models.CharField(max_length=64)       # icon to be found in /static/img
    desc = models.CharField(max_length=256)

    def __unicode__(self):
        return self.desc

    def json_dict(self, host_scheme):
        res1 = dict()
        res1['name'] = self.name.slug
        res1['icon'] = "/images/%s" % (self.icon)
        res1['desc'] = self.desc
        res1['resource_id'] = self.pk
        return res1

class Room(models.Model):
    meeting = models.ForeignKey(Meeting)
    name = models.CharField(max_length=255)
    capacity = models.IntegerField(null=True, blank=True)
    resources = models.ManyToManyField(ResourceAssociation, blank = True)

    def __unicode__(self):
        return "%s size: %u" % (self.name, self.capacity)

    def delete_timeslots(self):
        for ts in self.timeslot_set.all():
            ts.scheduledsession_set.all().delete()
            ts.delete()

    def create_timeslots(self):
        days, time_slices, slots  = self.meeting.build_timeslices()
        for day in days:
            for ts in slots[day]:
                TimeSlot.objects.create(type_id=ts.type_id,
                                    meeting=self.meeting,
                                    name=ts.name,
                                    time=ts.time,
                                    location=self,
                                    duration=ts.duration)
        #self.meeting.create_all_timeslots()

    def dom_id(self):
        return "room%u" % (self.pk)

    def json_url(self):
        return "/meeting/%s/room/%s.json" % (self.meeting.number, self.id)

    def json_dict(self, host_scheme):
        return {
            'href':                 urljoin(host_scheme, self.json_url()),
            'name':                 self.name,
            'capacity':             self.capacity,
            }


class TimeSlot(models.Model):
    """
    Everything that would appear on the meeting agenda of a meeting is
    mapped to a time slot, including breaks. Sessions are connected to
    TimeSlots during scheduling.
    """
    meeting = models.ForeignKey(Meeting)
    type = models.ForeignKey(TimeSlotTypeName)
    name = models.CharField(max_length=255)
    time = models.DateTimeField()
    duration = TimedeltaField()
    location = models.ForeignKey(Room, blank=True, null=True)
    show_location = models.BooleanField(default=True, help_text="Show location in agenda")
    sessions = models.ManyToManyField('Session', related_name='slots', through='ScheduledSession', null=True, blank=True, help_text=u"Scheduled session, if any")
    modified = models.DateTimeField(default=datetime.datetime.now)
    #

    @property
    def session(self):
        if not hasattr(self, "_session_cache"):
            self._session_cache = self.sessions.filter(scheduledsession__schedule=self.meeting.agenda).first()
        return self._session_cache

    @property
    def time_desc(self):
        return u"%s-%s" % (self.time.strftime("%H%M"), (self.time + self.duration).strftime("%H%M"))

    def meeting_date(self):
        return self.time.date()

    def registration(self):
        # below implements a object local cache
        # it tries to find a timeslot of type registration which starts at the same time as this slot
        # so that it can be shown at the top of the agenda.
        if not hasattr(self, '_reg_info'):
            try:
                self._reg_info = TimeSlot.objects.get(meeting=self.meeting, time__month=self.time.month, time__day=self.time.day, type="reg")
            except TimeSlot.DoesNotExist:
                self._reg_info = None
        return self._reg_info

    def __unicode__(self):
        location = self.get_location()
        if not location:
            location = "(no location)"

        return u"%s: %s-%s %s, %s" % (self.meeting.number, self.time.strftime("%m-%d %H:%M"), (self.time + self.duration).strftime("%H:%M"), self.name, location)
    def end_time(self):
        return self.time + self.duration
    def get_location(self):
        location = self.location
        if location:
            location = location.name
        elif self.type_id == "reg":
            location = self.meeting.reg_area
        elif self.type_id == "break":
            location = self.meeting.break_area
        if not self.show_location:
            location = ""
        return location

    @property
    def tz(self):
        if self.meeting.time_zone:
            return pytz.timezone(self.meeting.time_zone)
        else:
            return None
    def tzname(self):
        if self.tz:
            return self.tz.tzname(self.time)
        else:
            return ""
    def utc_start_time(self):
        if self.tz:
            local_start_time = self.tz.localize(self.time)
            return local_start_time.astimezone(pytz.utc)
        else:
            return None
    def utc_end_time(self):
        if self.tz:
            local_end_time = self.tz.localize(self.end_time())
            return local_end_time.astimezone(pytz.utc)
        else:
            return None

    @property
    def js_identifier(self):
        # this returns a unique identifier that is js happy.
        #  {{s.timeslot.time|date:'Y-m-d'}}_{{ s.timeslot.time|date:'Hi' }}"
        # also must match:
        #  {{r|slugify}}_{{day}}_{{slot.0|date:'Hi'}}
        dom_id="ts%u" % (self.pk)
        if self.location is not None:
            dom_id = self.location.dom_id()
        return "%s_%s_%s" % (dom_id, self.time.strftime('%Y-%m-%d'), self.time.strftime('%H%M'))

    def json_dict(self, host_scheme):
        ts = dict()
        ts['timeslot_id'] = self.id
        ts['href']        = urljoin(host_scheme, self.json_url())
        ts['room']        = self.get_location()
        ts['roomtype'] = self.type.slug
        if self.location is not None:
            ts['capacity'] = self.location.capacity
        ts["time"]     = date_format(self.time, 'Hi')
        ts["date"]     = fmt_date(self.time)
        ts["domid"]    = self.js_identifier
        following = self.slot_to_the_right
        if following is not None:
            ts["following_timeslot_id"] = following.id
        return ts

    def json_url(self):
        return "/meeting/%s/timeslot/%s.json" % (self.meeting.number, self.id)

    """
    This routine takes the current timeslot, which is assumed to have no location,
    and assigns a room, and then creates an identical timeslot for all of the other
    rooms.
    """
    def create_concurrent_timeslots(self):
        rooms = self.meeting.room_set.all()
        self.room = rooms[0]
	self.save()
        for room in rooms[1:]:
            ts = copy.copy(self)
            ts.id = None
            ts.location = room
            ts.save()

        #self.meeting.create_all_timeslots()

    """
    This routine deletes all timeslots which are in the same time as this slot.
    """
    def delete_concurrent_timeslots(self):
        # can not include duration in filter, because there is no support
        # for having it a WHERE clause.
        # below will delete self as well.
        for ts in self.meeting.timeslot_set.filter(time=self.time).all():
            if ts.duration!=self.duration:
                continue

            # now remove any schedule that might have been made to this
            # timeslot.
            ts.scheduledsession_set.all().delete()
            ts.delete()

    """
    Find a timeslot that comes next, in the same room.   It must be on the same day,
    and it must have a gap of less than 11 minutes. (10 is the spec)
    """
    @property
    def slot_to_the_right(self):
        return self.meeting.timeslot_set.filter(
            location = self.location,       # same room!
            type     = self.type,           # must be same type (usually session)
            time__gt = self.time + self.duration,  # must be after this session
            time__lt = self.time + self.duration + datetime.timedelta(seconds=11*60)).first()

# end of TimeSlot

class Schedule(models.Model):
    """
    Each person may have multiple agendas saved.
    An Agenda may be made visible, which means that it will show up in
    public drop down menus, etc.  It may also be made public, which means
    that someone who knows about it by name/id would be able to reference
    it.  A non-visible, public agenda might be passed around by the
    Secretariat to IESG members for review.  Only the owner may edit the
    agenda, others may copy it
    """
    meeting  = models.ForeignKey(Meeting, null=True)
    name     = models.CharField(max_length=16, blank=False)
    owner    = models.ForeignKey(Person)
    visible  = models.BooleanField(default=True, help_text=u"Make this agenda available to those who know about it")
    public   = models.BooleanField(default=True, help_text=u"Make this agenda publically available")
    badness  = models.IntegerField(null=True, blank=True)
    # considering copiedFrom = models.ForeignKey('Schedule', blank=True, null=True)

    def __unicode__(self):
        return u"%s:%s(%s)" % (self.meeting, self.name, self.owner)

    def base_url(self):
        return "/meeting/%s/agenda/%s/%s" % (self.meeting.number, self.owner_email(), self.name)

    # temporary property to pacify the places where Schedule.scheduledsession_set is used
    @property
    def scheduledsession_set(self):
        return self.assignments

#     def url_edit(self):
#         return "/meeting/%s/agenda/%s/edit" % (self.meeting.number, self.name)
#
#     @property
#     def relurl_edit(self):
#         return self.url_edit("")

    def owner_email(self):
        emails = self.owner.email_set.all()
        if len(emails)>0:
            return emails[0].address
        else:
            return "noemail"

    @property
    def visible_token(self):
        if self.visible:
            return "visible"
        else:
            return "hidden"

    @property
    def public_token(self):
        if self.public:
            return "public"
        else:
            return "private"

    @property
    def is_official(self):
        return (self.meeting.agenda == self)

    @property
    def official_class(self):
        if self.is_official:
            return "agenda_official"
        else:
            return "agenda_unofficial"

    # returns a dictionary {group -> [scheduledsession+]}
    # and it has [] if the session is not placed.
    # if there is more than one session for that group,
    # then a list of them is returned (always a list)
    @property
    def official_token(self):
        if self.is_official:
            return "official"
        else:
            return "unofficial"

    def delete_scheduledsessions(self):
        self.scheduledsession_set.all().delete()

    def json_url(self):
        return "%s.json" % self.base_url()

    def json_dict(self, host_scheme):
        sch = dict()
        sch['schedule_id'] = self.id
        sch['href']        = urljoin(host_scheme, self.json_url())
        if self.visible:
            sch['visible']  = "visible"
        else:
            sch['visible']  = "hidden"
        if self.public:
            sch['public']   = "public"
        else:
            sch['public']   = "private"
        sch['owner']       = urljoin(host_scheme, self.owner.json_url())
        # should include href to list of scheduledsessions, but they have no direct API yet.
        return sch

    @property
    def qs_scheduledsessions_with_assignments(self):
        return self.scheduledsession_set.filter(session__isnull=False)

    @property
    def group_mapping(self):
        assignments,sessions,total,scheduled = self.group_session_mapping
        return assignments

    @property
    def group_session_mapping(self):
        assignments = dict()
        sessions    = dict()
        total       = 0
        scheduled   = 0
        allschedsessions = self.qs_scheduledsessions_with_assignments.filter(timeslot__type = "session").all()
        for sess in self.meeting.sessions_that_can_meet.all():
            assignments[sess.group] = []
            sessions[sess] = None
            total += 1

        for ss in allschedsessions:
            assignments[ss.session.group].append(ss)
            # XXX can not deal with a session in two slots
            sessions[ss.session] = ss
            scheduled += 1
        return assignments,sessions,total,scheduled

    @property
    def sessions_that_can_meet(self):
        if not hasattr(self, "_cached_sessions_that_can_meet"):
            self._cached_sessions_that_can_meet = self.meeting.sessions_that_can_meet.all()
        return self._cached_sessions_that_can_meet

    def area_list(self):
        return ( self.assignments.filter(session__group__type__slug__in=['wg', 'rg', 'ag', 'iab'],
                                         session__group__parent__isnull=False)
                 .order_by('session__group__parent__acronym')
                 .values_list('session__group__parent__acronym', flat=True)
                 .distinct() )

    def groups(self):
        return Group.objects.filter(type__slug__in=['wg', 'rg', 'ag', 'iab'], session__scheduledsession__schedule=self).distinct().order_by('parent__acronym', 'acronym')

    # calculate badness of entire schedule
    def calc_badness(self):
        # now calculate badness
        assignments = self.group_mapping
        return self.calc_badness1(assignments)

    # calculate badness of entire schedule
    def calc_badness1(self, assignments):
        badness = 0
        for sess in self.sessions_that_can_meet:
            badness += sess.badness(assignments)
        self.badness = badness
        return badness

    def delete_schedule(self):
        self.scheduledsession_set.all().delete()
        self.delete()

# to be renamed ScheduleTimeslotSessionAssignments (stsa)
class ScheduledSession(models.Model):
    """
    This model provides an N:M relationship between Session and TimeSlot.
    Each relationship is attached to the named agenda, which is owned by
    a specific person/user.
    """
    timeslot = models.ForeignKey('TimeSlot', null=False, blank=False, help_text=u"")
    session  = models.ForeignKey('Session', null=True, default=None, help_text=u"Scheduled session")
    schedule = models.ForeignKey('Schedule', null=False, blank=False, related_name='assignments')
    extendedfrom = models.ForeignKey('ScheduledSession', null=True, default=None, help_text=u"Timeslot this session is an extension of")
    modified = models.DateTimeField(default=datetime.datetime.now)
    notes    = models.TextField(blank=True)
    badness  = models.IntegerField(default=0, blank=True, null=True)
    pinned   = models.BooleanField(default=False, help_text="Do not move session during automatic placement")

    class Meta:
        ordering = ["timeslot__time", "session__group__parent__name", "session__group__acronym", "session__name", ]

    # use to distinguish this from FakeScheduledSession in placement.py
    faked   = "real"

    def __unicode__(self):
        return u"%s [%s<->%s]" % (self.schedule, self.session, self.timeslot)

    @property
    def room_name(self):
        return self.timeslot.location.name

    @property
    def acronym(self):
        if self.session and self.session.group:
            return self.session.group.acronym

    @property
    def slot_to_the_right(self):
        s = self.timeslot.slot_to_the_right
        if s:
            return self.schedule.scheduledsession_set.filter(timeslot=s).first()
        else:
            return None

    @property
    def area(self):
        if not self.session or not self.session.group:
            return ""
        if self.session.group.type_id == "irtf":
            return "irtf"
        if self.timeslot.type_id == "plenary":
            return "1plenary"
        if not self.session.group.parent or not self.session.group.parent.type_id in ["area","irtf"]:
            return ""
        return self.session.group.parent.acronym

    @property
    def group_type_str(self):
        if not self.session or not self.session.group:
            return ""
        if self.session.group and self.session.group.type_id == "wg":
            if self.session.group.state_id == "bof":
                return "BOF"
            else:
                return "WG"

        return ""

    @property
    def slottype(self):
        if self.timeslot and self.timeslot.type:
            return self.timeslot.type.slug
        else:
            return ""

    def json_url(self):
        return "/meeting/%s/agenda/%s/%s/session/%u.json" % (self.schedule.meeting.number,
                                                             self.schedule.owner_email(),
                                                             self.schedule.name, self.id)

    def json_dict(self, host_scheme):
        ss = dict()
        ss['scheduledsession_id'] = self.id
        ss['href']          = urljoin(host_scheme, self.json_url())
        ss['timeslot_id'] = self.timeslot.id

        efset = self.session.scheduledsession_set.filter(schedule=self.schedule).order_by("timeslot__time")
        if efset.count() > 1:
            # now we know that there is some work to do finding the extendedfrom_id.
            # loop through the list of items
            previous = None
            for efss in efset:
                if efss.pk == self.pk:
                    extendedfrom = previous
                    break
                previous = efss
            if extendedfrom is not None:
                ss['extendedfrom_id']  = extendedfrom.id

        if self.session:
            ss['session_id']  = self.session.id
        ss["pinned"]   = self.pinned
        return ss

class Constraint(models.Model):
    """
    Specifies a constraint on the scheduling.
    One type (name=conflic?) of constraint is between source WG and target WG,
           e.g. some kind of conflict.
    Another type (name=bethere) of constraint is between source WG and
           availability of a particular Person, usually an AD.
    A third type (name=avoidday) of constraint is between source WG and
           a particular day of the week, specified in day.
    """
    meeting = models.ForeignKey(Meeting)
    source = models.ForeignKey(Group, related_name="constraint_source_set")
    target = models.ForeignKey(Group, related_name="constraint_target_set", null=True)
    person = models.ForeignKey(Person, null=True, blank=True)
    day    = models.DateTimeField(null=True, blank=True)
    name   = models.ForeignKey(ConstraintName)

    active_status = None

    def __unicode__(self):
        return u"%s %s target=%s person=%s" % (self.source, self.name.name.lower(), self.target, self.person)

    def brief_display(self):
        if self.target and self.person:
            return u"%s ; %s" % (self.target.acronym, self.person)
        elif self.target and not self.person:
            return u"%s " % (self.target.acronym)
        elif not self.target and self.person:
            return u"%s " % (self.person)



    @property
    def person_conflicted(self):
        if self.person is None:
            return "unknown person"
        return self.person.name

    def status(self):
        if self.active_status is not None:
            return self.active_status
        else:
            return True

    def __lt__(self, y):
        #import sys
        #sys.stdout.write("me: %s y: %s\n" % (self.name.slug, y.name.slug))
        if self.name.slug == 'conflict' and y.name.slug == 'conflic2':
            return True
        if self.name.slug == 'conflict' and y.name.slug == 'conflic3':
            return True
        if self.name.slug == 'conflic2' and y.name.slug == 'conflic3':
            return True
        return False

    def constraint_cost(self):
        return self.name.penalty;

    def json_url(self):
        return "/meeting/%s/constraint/%s.json" % (self.meeting.number, self.id)

    def json_dict(self, host_scheme):
        ct1 = dict()
        ct1['constraint_id'] = self.id
        ct1['href']          = urljoin(host_scheme, self.json_url())
        ct1['name']          = self.name.slug
        if self.person is not None:
            ct1['person_href'] = urljoin(host_scheme, self.person.json_url())
        if self.source is not None:
            ct1['source_href'] = urljoin(host_scheme, self.source.json_url())
        if self.target is not None:
            ct1['target_href'] = urljoin(host_scheme, self.target.json_url())
        ct1['meeting_href'] = urljoin(host_scheme, self.meeting.json_url())
        return ct1

constraint_cache_uses = 0
constraint_cache_initials = 0

class Session(models.Model):
    """Session records that a group should have a session on the
    meeting (time and location is stored in a TimeSlot) - if multiple
    timeslots are needed, multiple sessions will have to be created.
    Training sessions and similar are modeled by filling in a
    responsible group (e.g. Edu team) and filling in the name."""
    meeting = models.ForeignKey(Meeting)
    name = models.CharField(blank=True, max_length=255, help_text="Name of session, in case the session has a purpose rather than just being a group meeting")
    short = models.CharField(blank=True, max_length=32, help_text="Short version of 'name' above, for use in filenames")
    group = models.ForeignKey(Group)    # The group type determines the session type.  BOFs also need to be added as a group.
    attendees = models.IntegerField(null=True, blank=True)
    agenda_note = models.CharField(blank=True, max_length=255)
    requested = models.DateTimeField(default=datetime.datetime.now)
    requested_by = models.ForeignKey(Person)
    requested_duration = TimedeltaField(default=0)
    comments = models.TextField(blank=True)
    status = models.ForeignKey(SessionStatusName)
    scheduled = models.DateTimeField(null=True, blank=True)
    modified = models.DateTimeField(default=datetime.datetime.now)

    materials = models.ManyToManyField(Document, blank=True)
    resources = models.ManyToManyField(ResourceAssociation)

    unique_constraints_dict = None

    def agenda(self):
        items = self.materials.filter(type="agenda",states__type="agenda",states__slug="active")
        if items and items[0] is not None:
            return items[0]
        else:
            return None

    def minutes(self):
        try:
            return self.materials.get(type="minutes",states__type="minutes",states__slug="active")
        except Exception:
            return None

    def slides(self):
        try:
            return self.materials.filter(type="slides",states__type="slides",states__slug="active").order_by("order")
        except Exception:
            return []

    def __unicode__(self):
        if self.meeting.type_id == "interim":
            return self.meeting.number

        ss0name = "(unscheduled)"
        ss = self.scheduledsession_set.order_by('timeslot__time')
        if ss:
            ss0name = ss[0].timeslot.time.strftime("%H%M")
        return u"%s: %s %s[%u]" % (self.meeting, self.group.acronym, ss0name, self.pk)

    def is_bof(self):
        return self.group.is_bof();

    @property
    def short_name(self):
        if self.name:
            return self.name
        if self.short:
            return self.short
        if self.group:
            return self.group.acronym
        return u"req#%u" % (id)

    @property
    def special_request_token(self):
        if self.comments is not None and len(self.comments)>0:
            return "*"
        else:
            return ""

    def constraints(self):
        return Constraint.objects.filter(source=self.group, meeting=self.meeting).order_by('name__name')

    def reverse_constraints(self):
        return Constraint.objects.filter(target=self.group, meeting=self.meeting).order_by('name__name')

    def scheduledsession_for_agenda(self, schedule):
        return self.scheduledsession_set.filter(schedule=schedule)[0]

    def official_scheduledsession(self):
        return self.scheduledsession_for_agenda(self.meeting.agenda)

    def unique_constraints(self):
        global constraint_cache_uses, constraint_cache_initials
        constraint_cache_uses += 1
        # this cache keeps the automatic placer from visiting the database continuously
        if self.unique_constraints_dict is not None:
            constraint_cache_initials += 1
            return self.unique_constraints_dict
        self.unique_constraints_dict = dict()
        for constraint in self.constraints():
            self.unique_constraints_dict[constraint.target] = constraint

        for constraint in self.reverse_constraints():
            # update the constraint if there is a previous one, and
            # it is more important than what we had before
            if not (constraint in self.unique_constraints_dict) or (self.unique_constraints_dict[constraint.source] < constraint):
                self.unique_constraints_dict[constraint.source] = constraint
        return self.unique_constraints_dict

    def constraints_dict(self, host_scheme):
        constraint_list = []
        for constraint in self.constraints():
            ct1 = constraint.json_dict(host_scheme)
            constraint_list.append(ct1)

        for constraint in self.reverse_constraints():
            ct1 = constraint.json_dict(host_scheme)
            constraint_list.append(ct1)
        return constraint_list

    @property
    def people_constraints(self):
        return self.group.constraint_source_set.filter(meeting=self.meeting, name='bethere')

    def json_url(self):
        return "/meeting/%s/session/%s.json" % (self.meeting.number, self.id)

    def json_dict(self, host_scheme):
        sess1 = dict()
        sess1['href']           = urljoin(host_scheme, self.json_url())
        if self.group is not None:
            sess1['group']          = self.group.json_dict(host_scheme)
            sess1['group_href']     = urljoin(host_scheme, self.group.json_url())
            if self.group.parent is not None:
                sess1['area']           = str(self.group.parent.acronym).upper()
            sess1['description']    = str(self.group.name)
            sess1['group_id']       = str(self.group.pk)
        reslist = []
        for r in self.resources.all():
            reslist.append(r.json_dict(host_scheme))
        sess1['resources']      = reslist
        sess1['session_id']     = str(self.pk)
        sess1['name']           = str(self.name)
        sess1['title']          = str(self.short_name)
        sess1['short_name']     = str(self.short_name)
        sess1['bof']            = str(self.is_bof())
        sess1['agenda_note']    = str(self.agenda_note)
        sess1['attendees']      = str(self.attendees)
        sess1['status']         = str(self.status)
        if self.comments is not None:
            sess1['comments']       = str(self.comments)
        sess1['requested_time'] = str(self.requested.strftime("%Y-%m-%d"))
        # the related person object sometimes does not exist in the dataset.
        try:
            if self.requested_by is not None:
                sess1['requested_by']   = str(self.requested_by)
        except Person.DoesNotExist:
            pass

        sess1['requested_duration']= "%.1f" % (float(self.requested_duration.seconds) / 3600)
        sess1['special_request'] = str(self.special_request_token)
        return sess1

    def agenda_text(self):
        doc = self.agenda()
        if doc:
            path = os.path.join(settings.AGENDA_PATH, self.meeting.number, "agenda", doc.external_url)
            if os.path.exists(path):
                with open(path) as f:
                    return f.read()
            else:
                return "No agenda file found"
        else:
            return "The agenda has not been uploaded yet."

    def type(self):
        if self.group.type.slug in [ "wg" ]:
            return "BOF" if self.group.state.slug in ["bof", "bof-conc"] else "WG"
        else:
            return ""

    def ical_status(self):
        if self.status.slug == 'canceled': # sic
            return "CANCELLED"
        elif (datetime.date.today() - self.meeting.date) > datetime.timedelta(days=5):
            # this is a bit simpleminded, better would be to look at the
            # time(s) of the timeslot(s) of the official meeting schedule.
            return "CONFIRMED"
        else:
            return "TENTATIVE"

    def agenda_file(self):
        if not hasattr(self, '_agenda_file'):
            self._agenda_file = ""

            docs = self.materials.filter(type="agenda", states__type="agenda", states__slug="active")
            if not docs:
                return ""

            # we use external_url at the moment, should probably regularize
            # the filenames to match the document name instead
            filename = docs[0].external_url
            self._agenda_file = "%s/agenda/%s" % (self.meeting.number, filename)
            
        return self._agenda_file
    def badness_test(self, num):
        from settings import BADNESS_CALC_LOG
        #sys.stdout.write("num: %u / BAD: %u\n" % (num, BADNESS_CALC_LOG))
        return BADNESS_CALC_LOG >= num

    def badness_log(self, num, msg):
        if self.badness_test(num):
            sys.stdout.write(msg)

    # this evaluates the current session based upon the constraints
    # given, in the context of the assignments in the array.
    #
    # MATH.
    #    each failed conflic3 is worth 1000   points
    #    each failed conflic2 is worth 10000  points
    #    each failed conflic1 is worth 100000 points
    #    being in a room too small than asked is worth 200,000 * (size/50)
    #    being in a room too big by more than 100 is worth 200,000 once.
    #    a conflict where AD must be in two places is worth 500,000.
    #    not being scheduled is worth  10,000,000 points
    #
    def badness(self, assignments):
        badness = 0

        if not (self.group in assignments):
            return 0

        conflicts = self.unique_constraints()

        if self.badness_test(2):
            self.badness_log(2, "badness for group: %s has %u constraints\n" % (self.group.acronym, len(conflicts)))
        from settings import BADNESS_UNPLACED, BADNESS_TOOSMALL_50, BADNESS_TOOSMALL_100, BADNESS_TOOBIG, BADNESS_MUCHTOOBIG
        count = 0
        myss_list = assignments[self.group]
        # for each constraint of this sessions' group, by group
        if len(myss_list)==0:
            if self.badness_test(2):
                self.badness_log(2, " 0group: %s is unplaced\n" % (self.group.acronym))
            return BADNESS_UNPLACED

        for myss in myss_list:
            if self.attendees is None or myss.timeslot is None or myss.timeslot.location.capacity is None:
                continue
            mismatch = self.attendees - myss.timeslot.location.capacity
            if mismatch > 100:
                # the room is too small by 100
                badness += BADNESS_TOOSMALL_100
            elif mismatch > 50:
                # the room is too small by 50
                badness += BADNESS_TOOSMALL_50
            elif mismatch < 50:
                # the room is too big by 50
                badness += BADNESS_TOOBIG
            elif mismatch < 100:
                # the room is too big by 100 (not intimate enough)
                badness += BADNESS_MUCHTOOBIG

        for group,constraint in conflicts.items():
            if group is None:
                # must not be a group constraint.
                continue
            count += 1
            # get the list of sessions for other group.
            sess_count = 0
            if group in assignments:
                sess_count = len(assignments[group])
            if self.badness_test(4):
                self.badness_log(4, "  [%u] 1group: %s session_count: %u\n" % (count, group.acronym, sess_count))

            # see if the other group which is conflicted, has an assignment,
            if group in assignments:
                other_sessions = assignments[group]
                # and if it does, see if any of it's sessions conflict with any of my sessions
                # (each group could have multiple slots)
                #if self.badness_test(4):
                #    self.badness_log(4, "  [%u] 9group: other sessions: %s\n" % (count, other_sessions))
                for ss in other_sessions:
                    # this causes additional database dips
                    #if self.badness_test(4):
                    #    self.badness_log(4, "  [%u] 9group: ss: %s %s\n" % (count, ss, ss.faked))
                    if ss.session is None:
                        continue
                    if ss.timeslot is None:
                        continue
                    if self.badness_test(3):
                        self.badness_log(3, "    [%u] 2group: %s vs ogroup: %s\n" % (count, self.group.acronym, ss.session.group.acronym))
                    if ss.session.group.acronym == self.group.acronym:
                        continue
                    if self.badness_test(3):
                        self.badness_log(3, "    [%u] 3group: %s sessions: %s\n" % (count, group.acronym, ss.timeslot.time))
                    # see if they are scheduled at the same time.
                    conflictbadness = 0
                    for myss in myss_list:
                        if myss.timeslot is None:
                            continue
                        if self.badness_test(3):
                            self.badness_log(3, "      [%u] 4group: %s my_sessions: %s vs %s\n" % (count, group.acronym, myss.timeslot.time, ss.timeslot.time))
                        if ss.timeslot.time == myss.timeslot.time:
                            newcost = constraint.constraint_cost()
                            if self.badness_test(2):
                                self.badness_log(2, "        [%u] 5group: %s conflict(%s): %s on %s cost %u\n" % (count, self.group.acronym, constraint.name_id, ss.session.group.acronym, ss.timeslot.time, newcost))
                            # yes accumulate badness.
                            conflictbadness += newcost
                    ss.badness = conflictbadness
                    ss.save()
                    badness += conflictbadness
        # done
        if self.badness_test(1):
            self.badness_log(1, "badgroup: %s badness = %u\n" % (self.group.acronym, badness))
        return badness

    def setup_conflicts(self):
        conflicts = self.unique_constraints()

        self.session_conflicts = []

        for group,constraint in conflicts.items():
            if group is None:
                # must not be a group constraint, people constraints TBD.
                continue

            # get the list of sessions for other group.
            for session in self.meeting.session_set.filter(group = group):
                # make a tuple...
                conflict = (session.pk, constraint)
                self.session_conflicts.append(conflict)

    # This evaluates the current session based upon the constraints
    # given.  The conflicts have first been shorted into an array (session_conflicts)
    # as a tuple, and include the constraint itself.
    #
    # While the conflicts are listed by group, the conflicts listed here
    # have been resolved into pk of session requests that will conflict.
    # This is to make comparison be a straight integer comparison.
    #
    # scheduleslot contains the list of sessions which are at the same time as
    # this item.
    #
    # timeslot is where this item has been scheduled.
    #
    # MATH.
    #    each failed conflic3 is worth 1000   points
    #    each failed conflic2 is worth 10000  points
    #    each failed conflic1 is worth 100000 points
    #    being in a room too small than asked is worth 200,000 * (size/50)
    #    being in a room too big by more than 100 is worth 200,000 once.
    #    a conflict where AD must be in two places is worth 500,000.
    #    not being scheduled is worth  10,000,000 points
    #
    def badness_fast(self, timeslot, scheduleslot, session_pk_list):
        from settings import BADNESS_UNPLACED, BADNESS_TOOSMALL_50, BADNESS_TOOSMALL_100, BADNESS_TOOBIG, BADNESS_MUCHTOOBIG

        badness = 0

        # see if item has not been scheduled
        if timeslot is None:
            return BADNESS_UNPLACED

        # see if this session is in too small a place.
        if self.attendees is not None and timeslot.location.capacity is not None:
            mismatch = self.attendees - timeslot.location.capacity
            if mismatch > 100:
                # the room is too small by 100
                badness += BADNESS_TOOSMALL_100
            elif mismatch > 50:
                # the room is too small by 50
                badness += BADNESS_TOOSMALL_50
            elif mismatch < 50:
                # the room is too big by 50
                badness += BADNESS_TOOBIG
            elif mismatch < 100:
                # the room is too big by 100 (not intimate enough)
                badness += BADNESS_MUCHTOOBIG

        # now go through scheduleslot items and see if any are conflicts
        # inner loop is the shorter one, usually max 8 rooms.
        for conflict in self.session_conflicts:
            for pkt in session_pk_list:
                pk = pkt[0]
                if pk == self.pk:          # ignore conflicts with self.
                    continue

                if conflict[0] == pk:
                    ss = pkt[1]
                    if ss.timeslot is not None and ss.timeslot.location == timeslot.location:
                        continue          # ignore conflicts when two sessions in the same room
                    constraint = conflict[1]
                    badness += constraint.constraint_cost()

        if self.badness_test(1):
            self.badness_log(1, "badgroup: %s badness = %u\n" % (self.group.acronym, badness))
        return badness

