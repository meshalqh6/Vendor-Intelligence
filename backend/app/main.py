"""
VendorLens API — FastAPI over the deterministic engine plus the LLM
retrieve/explain endpoint.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .engine import build_alerts, build_scorecard, get_store, list_scorecards
from .services import llm
from .services.tools import execute as run_tool

app = FastAPI(title="VendorLens API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    store = get_store()
    return {"status": "healthy", "as_of": store.as_of.isoformat(),
            "live_llm": llm.live_enabled(), "provider": llm.PROVIDER,
            "model": llm.MODEL}


@app.get("/api/vendors")
def vendors(type: str = None, classification: str = None, risk: str = None):
    store = get_store()
    cards = list_scorecards(store, include_sources=False)
    if type:
        cards = [c for c in cards if c["type"] == type]
    if classification:
        cards = [c for c in cards if c["classification"] == classification]
    if risk:
        cards = [c for c in cards if c["risk"] == risk]
    # Summary counts for the dashboard header.
    summary = {"total": len(cards)}
    for key in ("classification", "risk"):
        counts = {}
        for c in cards:
            counts[c[key]] = counts.get(c[key], 0) + 1
        summary[key] = counts
    return {"vendors": cards, "summary": summary, "as_of": store.as_of.isoformat()}


@app.get("/api/vendors/{vendor_code}")
def vendor_detail(vendor_code: str):
    card = build_scorecard(get_store(), vendor_code)
    if not card:
        raise HTTPException(status_code=404, detail="vendor not found")
    return card


@app.get("/api/vendors/{vendor_code}/records")
def vendor_records(vendor_code: str, table: str = Query(...)):
    """Raw source rows for a table — the traceability drill-down."""
    rows = run_tool(get_store(), "get_source_records",
                    {"vendor_code": vendor_code, "table": table})
    if isinstance(rows, dict) and rows.get("error"):
        raise HTTPException(status_code=400, detail=rows["error"])
    return {"vendor_code": vendor_code, "table": table, "rows": rows}


@app.get("/api/alerts")
def alerts():
    return build_alerts(get_store())


@app.get("/api/config")
def config():
    """Expose the live scoring config so the demo can show it's data-driven."""
    store = get_store()
    return {"scoring": store.scoring, "next_actions": store.next_actions,
            "as_of": store.as_of.isoformat()}


# ---------------------------------------------------------------------------
# Follow-up workflow (simulated — no real mail server, per demo scope). Queues
# the message and returns a reference so the action feels real end-to-end.
# ---------------------------------------------------------------------------
_followups: list = []


class FollowupRequest(BaseModel):
    vendor_code: str
    vendor_name: Optional[str] = None
    alert_type: str
    record_id: Optional[str] = None
    to: Optional[str] = None
    subject: str
    body: str


@app.post("/api/followup")
def send_followup(req: FollowupRequest):
    ref = f"FU-{2500 + len(_followups) + 1}"
    rec = {"reference": ref,
           "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           **req.model_dump()}
    _followups.append(rec)
    return {"status": "queued", "reference": ref, "queued_at": rec["queued_at"]}


@app.get("/api/followups")
def list_followups():
    return {"followups": _followups}


class Turn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    history: Optional[list[Turn]] = None


@app.post("/api/ask")
async def ask(req: AskRequest):
    store = get_store()
    history = [t.model_dump() for t in (req.history or [])]

    async def event_stream():
        async for event in llm.stream_answer(store, req.question, history):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
