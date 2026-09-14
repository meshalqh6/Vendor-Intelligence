"""
Risk classification with the High-Risk HARD OVERRIDE.

Risk is independent of the weighted score. Any critical trigger forces High
regardless of score (e.g. 97% + expired ISO certificate => Preferred / High
Risk). Every trigger carries the source record IDs that fired it, so the answer
is fully traceable.
"""

from datetime import date


def _d(s):
    return date.fromisoformat(s) if s else None


def detect_triggers(store, vendor, ncr_rows, doc_rows, hse_rows):
    """Return the list of fired High-Risk triggers with their evidence."""
    as_of = store.as_of
    limit = store.scoring["capa_overdue_trigger_days"]
    triggers = []

    expired_mandatory = [d for d in doc_rows
                         if d["mandatory_flag"] and _d(d["expiry_date"]) < as_of]
    if expired_mandatory:
        triggers.append({
            "code": "expired_mandatory_document",
            "label": "Expired mandatory document",
            "detail": ", ".join(f'{d["doc_type"]} (expired {d["expiry_date"]})'
                                 for d in expired_mandatory),
            "source_record_ids": [d["doc_id"] for d in expired_mandatory],
        })

    critical_open = [n for n in ncr_rows
                     if n["severity"] == "Critical" and not n["closed_date"]]
    if critical_open:
        triggers.append({
            "code": "critical_ncr_open",
            "label": "Critical NCR open",
            "detail": ", ".join(f'{n["record_id"]} raised {n["raised_date"]}'
                                 for n in critical_open),
            "source_record_ids": [n["record_id"] for n in critical_open],
        })

    overdue = [n for n in ncr_rows
               if not n["closed_date"] and _d(n["due_date"])
               and (as_of - _d(n["due_date"])).days > limit]
    if overdue:
        triggers.append({
            "code": "capa_overdue_beyond_limit",
            "label": f"CAPA/NCR overdue beyond {limit} days",
            "detail": ", ".join(
                f'{n["record_id"]} due {n["due_date"]} '
                f'({(as_of - _d(n["due_date"])).days} days overdue)' for n in overdue),
            "source_record_ids": [n["record_id"] for n in overdue],
        })

    if hse_rows:
        triggers.append({
            "code": "hse_incident",
            "label": "HSE incident recorded",
            "detail": "; ".join(f'{h["incident_id"]}: {h["severity"]} on {h["incident_date"]}'
                                for h in hse_rows),
            "source_record_ids": [h["incident_id"] for h in hse_rows],
        })

    if vendor["blocked_flag"] or vendor["status"] in ("Blocked", "Suspended"):
        triggers.append({
            "code": "vendor_blocked_or_suspended",
            "label": "Vendor blocked/suspended",
            "detail": f'Status: {vendor["status"]}',
            "source_record_ids": [vendor["vendor_code"]],
        })

    return triggers


def classify_risk(store, score, triggers):
    """Base risk from score, then apply the High-Risk hard override."""
    if triggers:
        return "High"
    cfg = store.scoring["risk"]
    if score >= cfg["low"]["min_score"]:
        return "Low"
    if score >= cfg["medium"]["min_score"]:
        return "Medium"
    return "Moderate"  # covers moderate band and the sub-75 reassessment range
