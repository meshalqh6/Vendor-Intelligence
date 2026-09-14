"""
Deterministic engine tests — the "defensible numbers" proof.

Each planted narrative vendor must produce an exact score / classification /
risk. If the scoring rules or config change, these break loudly.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.engine import build_scorecard, build_alerts  # noqa: E402
from app.engine.store import Store  # noqa: E402


@pytest.fixture(scope="module")
def store():
    return Store()


def kpi(card, key):
    return next(k for k in card["kpis"] if k["key"] == key)


def trigger_codes(card):
    return {t["code"] for t in card["risk_triggers"]}


# ---------------------------------------------------------------------------
# Config sanity
# ---------------------------------------------------------------------------
def test_weights_sum_to_one(store):
    for group in ("supplier_kpis", "service_provider_kpis"):
        total = sum(k["weight"] for k in store.scoring[group].values())
        assert round(total, 6) == 1.0, group


# ---------------------------------------------------------------------------
# Narrative 1: Al Wajba Packaging — Preferred / High Risk via expired mandatory cert
# ---------------------------------------------------------------------------
def test_al_wajba_preferred_high_risk(store):
    c = build_scorecard(store, "SUP-1001")
    assert c["name"] == "Al Wajba Packaging"
    assert kpi(c, "quality")["value"] == 100.0
    assert kpi(c, "delivery")["value"] == 100.0
    assert kpi(c, "compliance")["value"] == 80.0
    assert kpi(c, "ncr_capa")["value"] == 100.0
    assert c["final_score"] == 96.0
    assert c["classification"] == "Preferred"
    assert c["risk"] == "High"                       # hard override
    assert "expired_mandatory_document" in trigger_codes(c)


# ---------------------------------------------------------------------------
# Narrative 2: Almarai — Preferred / High Risk via open critical NCR
# ---------------------------------------------------------------------------
def test_almarai_preferred_high_risk(store):
    c = build_scorecard(store, "SUP-1002")
    assert c["final_score"] == 100.0
    assert c["classification"] == "Preferred"
    assert c["risk"] == "High"
    assert "critical_ncr_open" in trigger_codes(c)


# ---------------------------------------------------------------------------
# Narrative 3: Bayara — the 74.6% boundary, just under Conditional (75)
# ---------------------------------------------------------------------------
def test_bayara_boundary(store):
    c = build_scorecard(store, "SUP-1003")
    assert kpi(c, "quality")["value"] == 76.0
    assert kpi(c, "delivery")["value"] == 72.0
    assert kpi(c, "compliance")["value"] == 75.0
    assert kpi(c, "ncr_capa")["value"] == 75.0
    assert c["final_score"] == 74.6
    assert c["classification"] == "Reassessment Required"   # 0.4 under Conditional
    assert c["risk"] == "Moderate"
    assert c["risk_triggers"] == []


# ---------------------------------------------------------------------------
# Narrative 5: Doha Calibration Services — Conditional / High; closing overdue
# CAPA -> Approved (what-if crosses a band AND clears the risk override)
# ---------------------------------------------------------------------------
def test_doha_overdue_capa_whatif(store):
    c = build_scorecard(store, "SRV-2003")
    assert c["type"] == "service_provider"
    assert c["final_score"] == 84.8
    assert c["classification"] == "Conditional"
    assert c["risk"] == "High"
    assert "capa_overdue_beyond_limit" in trigger_codes(c)
    # What-if: closing the overdue CAPA on time lifts the CAPA KPI to 100.
    capa = kpi(c, "capa")
    whatif = round(c["final_score"] - capa["contribution"] + 0.05 * 100, 2)
    assert whatif >= 85.0  # crosses into Approved


# ---------------------------------------------------------------------------
# Narrative 6: Emirates Facilities — service provider, HSE incident -> High
# ---------------------------------------------------------------------------
def test_emirates_hse_escalation(store):
    c = build_scorecard(store, "SRV-2001")
    assert c["type"] == "service_provider"
    assert c["risk"] == "High"
    assert "hse_incident" in trigger_codes(c)


# ---------------------------------------------------------------------------
# Narrative 7: Nadec — 3 documents expiring within 30 days -> proactive alert
# ---------------------------------------------------------------------------
def test_nadec_expiring_documents(store):
    alerts = build_alerts(store)
    nadec = [a for a in alerts["expiring_documents"] if a["vendor_code"] == "SRV-2002"]
    assert len(nadec) == 3
    assert all(0 <= a["days_left"] <= 30 for a in nadec)


# ---------------------------------------------------------------------------
# Global invariants
# ---------------------------------------------------------------------------
def test_all_vendors_scored(store):
    for v in store.vendors():
        c = build_scorecard(store, v["vendor_code"])
        assert 0 <= c["final_score"] <= 100
        assert c["classification"] in {"Preferred", "Approved", "Conditional",
                                       "Reassessment Required"}
        assert c["risk"] in {"Low", "Medium", "Moderate", "High"}


def test_at_least_two_preferred_high_risk(store):
    n = 0
    for v in store.vendors():
        c = build_scorecard(store, v["vendor_code"])
        if c["classification"] == "Preferred" and c["risk"] == "High":
            n += 1
    assert n >= 2
