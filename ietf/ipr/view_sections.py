# Copyright The IETF Trust 2007, All Rights Reserved

section_table = {
                "specific": {   "title": True,
                                "specific": 1, "generic": 0, "third_party": 0, 
                                "legacy_intro": False, "new_intro": True,  "form_intro": False,
                                "holder": True, "holder_contact": True, "ietf_contact": True,
                                "ietf_doc": True, "patent_info": True, "licensing": True,
                                "submitter": True, "notes": True, "form_submit": False,
                                "disclosure_type": "Specific IPR Disclosures", "form_legend": False, 
                                "per_rfc_disclosure": True, "also_specific": False,
                            },
                "generic": {   "title": True,
                                "specific": 0, "generic": 1, "third_party": 0, 
                                "legacy_intro": False, "new_intro": True,  "form_intro": False,
                                "holder": True, "holder_contact": True, "ietf_contact": False,
                                "ietf_doc": False, "patent_info": True, "licensing": True,
                                "submitter": True, "notes": True, "form_submit": False,
                                "disclosure_type": "Generic IPR Disclosures", "form_legend": False, 
                                "per_rfc_disclosure": False, "also_specific": True,
                            },
                "third-party": {"title": True,
                                "specific": 0, "generic": 0, "third_party": 1, 
                                "legacy_intro": False, "new_intro": True,  "form_intro": False,
                                "holder": True, "holder_contact": False, "ietf_contact": True,
                                "ietf_doc": True, "patent_info": True, "licensing": False,
                                "submitter": False, "notes": False, "form_submit": False,
                                "disclosure_type": "Notification", "form_legend": False, 
                                "per_rfc_disclosure": False, "also_specific": False,
                            },
                "legacy":   {   "title": True, "legacy": True,
                                "legacy_intro": True, "new_intro": False,  "form_intro": False,
                                "holder": True, "holder_contact": True, "ietf_contact": False,
                                "ietf_doc": True, "patent_info": False, "licensing": False,
                                "submitter": False, "notes": False, "form_submit": False,
                                "disclosure_type": "Legacy", "form_legend": False, 
                                "per_rfc_disclosure": False, "also_specific": False,
                            },
            }

def section_list_for_ipr(ipr):
    if   ipr.legacy_url_0:
        return section_table["legacy"]
    elif ipr.generic:
        #assert not ipr.third_party
        return section_table["generic"]
    elif ipr.third_party:
        return section_table["third-party"]
    else:
        return section_table["specific"]

