"""
Provider-neutral pieces of the retrieve/explain layer.

Everything here is shared by every backend: the system prompt and its hard
rules, the authoritative vendor directory injected into it, history handling,
citation extraction, and the deterministic mock responder that keeps the demo
stage-safe when no key is set.

Nothing in this module knows which vendor's API answers the question.
"""

import logging
import os

logger = logging.getLogger("vendorlens.llm")

PROVIDER = os.getenv("VENDORLENS_LLM_PROVIDER", "anthropic").strip().lower()

# Each provider has a different sensible default; VENDORLENS_MODEL overrides.
_DEFAULT_MODEL = {
    "anthropic": "claude-fable-5",
    "foundry": "claude-fable-5",
    "gemini": "gemini-3.6-flash",
}
MODEL = os.getenv("VENDORLENS_MODEL") or _DEFAULT_MODEL.get(PROVIDER, "claude-fable-5")

MAX_ROUNDS = 6

SYSTEM_PROMPT = (
    "You are VendorLens, an assistant for evaluating supplier and service-provider "
    "performance. Every score, KPI value, classification, risk status and next "
    "action is computed by a deterministic, auditable rules engine that you can "
    "reach ONLY through the provided tools.\n\n"
    "Hard rules:\n"
    "1. NEVER compute, estimate, round, or invent any number, score, percentage, "
    "classification, or risk level. Every figure you state must come verbatim from "
    "a tool result. If you need a number, call a tool.\n"
    "2. Always cite the vendor_code and the specific source record IDs (lot "
    "numbers, GRN numbers, document IDs, NCR/CAPA record IDs, incident IDs) that "
    "support your statement, so the user can trace it.\n"
    "3. Risk is independent of score and can override it — a high-scoring vendor "
    "can be High Risk (e.g. an expired mandatory certificate). Explain the trigger "
    "and cite the record.\n"
    "4. If the tools do not contain the answer, say so plainly. Do not guess.\n"
    "5. Lead with the answer, then the supporting evidence. Be concise."
)

_directory_cache = None


def vendor_directory(store):
    """Compact, authoritative engine snapshot injected into the system prompt so
    name->code resolution and portfolio/risk questions need no tool round-trip."""
    global _directory_cache
    if _directory_cache is None:
        from ...engine import list_scorecards
        lines = []
        for c in list_scorecards(store, include_sources=False):
            trg = ""
            if c["risk_triggers"]:
                trg = " | " + "; ".join(
                    f'{t["code"]}({",".join(t["source_record_ids"][:1])})'
                    for t in c["risk_triggers"])
            lines.append(f'{c["vendor_code"]} | {c["name"]} | {c["type"]} | '
                         f'{c["category"]} | {c["final_score"]} | '
                         f'{c["classification"]} | {c["risk"]}{trg}')
        _directory_cache = "\n".join(lines)
    return _directory_cache


def system_for(store):
    return (
        SYSTEM_PROMPT
        + "\n\nVENDOR DIRECTORY (authoritative engine output — "
          "code | name | type | category | score | classification | risk | risk_triggers):\n"
        + vendor_directory(store)
        + "\n\nTOOL-USE POLICY (important for latency — prefer the directory, avoid tool calls):\n"
          "- The directory above already contains the score, classification, risk and the "
          "triggering record ID for EVERY vendor. It is authoritative engine output.\n"
          "- Answer these DIRECTLY from the directory with NO tool call: which vendors are "
          "High risk (and why — the trigger + record are shown), portfolio counts, name→code "
          "lookups, filtering by category/type, and multi-vendor evaluation reports.\n"
          "- Call get_vendor_scorecard ONLY when the user explicitly wants a single vendor's "
          "detailed KPI breakdown. Call get_source_records ONLY when the user explicitly asks "
          "to see specific rows (e.g. 'which inspection lots'). Call get_alerts for "
          "expiring-document / watchlist questions.\n"
          "- If you do need data for multiple vendors, issue those tool calls in parallel in a "
          "single turn, never one after another.\n"
          "- Never state a value that isn't in this directory or a tool result."
    )


def seed_messages(history, question):
    """Prior turns + the new question as plain {role, content} dicts.

    Keeps only the recent user/assistant text turns so follow-ups have context
    without ballooning. Providers translate this into their own wire shape.
    """
    msgs = []
    for m in (history or [])[-10:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    # Ensure the thread starts on a user turn (every provider requires it).
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": question})
    return msgs


def citations(out):
    """Pull vendor_code + record IDs out of a tool result for the UI trail.

    Note this reads the ENGINE's output, not the model's — which is why the
    citation trail is identical whichever provider is answering.
    """
    cites = []
    if isinstance(out, dict):
        vc = out.get("vendor_code")
        for k in ("kpis",):
            for kpi in out.get(k, []) or []:
                for rid in (kpi.get("source_record_ids") or [])[:8]:
                    cites.append({"vendor_code": vc, "record_id": rid})
        for t in out.get("risk_triggers", []) or []:
            for rid in t.get("source_record_ids", []):
                cites.append({"vendor_code": vc, "record_id": rid, "trigger": t["code"]})
    return cites[:20]


# ---------------------------------------------------------------------------
# Deterministic mock — no LLM. Still cites real engine output.
# ---------------------------------------------------------------------------
def mock_answer(store, question):
    from ...engine import build_scorecard, list_scorecards

    q = question.lower()
    cards = list_scorecards(store, include_sources=True)
    match = next((c for c in cards if c["name"].lower() in q
                 or c["vendor_code"].lower() in q), None)
    if not match:
        match = next((c for c in cards
                      if any(w in c["name"].lower() for w in q.split() if len(w) > 3)), None)

    if match:
        c = build_scorecard(store, match["vendor_code"])
        parts = [
            f"{c['name']} ({c['vendor_code']}) scores {c['final_score']}/100 — "
            f"{c['classification']} / {c['risk']} Risk.\n\nKPI breakdown:"
        ]
        for k in c["kpis"]:
            parts.append(f"  - {k['label']}: {k['value']} (weight {int(k['weight']*100)}%, "
                         f"contributes {k['contribution']}). {k['detail']}")
        if c["risk_triggers"]:
            parts.append("\nRisk triggers (override the score):")
            for t in c["risk_triggers"]:
                parts.append(f"  - {t['label']}: {t['detail']} "
                             f"[records: {', '.join(t['source_record_ids'][:5])}]")
        parts.append(f"\nRecommended action: {c['next_action']['recommended_action']}")
        parts.append(f"System control: {c['next_action']['system_control']}")
        text = "\n".join(parts)
    else:
        pref_high = [c for c in cards if c["classification"] == "Preferred" and c["risk"] == "High"]
        text = ("I can answer questions about specific vendors and the portfolio. "
                f"There are {len(cards)} vendors. "
                + (f"{len(pref_high)} score Preferred yet carry High Risk due to a "
                   "critical trigger (e.g. an expired mandatory certificate): "
                   + ", ".join(f"{c['name']} ({c['vendor_code']})" for c in pref_high)
                   if pref_high else ""))

    for word in text.split(" "):
        yield {"type": "token", "content": word + " "}
    yield {"type": "done"}
