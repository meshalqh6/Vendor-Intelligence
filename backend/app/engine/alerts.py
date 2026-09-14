"""
Proactive alerts / watchlist, computed deterministically from source rows:
documents expiring soon, recorded HSE incidents, overdue CAPAs, and vendors
sitting just under a classification threshold (boundary cases).
"""

from datetime import date, timedelta

from .scoring import list_scorecards

EXPIRY_WINDOW_DAYS = 30
BOUNDARY_MARGIN = 1.0  # flag vendors within this many points below a threshold


def _d(s):
    return date.fromisoformat(s) if s else None


def build_alerts(store):
    as_of = store.as_of
    horizon = as_of + timedelta(days=EXPIRY_WINDOW_DAYS)
    vendors = {v["vendor_code"]: v for v in store.vendors()}

    expiring, expired_mandatory, hse, overdue = [], [], [], []
    for vc, v in vendors.items():
        for doc in store.compliance_docs(vc):
            exp = _d(doc["expiry_date"])
            if as_of <= exp <= horizon:
                expiring.append({"vendor_code": vc, "name": v["name"],
                                 "doc_id": doc["doc_id"], "doc_type": doc["doc_type"],
                                 "expiry_date": doc["expiry_date"],
                                 "days_left": (exp - as_of).days,
                                 "mandatory": bool(doc["mandatory_flag"])})
            elif exp < as_of and doc["mandatory_flag"]:
                expired_mandatory.append({"vendor_code": vc, "name": v["name"],
                                          "doc_id": doc["doc_id"], "doc_type": doc["doc_type"],
                                          "expiry_date": doc["expiry_date"]})
        for h in store.hse_incidents(vc):
            hse.append({"vendor_code": vc, "name": v["name"], "incident_id": h["incident_id"],
                        "incident_date": h["incident_date"], "severity": h["severity"],
                        "description": h["description"]})
        for n in store.ncr_capa(vc):
            due = _d(n["due_date"])
            if not n["closed_date"] and due and (as_of - due).days > 0:
                overdue.append({"vendor_code": vc, "name": v["name"],
                                "record_id": n["record_id"], "type": n["type"],
                                "severity": n["severity"], "due_date": n["due_date"],
                                "days_overdue": (as_of - due).days})

    # Boundary cases: final score just below a classification threshold.
    thresholds = [c["min_score"] for c in store.scoring["classification"] if c["min_score"] > 0]
    boundary = []
    for sc in list_scorecards(store, include_sources=False):
        for t in thresholds:
            if 0 < (t - sc["final_score"]) <= BOUNDARY_MARGIN:
                boundary.append({"vendor_code": sc["vendor_code"], "name": sc["name"],
                                 "final_score": sc["final_score"], "threshold": t,
                                 "gap": round(t - sc["final_score"], 2),
                                 "classification": sc["classification"]})
    expiring.sort(key=lambda x: x["days_left"])
    overdue.sort(key=lambda x: -x["days_overdue"])
    return {
        "expiring_documents": expiring,
        "expired_mandatory_documents": expired_mandatory,
        "hse_incidents": hse,
        "overdue_capa": overdue,
        "boundary_cases": boundary,
        "as_of": as_of.isoformat(),
    }
