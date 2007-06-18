import re
import django.utils.html
from django.shortcuts import render_to_response as render
from ietf.idtracker.models import IETFWG, InternetDraft, Rfc
from ietf.ipr.models import IprRfc, IprDraft
from ietf.ipr.related import related_docs
from ietf.utils import log


def search(request, type="", q="", id=""):
    wgs = IETFWG.objects.filter(group_type__group_type_id=1).exclude(group_acronym__acronym='2000').select_related().order_by('acronym.acronym')
    args = request.REQUEST.items()
    if args:
        for key, value in args:
            if key == "option":
                type = value
            if re.match(".*search", key):
                q = value
            if re.match(".*id", key):
                id = value
        if type and q or id:
            log("Got query: type=%s, q=%s, id=%s" % (type, q, id))
            if type in ["document_search", "rfc_search"]:
                if type == "document_search":
                    if q:
                        start = InternetDraft.objects.filter(filename__contains=q)
                    if id:
                        start = InternetDraft.objects.filter(id_document_tag=id)
                if type == "rfc_search":
                    if q:
                        start = Rfc.objects.filter(rfc_number=q)
                if start.count() == 1:
                    first = start[0]
                    # get all related drafts, then search for IPRs on all

                    docs = related_docs(first, [])
                    #docs = get_doclist.get_doclist(first)
                    iprs = []
                    for doc in docs:
                        if isinstance(doc, InternetDraft):
                            disclosures = [ item.ipr for item in IprDraft.objects.filter(document=doc, ipr__status__in=[1,3]) ]
                        elif isinstance(doc, Rfc):
                            disclosures = [ item.ipr for item in IprRfc.objects.filter(document=doc, ipr__status__in=[1,3]) ]
                        else:
                            raise ValueError("Doc type is neither draft nor rfc: %s" % doc)
                        if disclosures:
                            doc.iprs = disclosures
                            iprs += disclosures
                    iprs = list(set(iprs))
                    return render("ipr/search_doc_result.html", {"first": first, "iprs": iprs, "docs": docs})
                elif start.count():
                    return render("ipr/search_doc_list.html", {"docs": start })
                else:
                    raise ValueError("Missing or malformed search parameters, or internal error")
            elif type == "patent_search":
                pass
            elif type == "patent_info_search":
                pass
            elif type == "wg_search":
                pass
            elif type == "title_search":
                pass
            elif type == "ip_title_search":
                pass
            else:
                raise ValueError("Unexpected search type in IPR query: %s" % type)
        return django.http.HttpResponseRedirect(request.path)
    return render("ipr/search.html", {"wgs": wgs})