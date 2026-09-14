"""
VendorLens synthetic data generator.

Produces data/vendorlens.db — a SQLite database shaped like realistic SAP
(MM/QM/PM/FI/EHS/DMS) + ETQ (NCR/CAPA) extracts for ~40 Gulf-region dairy/FMCG
vendors over 24 months. The random seed is fixed, so every run is identical.

Named "narrative" vendors are hand-built so the deterministic rules engine
produces the exact scenarios in docs/DEMO_SCRIPT.md. Filler vendors are
generated from per-tier profiles for a realistic spread.

Run:  python scripts/generate_data.py
"""

import os
import random
import sqlite3
from datetime import date, datetime, time, timedelta

# Fixed reference date ("today") and fixed seed => identical DB every run.
AS_OF = date(2026, 8, 1)
HISTORY_START = date(2024, 8, 1)
random.seed(20260801)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vendorlens.db")

# ---------------------------------------------------------------------------
# In-memory row buffers, flushed to SQLite at the end.
# ---------------------------------------------------------------------------
vendors = []
purchase_orders = []
goods_receipts = []
inspection_lots = []
work_orders = []
service_entries = []
ncr_capa = []
compliance_docs = []
hse_incidents = []

_counters = {"po": 0, "grn": 0, "lot": 0, "wo": 0, "ses": 0, "ncr": 0, "doc": 0, "inc": 0}


def _seq(kind, prefix):
    _counters[kind] += 1
    return f"{prefix}{_counters[kind]:06d}"


def rand_date(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


# ---------------------------------------------------------------------------
# Reusable record builders (used by both narrative and filler vendors)
# ---------------------------------------------------------------------------
MATERIALS = ["RM-MILK-RAW", "RM-SUGAR", "PKG-CARTON", "PKG-PET", "RM-CULTURE",
             "RM-FLAVOR", "RM-STABILIZER", "PKG-LABEL", "RM-COCOA", "RM-SALT"]
DOC_TYPES_MANDATORY = ["ISO 22000:2018", "FSSC 22000 v6", "Halal Certificate",
                       "ISO 45001:2018"]
DOC_TYPES_OPTIONAL = ["Trade License", "Public Liability Insurance",
                      "Supplier Self-Assessment"]
ORDER_TYPES = ["Preventive Maintenance", "Corrective Maintenance",
               "Calibration", "Cleaning & Sanitation", "Pest Control"]
END_USERS = ["Plant Ops", "QA Lab", "Warehouse", "Utilities", "Facilities"]


def add_supplier_delivery(vc, po_date, lead_days, delay_days, qty, accept_qty):
    """One PO -> GRN -> inspection lot. delay_days = GRN posting vs requested date."""
    po = _seq("po", "PO")
    req = po_date + timedelta(days=lead_days)
    posting = req + timedelta(days=delay_days)
    purchase_orders.append((po, vc, random.choice(MATERIALS), po_date.isoformat(),
                            req.isoformat(), qty, round(qty * random.uniform(3, 40), 2)))
    grn = _seq("grn", "GRN")
    goods_receipts.append((grn, po, posting.isoformat(), qty))
    lot = _seq("lot", "LOT")
    rejected = qty - accept_qty
    ud = "A" if rejected == 0 else ("R" if accept_qty == 0 else "P")  # accept/reject/partial
    inspection_lots.append((lot, grn, qty, accept_qty, rejected, ud,
                            (posting + timedelta(days=2)).isoformat()))


def add_ncr(vc, raised, due, closed, severity, status, source="ETQ", typ="NCR"):
    ncr_capa.append((_seq("ncr", "NCR"), vc, source, typ, severity,
                     raised.isoformat(), due.isoformat(),
                     closed.isoformat() if closed else None, status))


def add_doc(vc, doc_type, issue, expiry, mandatory):
    compliance_docs.append((_seq("doc", "DOC"), vc, doc_type, issue.isoformat(),
                            expiry.isoformat(), 1 if mandatory else 0))


def add_work_order(vc, planned_date, completion_hours, sla_hours):
    """planned_date is a date; completion_hours is hours from planned start to actual finish."""
    planned = datetime.combine(planned_date, time(8, 0))
    actual = planned + timedelta(hours=completion_hours)
    work_orders.append((_seq("wo", "WO"), vc, random.choice(ORDER_TYPES),
                        planned.isoformat(), actual.isoformat(), sla_hours))


def add_service_entry(vc, sdate, quality, response, hse):
    service_entries.append((_seq("ses", "SES"), vc, sdate.isoformat(),
                            quality, response, hse, random.choice(END_USERS)))


def add_hse_incident(vc, idate, severity, desc):
    hse_incidents.append((_seq("inc", "INC"), vc, idate.isoformat(), severity, desc))


# ---------------------------------------------------------------------------
# Delay/accept helpers keyed to target bands
# ---------------------------------------------------------------------------
DELAY_FOR_BAND = {"OnTime": 0, "Minor": 18, "Major": 25, "Critical": 35}


def full_valid_docs(vc, count=5, mandatory_first=True):
    """All docs valid (expiry well in the future)."""
    types = (DOC_TYPES_MANDATORY + DOC_TYPES_OPTIONAL)[:count]
    for i, dt in enumerate(types):
        mandatory = dt in DOC_TYPES_MANDATORY
        add_doc(vc, dt, AS_OF - timedelta(days=400),
                AS_OF + timedelta(days=random.randint(200, 700)), mandatory)


# ===========================================================================
# NARRATIVE VENDORS — hand-built to yield exact engine outputs.
# ===========================================================================
def build_narrative():
    # --- 1. Al Wajba Packaging — Preferred / High Risk (expired mandatory cert)
    # Q=100, D=100, N=100 (no NCRs), C=80 (4 of 5 docs valid, ISO 22000 EXPIRED).
    # final = .35*100 + .25*100 + .20*80 + .20*100 = 96.0 -> Preferred.
    vc = "SUP-1001"
    vendors.append((vc, "Al Wajba Packaging", "Packaging", "supplier", "Qatar", "Active", 0))
    d = HISTORY_START
    for _ in range(20):
        add_supplier_delivery(vc, d, 10, DELAY_FOR_BAND["OnTime"], 1000, 1000)  # 100% accept, on-time
        d += timedelta(days=30)
    add_doc(vc, "ISO 22000:2018", AS_OF - timedelta(days=800),
            AS_OF - timedelta(days=40), True)     # EXPIRED mandatory -> High trigger
    add_doc(vc, "FSSC 22000 v6", AS_OF - timedelta(days=200), AS_OF + timedelta(days=400), True)
    add_doc(vc, "ISO 45001:2018", AS_OF - timedelta(days=200), AS_OF + timedelta(days=450), True)
    add_doc(vc, "Halal Certificate", AS_OF - timedelta(days=100), AS_OF + timedelta(days=500), True)
    add_doc(vc, "Trade License", AS_OF - timedelta(days=100), AS_OF + timedelta(days=600), False)
    # 4 valid of 5 required documents in the compliance denominator (see engine).

    # --- 2. Almarai Trading Est. — Preferred / High Risk (open critical NCR)
    # Q=100, D=100, C=100, closed NCRs grade A -> NCR KPI 100. final=100 -> Preferred.
    # One OPEN CRITICAL NCR (not yet overdue) -> High trigger, no KPI penalty.
    vc = "SUP-1002"
    vendors.append((vc, "Almarai Trading Est.", "Dairy", "supplier", "Saudi Arabia", "Active", 0))
    d = HISTORY_START
    for _ in range(22):
        add_supplier_delivery(vc, d, 9, DELAY_FOR_BAND["OnTime"], 1000, 1000)
        d += timedelta(days=28)
    full_valid_docs(vc, 5)
    for _ in range(3):  # closed grade A
        r = rand_date(HISTORY_START, AS_OF - timedelta(days=120))
        add_ncr(vc, r, r + timedelta(days=30), r + timedelta(days=20), "Major", "Closed")
    # open critical NCR raised recently, due in the future -> not overdue
    add_ncr(vc, AS_OF - timedelta(days=10), AS_OF + timedelta(days=20), None, "Critical", "Open")

    # --- 3. Bayara Foods — Reassessment Required / boundary at exactly 74.6%
    # Q=76 (7600/10000), D=72 (bands 85,85,70,70,50), C=75 (3/4, expired NON-mandatory),
    # N=75 (grade C closures). final = 26.6+18+15+15 = 74.6 -> just under Conditional (75).
    vc = "SUP-1003"
    vendors.append((vc, "Bayara Foods", "FMCG", "supplier", "UAE", "Active", 0))
    base = HISTORY_START + timedelta(days=30)
    bands = ["Minor", "Minor", "Major", "Major", "Critical"]  # avg score 72
    accepts = [1520, 1520, 1520, 1520, 1520]                  # 7600 / 10000 = 76%
    for i, b in enumerate(bands):
        add_supplier_delivery(vc, base + timedelta(days=90 * i), 10,
                              DELAY_FOR_BAND[b], 2000, accepts[i])
    add_doc(vc, "FSSC 22000 v6", AS_OF - timedelta(days=200), AS_OF + timedelta(days=400), True)
    add_doc(vc, "ISO 22000:2018", AS_OF - timedelta(days=100), AS_OF + timedelta(days=500), True)
    add_doc(vc, "Halal Certificate", AS_OF - timedelta(days=100), AS_OF + timedelta(days=300), True)
    add_doc(vc, "Public Liability Insurance", AS_OF - timedelta(days=500),
            AS_OF - timedelta(days=30), False)   # expired but NON-mandatory -> no High trigger
    for _ in range(3):  # grade C closures (10 days late) -> score 75 avg
        r = rand_date(HISTORY_START, AS_OF - timedelta(days=90))
        add_ncr(vc, r, r + timedelta(days=20), r + timedelta(days=30), "Minor", "Closed")

    # --- 4. Gulf Dairy Feeds — sharp quality decline over the last two quarters
    vc = "SUP-1004"
    vendors.append((vc, "Gulf Dairy Feeds", "Animal Feed", "supplier", "Bahrain", "Active", 0))
    month = HISTORY_START
    while month < AS_OF:
        months_from_end = (AS_OF.year - month.year) * 12 + (AS_OF.month - month.month)
        if months_from_end > 6:
            accept_rate = 0.98
        elif months_from_end > 3:
            accept_rate = 0.80
        else:
            accept_rate = 0.68            # last two quarters collapse
        qty = 1500
        add_supplier_delivery(vc, month, 8, DELAY_FOR_BAND["OnTime"], qty,
                              int(qty * accept_rate))
        month += timedelta(days=30)
    full_valid_docs(vc, 5)

    # --- 5. Doha Calibration Services — service provider, overdue-CAPA what-if.
    # SLA=85 (17/20 within), Service Quality=83, Response=83, HSE=83, Compliance=100,
    # CAPA=75 (3 of 4 within due; 1 overdue-open). Weighted:
    #   .25*85 + .25*83 + .20*83 + .15*83 + .10*100 + .05*75 = 84.8 -> Conditional / High.
    # Closing the overdue CAPA on time -> CAPA KPI 100 -> 86.05 -> Approved, risk clears.
    vc = "SRV-2003"
    vendors.append((vc, "Doha Calibration Services", "Maintenance", "service_provider",
                    "Qatar", "Active", 0))
    d = HISTORY_START
    for i in range(20):
        add_work_order(vc, d, 20 if i < 17 else 60, 48)   # 17 within SLA, 3 breach
        add_service_entry(vc, d, 83, 83, 83)
        d += timedelta(days=33)
    full_valid_docs(vc, 5)
    for _ in range(3):  # CAPAs closed within due
        r = rand_date(HISTORY_START, AS_OF - timedelta(days=90))
        add_ncr(vc, r, r + timedelta(days=20), r + timedelta(days=10), "Minor", "Closed", typ="CAPA")
    # overdue CAPA: due 90 days ago, still OPEN -> capa_overdue_beyond_limit + High risk
    add_ncr(vc, AS_OF - timedelta(days=150), AS_OF - timedelta(days=90), None,
            "Major", "Open", typ="CAPA")

    # --- 6. Emirates Facilities Management — service provider, HSE incident -> High/escalate
    vc = "SRV-2001"
    vendors.append((vc, "Emirates Facilities Management", "Facilities", "service_provider",
                    "UAE", "Active", 0))
    d = HISTORY_START
    for _ in range(30):
        add_work_order(vc, d, random.randint(4, 40), 48)  # within SLA
        add_service_entry(vc, d, random.randint(86, 94), random.randint(85, 93),
                          random.randint(80, 90))
        d += timedelta(days=22)
    full_valid_docs(vc, 5)
    add_hse_incident(vc, AS_OF - timedelta(days=45), "Lost Time Injury",
                     "Contractor slip-and-fall during tank cleaning; RIDDOR reportable.")

    # --- 7. Nadec Logistics — 3 documents expiring within 30 days (proactive alert)
    vc = "SRV-2002"
    vendors.append((vc, "Nadec Logistics", "Logistics", "service_provider",
                    "Saudi Arabia", "Active", 0))
    d = HISTORY_START
    for _ in range(28):
        add_work_order(vc, d, random.randint(6, 44), 48)
        add_service_entry(vc, d, random.randint(88, 96), random.randint(88, 95),
                          random.randint(88, 95))
        d += timedelta(days=24)
    # 3 docs expiring soon (still valid now) + 2 comfortably valid
    add_doc(vc, "ISO 45001:2018", AS_OF - timedelta(days=350), AS_OF + timedelta(days=18), True)
    add_doc(vc, "Trade License", AS_OF - timedelta(days=350), AS_OF + timedelta(days=25), False)
    add_doc(vc, "Public Liability Insurance", AS_OF - timedelta(days=350),
            AS_OF + timedelta(days=12), False)
    add_doc(vc, "FSSC 22000 v6", AS_OF - timedelta(days=100), AS_OF + timedelta(days=500), True)
    add_doc(vc, "Halal Certificate", AS_OF - timedelta(days=100), AS_OF + timedelta(days=400), True)


# ===========================================================================
# FILLER VENDORS — profile-driven spread across classifications.
# ===========================================================================
SUP_FILLER_NAMES = [
    "Khaleej Sugar Refinery", "Arabian Cartons Industries", "Delta Food Industries",
    "National Food Products Co.", "Agthia Consumer Products", "Al Ain Farms",
    "Marmum Dairy Farm", "Halwani Brothers", "Sunbulah Group", "Basmah Trading",
    "Gulfa Mineral Water", "Al Kabeer Group", "Emirates Modern Poultry",
    "Al Islami Foods", "Pinar Gulf", "Hayat Dairy", "Al Safi Danone",
    "Al Watania Poultry", "Nestle Gulf Supplies", "Barakat Vegetables",
]
SRV_FILLER_NAMES = [
    "Imdaad Facilities", "Farnek Services", "Enova Facilities", "Berkeley Services",
    "EFS Facilities", "Al Shirawi Contracting", "Etihad Cold Storage",
    "Aramex Logistics", "GAC Logistics", "Rentokil Boecker", "Musanadah FM",
    "Initial Saudi Group", "Tanzifco Environmental",
]

# tier -> (accept_rate, delivery_bands_pool, doc_valid_ratio, ncr_grade_days_late)
TIERS = {
    "preferred":   (0.99, ["OnTime", "OnTime", "OnTime", "Minor"], 1.0, [0, 0, 3]),
    "approved":    (0.95, ["OnTime", "OnTime", "Minor", "Minor"], 1.0, [0, 5, 6]),
    "conditional": (0.86, ["Minor", "Minor", "Major", "OnTime"], 0.83, [5, 10, 12]),
    "reassess":    (0.74, ["Major", "Major", "Critical", "Minor"], 0.7, [10, 20, 30]),
}
TIER_WEIGHTS = [("preferred", 3), ("approved", 8), ("conditional", 6), ("reassess", 3)]


def pick_tier():
    pool = []
    for t, w in TIER_WEIGHTS:
        pool += [t] * w
    return random.choice(pool)


def build_filler_supplier(vc, name):
    tier = pick_tier()
    accept_rate, bands, doc_ratio, ncr_late = TIERS[tier]
    country = random.choice(["Saudi Arabia", "UAE", "Bahrain", "Kuwait", "Oman", "Qatar"])
    blocked = 1 if (tier == "reassess" and random.random() < 0.25) else 0
    status = "Blocked" if blocked else "Active"
    vendors.append((vc, name, random.choice(["Dairy", "FMCG", "Packaging"]),
                    "supplier", country, status, blocked))
    n_po = random.randint(40, 56)
    d = HISTORY_START
    step = max((AS_OF - HISTORY_START).days // n_po, 1)
    for _ in range(n_po):
        qty = random.choice([500, 1000, 1500, 2000])
        accepted = int(qty * min(1.0, random.gauss(accept_rate, 0.03)))
        accepted = max(0, min(qty, accepted))
        band = random.choice(bands)
        add_supplier_delivery(vc, d, random.randint(7, 25), DELAY_FOR_BAND[band], qty, accepted)
        d += timedelta(days=step)
    # docs
    req_types = DOC_TYPES_MANDATORY + [random.choice(DOC_TYPES_OPTIONAL)]
    n_valid = round(len(req_types) * doc_ratio)
    for i, dt in enumerate(req_types):
        mandatory = dt in DOC_TYPES_MANDATORY
        if i < n_valid:
            add_doc(vc, dt, AS_OF - timedelta(days=300), AS_OF + timedelta(days=random.randint(120, 600)), mandatory)
        else:
            # expired; if mandatory this creates a legitimate High-risk filler
            add_doc(vc, dt, AS_OF - timedelta(days=700), AS_OF - timedelta(days=random.randint(10, 120)), mandatory)
    # NCRs — profile grades plus extra minor closures for realistic volume
    for late in ncr_late:
        if random.random() < 0.7:
            r = rand_date(HISTORY_START, AS_OF - timedelta(days=90))
            add_ncr(vc, r, r + timedelta(days=25), r + timedelta(days=25 + late),
                    random.choice(["Minor", "Major"]), "Closed")
    for _ in range(random.randint(2, 5)):
        r = rand_date(HISTORY_START, AS_OF - timedelta(days=60))
        late = random.choice([0, 3, 6, 10])
        add_ncr(vc, r, r + timedelta(days=20), r + timedelta(days=20 + late),
                "Minor", "Closed")


def build_filler_service(vc, name):
    tier = pick_tier()
    country = random.choice(["Saudi Arabia", "UAE", "Bahrain", "Kuwait", "Oman", "Qatar"])
    base = {"preferred": 96, "approved": 90, "conditional": 80, "reassess": 72}[tier]
    blocked = 1 if (tier == "reassess" and random.random() < 0.2) else 0
    status = "Suspended" if blocked else "Active"
    low = name.lower()
    if any(w in low for w in ("logistics", "cold storage", "aramex", "gac")):
        category = "Logistics"
    elif any(w in low for w in ("facilities", "services", "contracting", "efs", "fm")):
        category = "Facilities"
    else:
        category = "Maintenance"
    vendors.append((vc, name, category, "service_provider", country, status, blocked))
    n_wo = random.randint(32, 46)
    within_sla_rate = {"preferred": 0.98, "approved": 0.92, "conditional": 0.82, "reassess": 0.68}[tier]
    d = HISTORY_START
    step = max((AS_OF - HISTORY_START).days // n_wo, 1)
    for _ in range(n_wo):
        sla = 48
        if random.random() < within_sla_rate:
            hours = random.randint(4, sla - 2)
        else:
            hours = random.randint(sla + 4, sla + 60)
        add_work_order(vc, d, hours, sla)
        if random.random() < 0.6:
            add_service_entry(vc, d,
                              max(0, min(100, int(random.gauss(base, 4)))),
                              max(0, min(100, int(random.gauss(base, 4)))),
                              max(0, min(100, int(random.gauss(base + 2, 4)))))
        d += timedelta(days=step)
    req_types = DOC_TYPES_MANDATORY + [random.choice(DOC_TYPES_OPTIONAL)]
    doc_ratio = TIERS[tier][2]
    n_valid = round(len(req_types) * doc_ratio)
    for i, dt in enumerate(req_types):
        mandatory = dt in DOC_TYPES_MANDATORY
        if i < n_valid:
            add_doc(vc, dt, AS_OF - timedelta(days=300), AS_OF + timedelta(days=random.randint(120, 600)), mandatory)
        else:
            add_doc(vc, dt, AS_OF - timedelta(days=700), AS_OF - timedelta(days=random.randint(10, 120)), mandatory)
    # a few CAPAs
    for _ in range(random.randint(2, 5)):
        r = rand_date(HISTORY_START, AS_OF - timedelta(days=60))
        late = {"preferred": 0, "approved": 4, "conditional": 12, "reassess": 25}[tier]
        add_ncr(vc, r, r + timedelta(days=20), r + timedelta(days=20 + late),
                random.choice(["Minor", "Major"]), "Closed", typ="CAPA")


# ===========================================================================
# SQLite schema + write
# ===========================================================================
SCHEMA = """
DROP TABLE IF EXISTS meta;
DROP TABLE IF EXISTS vendors;
DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS goods_receipts;
DROP TABLE IF EXISTS inspection_lots;
DROP TABLE IF EXISTS work_orders;
DROP TABLE IF EXISTS service_entries;
DROP TABLE IF EXISTS ncr_capa;
DROP TABLE IF EXISTS compliance_docs;
DROP TABLE IF EXISTS hse_incidents;

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE vendors (
    vendor_code TEXT PRIMARY KEY, name TEXT, category TEXT, type TEXT,
    country TEXT, status TEXT, blocked_flag INTEGER);
CREATE TABLE purchase_orders (
    po_number TEXT PRIMARY KEY, vendor_code TEXT, material_code TEXT, po_date TEXT,
    requested_delivery_date TEXT, qty REAL, value REAL);
CREATE TABLE goods_receipts (
    grn_number TEXT PRIMARY KEY, po_number TEXT, posting_date TEXT, received_qty REAL);
CREATE TABLE inspection_lots (
    lot_number TEXT PRIMARY KEY, grn_number TEXT, lot_qty REAL, accepted_qty REAL,
    rejected_qty REAL, usage_decision TEXT, ud_date TEXT);
CREATE TABLE work_orders (
    wo_number TEXT PRIMARY KEY, vendor_code TEXT, order_type TEXT, planned_completion TEXT,
    actual_completion TEXT, sla_hours REAL);
CREATE TABLE service_entries (
    ses_number TEXT PRIMARY KEY, vendor_code TEXT, service_date TEXT, quality_rating REAL,
    response_rating REAL, hse_rating REAL, end_user TEXT);
CREATE TABLE ncr_capa (
    record_id TEXT PRIMARY KEY, vendor_code TEXT, source TEXT, type TEXT, severity TEXT,
    raised_date TEXT, due_date TEXT, closed_date TEXT, status TEXT);
CREATE TABLE compliance_docs (
    doc_id TEXT PRIMARY KEY, vendor_code TEXT, doc_type TEXT, issue_date TEXT,
    expiry_date TEXT, mandatory_flag INTEGER);
CREATE TABLE hse_incidents (
    incident_id TEXT PRIMARY KEY, vendor_code TEXT, incident_date TEXT, severity TEXT,
    description TEXT);
"""


def write_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO meta VALUES (?,?)", ("as_of_date", AS_OF.isoformat()))
    conn.executemany("INSERT INTO vendors VALUES (?,?,?,?,?,?,?)", vendors)
    conn.executemany("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?)", purchase_orders)
    conn.executemany("INSERT INTO goods_receipts VALUES (?,?,?,?)", goods_receipts)
    conn.executemany("INSERT INTO inspection_lots VALUES (?,?,?,?,?,?,?)", inspection_lots)
    conn.executemany("INSERT INTO work_orders VALUES (?,?,?,?,?,?)", work_orders)
    conn.executemany("INSERT INTO service_entries VALUES (?,?,?,?,?,?,?)", service_entries)
    conn.executemany("INSERT INTO ncr_capa VALUES (?,?,?,?,?,?,?,?,?)", ncr_capa)
    conn.executemany("INSERT INTO compliance_docs VALUES (?,?,?,?,?,?)", compliance_docs)
    conn.executemany("INSERT INTO hse_incidents VALUES (?,?,?,?,?)", hse_incidents)
    conn.commit()
    conn.close()


def main():
    build_narrative()
    for i, nm in enumerate(SUP_FILLER_NAMES):
        build_filler_supplier(f"SUP-1{100 + i:03d}", nm)
    for i, nm in enumerate(SRV_FILLER_NAMES):
        build_filler_service(f"SRV-2{100 + i:03d}", nm)
    write_db()
    print(f"Wrote {DB_PATH}")
    print(f"  vendors           {len(vendors)}")
    print(f"  purchase_orders   {len(purchase_orders)}")
    print(f"  goods_receipts    {len(goods_receipts)}")
    print(f"  inspection_lots   {len(inspection_lots)}")
    print(f"  work_orders       {len(work_orders)}")
    print(f"  service_entries   {len(service_entries)}")
    print(f"  ncr_capa          {len(ncr_capa)}")
    print(f"  compliance_docs   {len(compliance_docs)}")
    print(f"  hse_incidents     {len(hse_incidents)}")


if __name__ == "__main__":
    main()
