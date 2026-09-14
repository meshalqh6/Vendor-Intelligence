"""
Read-only tools exposed to Claude. Every tool returns output straight from the
deterministic engine or raw source rows — the model can only retrieve, never
compute. This is what makes the assistant's numbers traceable and un-fakeable.
"""

from ..engine import build_alerts, build_scorecard, list_scorecards

# Tables the model may pull raw rows from, for citing individual source records.
_SOURCE_TABLES = {
    "purchase_orders", "goods_receipts", "inspection_lots", "work_orders",
    "service_entries", "ncr_capa", "compliance_docs", "hse_incidents",
}

TOOL_DEFS = [
    {
        "name": "list_vendors",
        "description": (
            "List vendors with their computed score, classification, risk and "
            "recommended next action. Use to find vendors or answer portfolio-wide "
            "questions. Optional filters narrow the list."),
        "input_schema": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "Case-insensitive substring match on vendor name."},
                "category_contains": {"type": "string", "description": "Case-insensitive substring match on vendor category (e.g. 'Logistics', 'Facilities', 'Packaging')."},
                "type": {"type": "string", "enum": ["supplier", "service_provider"]},
                "classification": {"type": "string", "enum": ["Preferred", "Approved", "Conditional", "Reassessment Required"]},
                "risk": {"type": "string", "enum": ["Low", "Medium", "Moderate", "High"]},
            },
        },
    },
    {
        "name": "get_vendor_scorecard",
        "description": (
            "Get the full computed scorecard for one vendor: every KPI value, its "
            "weight and contribution, the source record IDs that fed each KPI, the "
            "final weighted score, classification, risk status with the exact "
            "triggers, the recommended next action, and the quarterly trend. Use "
            "this to explain WHY a vendor has a given score or risk."),
        "input_schema": {
            "type": "object",
            "properties": {"vendor_code": {"type": "string"}},
            "required": ["vendor_code"],
        },
    },
    {
        "name": "get_source_records",
        "description": (
            "Fetch raw source rows for a vendor from a SAP/ETQ table so you can "
            "cite individual records (e.g. the specific expired document or overdue "
            "CAPA). Tables: " + ", ".join(sorted(_SOURCE_TABLES)) + "."),
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_code": {"type": "string"},
                "table": {"type": "string", "enum": sorted(_SOURCE_TABLES)},
            },
            "required": ["vendor_code", "table"],
        },
    },
    {
        "name": "get_alerts",
        "description": (
            "Get the proactive watchlist: documents expiring within 30 days, "
            "expired mandatory documents, recorded HSE incidents, overdue CAPAs, "
            "and vendors sitting just below a classification threshold."),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def execute(store, name, tool_input):
    if name == "list_vendors":
        cards = list_scorecards(store, include_sources=False)
        f = tool_input or {}
        if f.get("name_contains"):
            q = f["name_contains"].lower()
            cards = [c for c in cards if q in c["name"].lower()]
        if f.get("category_contains"):
            q = f["category_contains"].lower()
            cards = [c for c in cards if q in c["category"].lower()]
        if f.get("type"):
            cards = [c for c in cards if c["type"] == f["type"]]
        if f.get("classification"):
            cards = [c for c in cards if c["classification"] == f["classification"]]
        if f.get("risk"):
            cards = [c for c in cards if c["risk"] == f["risk"]]
        return [{"vendor_code": c["vendor_code"], "name": c["name"], "type": c["type"],
                 "category": c["category"], "final_score": c["final_score"],
                 "classification": c["classification"], "risk": c["risk"],
                 "next_action": c["next_action"]} for c in cards]

    if name == "get_vendor_scorecard":
        card = build_scorecard(store, tool_input["vendor_code"])
        return card or {"error": "vendor not found"}

    if name == "get_source_records":
        table = tool_input["table"]
        if table not in _SOURCE_TABLES:
            return {"error": "table not allowed"}
        vc = tool_input["vendor_code"]
        fetch = {
            "purchase_orders": lambda: store._q("SELECT * FROM purchase_orders WHERE vendor_code=? LIMIT 60", (vc,)),
            "goods_receipts": lambda: store.deliveries(vc),
            "inspection_lots": lambda: store.inspection_lots(vc),
            "work_orders": lambda: store.work_orders(vc),
            "service_entries": lambda: store.service_entries(vc),
            "ncr_capa": lambda: store.ncr_capa(vc),
            "compliance_docs": lambda: store.compliance_docs(vc),
            "hse_incidents": lambda: store.hse_incidents(vc),
        }[table]()
        return fetch[:60]

    if name == "get_alerts":
        return build_alerts(store)

    return {"error": f"unknown tool {name}"}
