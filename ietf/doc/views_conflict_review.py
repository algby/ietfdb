import datetime, os

from django import forms
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.http import HttpResponseRedirect, Http404
from django.core.urlresolvers import reverse
from django.template import RequestContext
from django.template.loader import render_to_string
from django.conf import settings

from ietf.doc.models import ( BallotDocEvent, BallotPositionDocEvent, DocAlias, DocEvent,
    Document, NewRevisionDocEvent, State, save_document_in_history )
from ietf.doc.utils import ( add_state_change_event, close_open_ballots,
    create_ballot_if_not_open, get_document_content, update_telechat )
from ietf.doc.mails import email_iana
from ietf.doc.forms import AdForm, NotifyForm
from ietf.group.models import Role, Group
from ietf.iesg.models import TelechatDate
from ietf.ietfauth.utils import has_role, role_required, is_authorized_in_doc_stream
from ietf.person.models import Person
from ietf.utils.mail import send_mail_preformatted
from ietf.utils.textupload import get_cleaned_text_file_content

class ChangeStateForm(forms.Form):
    review_state = forms.ModelChoiceField(State.objects.filter(used=True, type="conflrev"), label="Conflict review state", empty_label=None, required=True)
    comment = forms.CharField(widget=forms.Textarea, help_text="Optional comment for the review history", required=False)

@role_required("Area Director", "Secretariat")
def change_state(request, name, option=None):
    """Change state of an IESG review for IETF conflicts in other stream's documents, notifying parties as necessary
    and logging the change as a comment."""
    review = get_object_or_404(Document, type="conflrev", name=name)

    login = request.user.person

    if request.method == 'POST':
        form = ChangeStateForm(request.POST)
        if form.is_valid():
            clean = form.cleaned_data
            new_state = clean['review_state']
            comment = clean['comment'].rstrip()

            if comment:
                c = DocEvent(type="added_comment", doc=review, by=login)
                c.desc = comment
                c.save()

            prev_state = review.get_state()
            if new_state != prev_state:
                save_document_in_history(review)

                review.set_state(new_state)
                add_state_change_event(review, login, prev_state, new_state)

                review.time = datetime.datetime.now()
                review.save()

                if new_state.slug == "iesgeval":
                    create_ballot_if_not_open(review, login, "conflrev")
                    ballot = review.latest_event(BallotDocEvent, type="created_ballot")
                    if has_role(request.user, "Area Director") and not review.latest_event(BallotPositionDocEvent, ad=login, ballot=ballot, type="changed_ballot_position"):

                        # The AD putting a conflict review into iesgeval who doesn't already have a position is saying "yes"
                        pos = BallotPositionDocEvent(doc=review, by=login)
                        pos.ballot = ballot
                        pos.type = "changed_ballot_position"
                        pos.ad = login
                        pos.pos_id = "yes"
                        pos.desc = "[Ballot Position Update] New position, %s, has been recorded for %s" % (pos.pos.name, pos.ad.plain_name())
                        pos.save()
                    send_conflict_eval_email(request,review)


            return redirect('doc_view', name=review.name)
    else:
        s = review.get_state()
        init = dict(review_state=s.pk if s else None)
        form = ChangeStateForm(initial=init)

    return render_to_response('doc/change_state.html',
                              dict(form=form,
                                   doc=review,
                                   login=login,
                                   help_url=reverse('state_help', kwargs=dict(type="conflict-review")),
                                   ),
                              context_instance=RequestContext(request))

def send_conflict_review_started_email(request, review):
    msg = render_to_string("doc/conflict_review/review_started.txt",
                            dict(frm = settings.DEFAULT_FROM_EMAIL,
                                 by = request.user.person,
                                 review = review,
                                 reviewed_doc = review.relateddocument_set.get(relationship__slug='conflrev').target.document,
                                 review_url = settings.IDTRACKER_BASE_URL+review.get_absolute_url(),
                                 )
                           )
    if not has_role(request.user,"Secretariat"):
        send_mail_preformatted(request,msg)
    email_iana(request, 
               review.relateddocument_set.get(relationship__slug='conflrev').target.document,
               settings.IANA_EVAL_EMAIL,
                msg)

def send_conflict_eval_email(request,review):
    msg = render_to_string("doc/eval_email.txt",
                            dict(doc=review,
                                 doc_url = settings.IDTRACKER_BASE_URL+review.get_absolute_url(),
                                 )
                           )
    send_mail_preformatted(request,msg)
    email_iana(request, 
               review.relateddocument_set.get(relationship__slug='conflrev').target.document,
               settings.IANA_EVAL_EMAIL,
                msg)

class UploadForm(forms.Form):
    content = forms.CharField(widget=forms.Textarea, label="Conflict review response", help_text="Edit the conflict review response", required=False)
    txt = forms.FileField(label=".txt format", help_text="Or upload a .txt file", required=False)

    def clean_content(self):
        return self.cleaned_data["content"].replace("\r", "")

    def clean_txt(self):
        return get_cleaned_text_file_content(self.cleaned_data["txt"])

    def save(self, review):
        filename = os.path.join(settings.CONFLICT_REVIEW_PATH, '%s-%s.txt' % (review.canonical_name(), review.rev))
        with open(filename, 'wb') as destination:
            if self.cleaned_data['txt']:
                destination.write(self.cleaned_data['txt'])
            else:
                destination.write(self.cleaned_data['content'])

#This is very close to submit on charter - can we get better reuse?
@role_required('Area Director','Secretariat')
def submit(request, name):
    review = get_object_or_404(Document, type="conflrev", name=name)

    login = request.user.person

    path = os.path.join(settings.CONFLICT_REVIEW_PATH, '%s-%s.txt' % (review.canonical_name(), review.rev))
    not_uploaded_yet = review.rev == "00" and not os.path.exists(path)

    if not_uploaded_yet:
        # this case is special - the conflict review text document doesn't actually exist yet
        next_rev = review.rev
    else:
        next_rev = "%02d" % (int(review.rev)+1) 

    if request.method == 'POST':
        if "submit_response" in request.POST:
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                save_document_in_history(review)

                review.rev = next_rev

                e = NewRevisionDocEvent(doc=review, by=login, type="new_revision")
                e.desc = "New version available: <b>%s-%s.txt</b>" % (review.canonical_name(), review.rev)
                e.rev = review.rev
                e.save()
            
                # Save file on disk
                form.save(review)

                review.time = datetime.datetime.now()
                review.save()

                return redirect('doc_view', name=review.name)

        elif "reset_text" in request.POST:

            init = { "content": render_to_string("doc/conflict_review/review_choices.txt",dict())}
            form = UploadForm(initial=init)

        # Protect against handcrufted malicious posts
        else:
            form = None

    else:
        form = None

    if not form:
        init = { "content": ""}

        if not_uploaded_yet:
            init["content"] = render_to_string("doc/conflict_review/review_choices.txt",
                                                dict(),
                                              )
        else:
            filename = os.path.join(settings.CONFLICT_REVIEW_PATH, '%s-%s.txt' % (review.canonical_name(), review.rev))
            try:
                with open(filename, 'r') as f:
                    init["content"] = f.read()
            except IOError:
                pass

        form = UploadForm(initial=init)

    return render_to_response('doc/conflict_review/submit.html',
                              {'form': form,
                               'next_rev': next_rev,
                               'review' : review,
                               'conflictdoc' : review.relateddocument_set.get(relationship__slug='conflrev').target.document,
                              },
                              context_instance=RequestContext(request))


@role_required("Area Director", "Secretariat")
def edit_notices(request, name):
    """Change the set of email addresses document change notificaitions go to."""

    review = get_object_or_404(Document, type="conflrev", name=name)

    if request.method == 'POST':
        form = NotifyForm(request.POST)
        if form.is_valid():

            review.notify = form.cleaned_data['notify']
            review.save()

            login = request.user.person
            c = DocEvent(type="added_comment", doc=review, by=login)
            c.desc = "Notification list changed to : "+review.notify
            c.save()

            return redirect('doc_view', name=review.name)

    else:

        init = { "notify" : review.notify }
        form = NotifyForm(initial=init)

    conflictdoc = review.relateddocument_set.get(relationship__slug='conflrev').target.document
    titletext = 'the conflict review of %s-%s' % (conflictdoc.canonical_name(),conflictdoc.rev)
    return render_to_response('doc/notify.html',
                              {'form': form,
                               'doc': review,
                               'titletext' : titletext
                              },
                              context_instance = RequestContext(request))

@role_required("Area Director", "Secretariat")
def edit_ad(request, name):
    """Change the shepherding Area Director for this review."""

    review = get_object_or_404(Document, type="conflrev", name=name)

    if request.method == 'POST':
        form = AdForm(request.POST)
        if form.is_valid():

            review.ad = form.cleaned_data['ad']
            review.save()
    
            login = request.user.person
            c = DocEvent(type="added_comment", doc=review, by=login)
            c.desc = "Shepherding AD changed to "+review.ad.name
            c.save()

            return redirect('doc_view', name=review.name)

    else:
        init = { "ad" : review.ad_id }
        form = AdForm(initial=init)

    
    conflictdoc = review.relateddocument_set.get(relationship__slug='conflrev').target.document
    titletext = 'the conflict review of %s-%s' % (conflictdoc.canonical_name(),conflictdoc.rev)
    return render_to_response('doc/change_ad.html',
                              {'form': form,
                               'doc': review,
                               'titletext': titletext
                              },
                              context_instance = RequestContext(request))

def default_approval_text(review):

    filename = "%s-%s.txt" % (review.canonical_name(), review.rev)
    current_text = get_document_content(filename, os.path.join(settings.CONFLICT_REVIEW_PATH, filename), split=False, markup=False)

    conflictdoc = review.relateddocument_set.get(relationship__slug='conflrev').target.document
    if conflictdoc.stream_id=='ise':
         receiver = 'RFC-Editor'
    elif conflictdoc.stream_id=='irtf':
         receiver = 'IRTF'
    else:
         receiver = 'recipient'
    text = render_to_string("doc/conflict_review/approval_text.txt",
                               dict(review=review,
                                    review_url = settings.IDTRACKER_BASE_URL+review.get_absolute_url(),
                                    conflictdoc = conflictdoc,
                                    conflictdoc_url = settings.IDTRACKER_BASE_URL+conflictdoc.get_absolute_url(),
                                    receiver=receiver,
                                    approved_review = current_text
                                   )
                              )

    return text


class AnnouncementForm(forms.Form):
    announcement_text = forms.CharField(widget=forms.Textarea, label="IETF Conflict Review Announcement", help_text="Edit the announcement message", required=True)

@role_required("Secretariat")
def approve(request, name):
    """Approve this conflict review, setting the appropriate state and send the announcement to the right parties."""
    review = get_object_or_404(Document, type="conflrev", name=name)

    if review.get_state('conflrev').slug not in ('appr-reqnopub-pend','appr-noprob-pend'):
      raise Http404

    login = request.user.person

    if request.method == 'POST':

        form = AnnouncementForm(request.POST)

        if form.is_valid():
            prev_state = review.get_state()

            new_state_slug = 'appr-reqnopub-sent' if prev_state.slug == 'appr-reqnopub-pend' else 'appr-noprob-sent'
            new_state = State.objects.get(used=True, type="conflrev", slug=new_state_slug)
            save_document_in_history(review)

            review.set_state(new_state)
            add_state_change_event(review, login, prev_state, new_state)

            close_open_ballots(review, login)

            e = DocEvent(doc=review, by=login)
            e.type = "iesg_approved"
            e.desc = "IESG has approved the conflict review response"
            e.save()

            review.time = e.time
            review.save()

            # send announcement
            send_mail_preformatted(request, form.cleaned_data['announcement_text'])

            c = DocEvent(type="added_comment", doc=review, by=login)
            c.desc = "The following approval message was sent\n"+form.cleaned_data['announcement_text']
            c.save()

            return HttpResponseRedirect(review.get_absolute_url())

    else:

        init = { "announcement_text" : default_approval_text(review) }
        form = AnnouncementForm(initial=init)
    
    return render_to_response('doc/conflict_review/approve.html',
                              dict(
                                   review = review,
                                   conflictdoc = review.relateddocument_set.get(relationship__slug='conflrev').target.document,   
                                   form = form,
                                   ),
                              context_instance=RequestContext(request))

class SimpleStartReviewForm(forms.Form):
    notify = forms.CharField(max_length=255, label="Notice emails", help_text="Separate email addresses with commas", required=False)

class StartReviewForm(forms.Form):
    ad = forms.ModelChoiceField(Person.objects.filter(role__name="ad", role__group__state="active").order_by('name'), 
                                label="Shepherding AD", empty_label="(None)", required=True)
    create_in_state = forms.ModelChoiceField(State.objects.filter(used=True, type="conflrev", slug__in=("needshep", "adrev")), empty_label=None, required=False)
    notify = forms.CharField(max_length=255, label="Notice emails", help_text="Separate email addresses with commas", required=False)
    telechat_date = forms.TypedChoiceField(coerce=lambda x: datetime.datetime.strptime(x, '%Y-%m-%d').date(), empty_value=None, required=False, widget=forms.Select(attrs={'onchange':'make_bold()'}))

    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

        # telechat choices
        dates = [d.date for d in TelechatDate.objects.active().order_by('date')]
        #init = kwargs['initial']['telechat_date']
        #if init and init not in dates:
        #    dates.insert(0, init)

        self.fields['telechat_date'].choices = [("", "(not on agenda)")] + [(d, d.strftime("%Y-%m-%d")) for d in dates]

@role_required("Secretariat","IRTF Chair","ISE")
def start_review(request, name):
    if has_role(request.user,"Secretariat"):
        return start_review_as_secretariat(request,name)
    else:
        return start_review_as_stream_owner(request,name)

def start_review_sanity_check(request, name):
    doc_to_review = get_object_or_404(Document, type="draft", name=name)

    if ( not doc_to_review.stream_id in ('ise','irtf') )  or ( not is_authorized_in_doc_stream(request.user,doc_to_review)):
        raise Http404

    # sanity check that there's not already a conflict review document for this document
    if [ rel.source for alias in doc_to_review.docalias_set.all() for rel in alias.relateddocument_set.filter(relationship='conflrev') ]:
        raise Http404

    return doc_to_review

def build_notify_addresses(doc_to_review):
    # Take care to do the right thing during ietf chair and stream owner transitions
    notify_addresses = []
    notify_addresses.extend([x.person.formatted_email() for x in Role.objects.filter(group__acronym=doc_to_review.stream.slug,name='chair')])
    notify_addresses.append("%s@%s" % (doc_to_review.name, settings.TOOLS_SERVER))
    return notify_addresses

def build_conflict_review_document(login, doc_to_review, ad, notify, create_in_state):
    if doc_to_review.name.startswith('draft-'):
        review_name = 'conflict-review-'+doc_to_review.name[6:]
    else:
        # This is a failsafe - and might be treated better as an error
        review_name = 'conflict-review-'+doc_to_review.name

    iesg_group = Group.objects.get(acronym='iesg')

    conflict_review=Document( type_id = "conflrev",
                              title = "IETF conflict review for %s" % doc_to_review.name,
                              name = review_name,
                              rev = "00",
                              ad = ad,
                              notify = notify,
		              stream_id = 'ietf',
                              group = iesg_group,
                            )
    conflict_review.save()
    conflict_review.set_state(create_in_state)

    DocAlias.objects.create( name=review_name , document=conflict_review )
            
    conflict_review.relateddocument_set.create(target=DocAlias.objects.get(name=doc_to_review.name),relationship_id='conflrev')

    c = DocEvent(type="added_comment", doc=conflict_review, by=login)
    c.desc = "IETF conflict review requested"
    c.save()

    c = DocEvent(type="added_comment", doc=doc_to_review, by=login)
    # Is it really OK to put html tags into comment text?
    c.desc = 'IETF conflict review initiated - see <a href="%s">%s</a>' % (reverse('doc_view', kwargs={'name':conflict_review.name}),conflict_review.name)
    c.save()

    return conflict_review

def start_review_as_secretariat(request, name):
    """Start the conflict review process, setting the initial shepherding AD, and possibly putting the review on a telechat."""

    doc_to_review = start_review_sanity_check(request, name)

    login = request.user.person

    if request.method == 'POST':
        form = StartReviewForm(request.POST)
        if form.is_valid():
            conflict_review = build_conflict_review_document(login = login,
                                                             doc_to_review = doc_to_review, 
                                                             ad = form.cleaned_data['ad'],
                                                             notify = form.cleaned_data['notify'],
                                                             create_in_state = form.cleaned_data['create_in_state']
                                                            )

            tc_date = form.cleaned_data['telechat_date']
            if tc_date:
                update_telechat(request, conflict_review, login, tc_date)

            send_conflict_review_started_email(request, conflict_review)

            return HttpResponseRedirect(conflict_review.get_absolute_url())
    else: 
        notify_addresses = build_notify_addresses(doc_to_review)
        init = { 
                "ad" : Role.objects.filter(group__acronym='ietf',name='chair')[0].person.id,
                "notify" : u', '.join(notify_addresses),
               }
        form = StartReviewForm(initial=init)

    return render_to_response('doc/conflict_review/start.html',
                              {'form':   form,
                               'doc_to_review': doc_to_review,
                              },
                              context_instance = RequestContext(request))

def start_review_as_stream_owner(request, name):
    """Start the conflict review process using defaults for everything but notify and let the secretariat know"""

    doc_to_review = start_review_sanity_check(request, name)

    login = request.user.person

    if request.method == 'POST':
        form = SimpleStartReviewForm(request.POST)
        if form.is_valid():
            conflict_review = build_conflict_review_document(login = login,
                                                             doc_to_review = doc_to_review, 
                                                             ad = Role.objects.filter(group__acronym='ietf',name='chair')[0].person,
                                                             notify = form.cleaned_data['notify'],
                                                             create_in_state = State.objects.get(used=True,type='conflrev',slug='needshep')
                                                            )

            send_conflict_review_started_email(request, conflict_review)

            return HttpResponseRedirect(conflict_review.get_absolute_url())
    else: 
        notify_addresses = build_notify_addresses(doc_to_review)
        
        init = { 
                "notify" : u', '.join(notify_addresses),
               }
        form = SimpleStartReviewForm(initial=init)

    return render_to_response('doc/conflict_review/start.html',
                              {'form':   form,
                               'doc_to_review': doc_to_review,
                              },
                              context_instance = RequestContext(request))
