"""
Deterministic KPI scoring, classification and scorecard assembly.

This is the auditable core the demo must prove: every number here is computed
from source rows by fixed arithmetic and config thresholds — no model, no
randomness. Each KPI reports the exact source record IDs that fed it.
"""

from datetime import date, datetime

from .actions import next_action
from .risk import classify_risk, detect_triggers


def _d(s):
    return date.fromisoformat(s) if s else None


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def _round(x):
    return round(x, 2)


# ---------------------------------------------------------------------------
# Banding helpers driven by config
# ---------------------------------------------------------------------------
def _delivery_band(store, days_late):
    for b in store.scoring["delivery_banding"]:
        if b["max_days"] is None or days_late <= b["max_days"]:
            return b["band"], b["score"]
    last = store.scoring["delivery_banding"][-1]
    return last["band"], last["score"]


def _ncr_band(store, days_late):
    for b in store.scoring["ncr_capa_banding"]:
        if b["max_days_late"] is None or days_late <= b["max_days_late"]:
            return b["grade"], b["score"]
    last = store.scoring["ncr_capa_banding"][-1]
    return last["grade"], last["score"]


def _rating_grade(store, value):
    for r in store.scoring["rating_scale"]:
        if value >= r["min"]:
            return r["grade"]
    return "D"


def _classify(store, score):
    for c in store.scoring["classification"]:
        if score >= c["min_score"]:
            return c["label"]
    return store.scoring["classification"][-1]["label"]


# ---------------------------------------------------------------------------
# Individual KPI computations -> (value, source_ids, detail)
# ---------------------------------------------------------------------------
def _kpi_quality(store, lots):
    if not lots:
        return 100.0, [], "No inspection data (defaults to 100)."
    total = sum(l["lot_qty"] for l in lots)
    accepted = sum(l["accepted_qty"] for l in lots)
    value = (accepted / total * 100) if total else 100.0
    detail = f"{accepted:.0f} accepted of {total:.0f} lot qty across {len(lots)} lots."
    return value, [l["lot_number"] for l in lots], detail


def _kpi_delivery(store, deliveries):
    if not deliveries:
        return 100.0, [], "No deliveries (defaults to 100)."
    scores, counts = [], {}
    for dvy in deliveries:
        days = (_d(dvy["posting_date"]) - _d(dvy["requested_delivery_date"])).days
        band, sc = _delivery_band(store, days)
        scores.append(sc)
        counts[band] = counts.get(band, 0) + 1
    value = sum(scores) / len(scores)
    detail = ", ".join(f"{k}: {v}" for k, v in counts.items())
    return value, [d["grn_number"] for d in deliveries], detail


def _kpi_compliance(store, docs):
    if not docs:
        return 100.0, [], "No documents on file (defaults to 100)."
    valid = [d for d in docs if _d(d["expiry_date"]) >= store.as_of]
    value = len(valid) / len(docs) * 100
    detail = f"{len(valid)} valid of {len(docs)} required documents."
    return value, [d["doc_id"] for d in docs], detail


def _kpi_ncr(store, records):
    """Average of per-record closure bands. Open-but-overdue records score as
    grade E (realized failure); open-not-yet-due records are excluded."""
    scored, ids = [], []
    for n in records:
        due = _d(n["due_date"])
        if n["closed_date"]:
            days_late = (_d(n["closed_date"]) - due).days
            _, sc = _ncr_band(store, days_late)
            scored.append(sc)
            ids.append(n["record_id"])
        elif due and (store.as_of - due).days > 0:  # open and past due
            _, sc = _ncr_band(store, (store.as_of - due).days)
            scored.append(sc)
            ids.append(n["record_id"])
        # open-not-yet-due => no closure to band, skip
    if not scored:
        return 100.0, ids, "No closed/overdue records (defaults to 100)."
    value = sum(scored) / len(scored)
    return value, ids, f"{len(scored)} banded records, average grade score {value:.1f}."


def _kpi_sla(store, wos):
    if not wos:
        return 100.0, [], "No work orders (defaults to 100)."
    within = 0
    for w in wos:
        if w["actual_completion"]:
            hours = (_dt(w["actual_completion"]) - _dt(w["planned_completion"])).total_seconds() / 3600
            if hours <= w["sla_hours"]:
                within += 1
    value = within / len(wos) * 100
    return value, [w["wo_number"] for w in wos], f"{within} of {len(wos)} work orders within SLA."


def _kpi_rating(store, entries, field, label):
    if not entries:
        return 100.0, [], f"No {label} ratings (defaults to 100)."
    vals = [e[field] for e in entries]
    value = sum(vals) / len(vals)
    return value, [e["ses_number"] for e in entries], \
        f"Average {label} rating {value:.1f} (grade {_rating_grade(store, value)}) over {len(vals)} entries."


def _kpi_capa(store, records):
    if not records:
        return 100.0, [], "No CAPAs (defaults to 100)."
    within = 0
    for n in records:
        if n["closed_date"] and (_d(n["closed_date"]) - _d(n["due_date"])).days <= 0:
            within += 1
    value = within / len(records) * 100
    return value, [n["record_id"] for n in records], \
        f"{within} of {len(records)} CAPAs closed within due date."


# ---------------------------------------------------------------------------
# Trend (quarterly) for the vendor's headline quality metric
# ---------------------------------------------------------------------------
def _quarter(iso):
    dt = _d(iso)
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def _supplier_trend(lots):
    buckets = {}
    for l in lots:
        q = _quarter(l["ud_date"])
        b = buckets.setdefault(q, [0, 0])
        b[0] += l["accepted_qty"]
        b[1] += l["lot_qty"]
    return [{"period": q, "value": _round(a / t * 100) if t else 100.0}
            for q, (a, t) in sorted(buckets.items())]


def _service_trend(entries):
    buckets = {}
    for e in entries:
        q = _quarter(e["service_date"])
        b = buckets.setdefault(q, [])
        b.append(e["quality_rating"])
    return [{"period": q, "value": _round(sum(v) / len(v))}
            for q, v in sorted(buckets.items())]


# ---------------------------------------------------------------------------
# Scorecard assembly
# ---------------------------------------------------------------------------
def _kpi(key, cfg_entry, value, ids, detail):
    weight = cfg_entry["weight"]
    return {
        "key": key,
        "label": cfg_entry["label"],
        "weight": weight,
        "value": _round(value),
        "contribution": _round(weight * value),
        "detail": detail,
        "source_record_ids": ids,
    }


def build_scorecard(store, vendor_code, include_sources=True):
    vendor = store.vendor(vendor_code)
    if not vendor:
        return None

    ncr_rows = store.ncr_capa(vendor_code)
    doc_rows = store.compliance_docs(vendor_code)
    hse_rows = store.hse_incidents(vendor_code)

    if vendor["type"] == "supplier":
        cfg = store.scoring["supplier_kpis"]
        lots = store.inspection_lots(vendor_code)
        deliveries = store.deliveries(vendor_code)
        q_v, q_id, q_d = _kpi_quality(store, lots)
        d_v, d_id, d_d = _kpi_delivery(store, deliveries)
        c_v, c_id, c_d = _kpi_compliance(store, doc_rows)
        n_v, n_id, n_d = _kpi_ncr(store, ncr_rows)
        kpis = [
            _kpi("quality", cfg["quality"], q_v, q_id, q_d),
            _kpi("delivery", cfg["delivery"], d_v, d_id, d_d),
            _kpi("compliance", cfg["compliance"], c_v, c_id, c_d),
            _kpi("ncr_capa", cfg["ncr_capa"], n_v, n_id, n_d),
        ]
        trend = _supplier_trend(lots)
    else:
        cfg = store.scoring["service_provider_kpis"]
        wos = store.work_orders(vendor_code)
        entries = store.service_entries(vendor_code)
        sla_v, sla_id, sla_d = _kpi_sla(store, wos)
        sq_v, sq_id, sq_d = _kpi_rating(store, entries, "quality_rating", "service quality")
        rt_v, rt_id, rt_d = _kpi_rating(store, entries, "response_rating", "response time")
        hse_v, hse_id, hse_d = _kpi_rating(store, entries, "hse_rating", "HSE")
        c_v, c_id, c_d = _kpi_compliance(store, doc_rows)
        capa_v, capa_id, capa_d = _kpi_capa(store, ncr_rows)
        kpis = [
            _kpi("sla", cfg["sla"], sla_v, sla_id, sla_d),
            _kpi("service_quality", cfg["service_quality"], sq_v, sq_id, sq_d),
            _kpi("response_time", cfg["response_time"], rt_v, rt_id, rt_d),
            _kpi("hse", cfg["hse"], hse_v, hse_id, hse_d),
            _kpi("compliance_docs", cfg["compliance_docs"], c_v, c_id, c_d),
            _kpi("capa", cfg["capa"], capa_v, capa_id, capa_d),
        ]
        trend = _service_trend(entries)

    final_score = _round(sum(k["contribution"] for k in kpis))
    classification = _classify(store, final_score)
    triggers = detect_triggers(store, vendor, ncr_rows, doc_rows, hse_rows)
    risk = classify_risk(store, final_score, triggers)
    action = next_action(store, classification, risk)

    if not include_sources:
        for k in kpis:
            k.pop("source_record_ids", None)

    return {
        "vendor_code": vendor["vendor_code"],
        "name": vendor["name"],
        "type": vendor["type"],
        "category": vendor["category"],
        "country": vendor["country"],
        "status": vendor["status"],
        "blocked_flag": vendor["blocked_flag"],
        "kpis": kpis,
        "final_score": final_score,
        "classification": classification,
        "risk": risk,
        "risk_triggers": triggers,
        "next_action": action,
        "trend": trend,
    }


def list_scorecards(store, include_sources=False):
    return [build_scorecard(store, v["vendor_code"], include_sources=include_sources)
            for v in store.vendors()]
