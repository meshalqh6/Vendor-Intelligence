"""
DEAD CODE — SUPERSEDED, DO NOT EDIT.

Replaced by the `services/llm/` package, which added Google Gemini alongside
Claude. Nothing imports this module; it is a frozen copy kept only for
reference and will drift out of sync. Edit these instead:

    services/llm/common.py            system prompt, vendor directory,
                                      citations, deterministic mock responder
    services/llm/anthropic_backend.py Claude (direct API + Foundry)
    services/llm/gemini_backend.py    Gemini (Gemini API + Vertex AI)
    services/llm/__init__.py          provider dispatch

Safe to delete.

---

Claude retrieval/explain layer.

The LLM only RETRIEVES and EXPLAINS engine output via read-only tools — it never
computes a number. Built on Claude Fable 5 with a server-side fallback to Opus
4.8 (Fable's classifiers can occasionally false-positive on benign work, and the
fallback keeps the demo answering). Falls back to a deterministic templated
responder when no ANTHROPIC_API_KEY is set, so the demo is always stage-safe.

Provider is swappable via VENDORLENS_LLM_PROVIDER:
  - "anthropic" (default): direct Anthropic API — simplest for the demo.
  - "foundry": Claude on Microsoft Foundry (Azure) — the enterprise path. Server-
    side fallbacks are unavailable on Foundry, so they are omitted there.
"""

import json
import logging
import os

from .tools import TOOL_DEFS, execute

logger = logging.getLogger("vendorlens.claude")

MODEL = os.getenv("VENDORLENS_MODEL", "claude-fable-5")
FALLBACK_MODEL = os.getenv("VENDORLENS_FALLBACK_MODEL", "claude-opus-4-8")
PROVIDER = os.getenv("VENDORLENS_LLM_PROVIDER", "anthropic")
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


def _make_client():
    if PROVIDER == "foundry":
        try:
            from anthropic import AsyncAnthropicFoundry
            return AsyncAnthropicFoundry(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                resource=os.getenv("VENDORLENS_FOUNDRY_RESOURCE"),
            )
        except Exception as e:  # pragma: no cover - deployment-specific
            logger.warning("Foundry client unavailable (%s); using mock.", e)
            return None
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set; using deterministic mock responder.")
        return None
    try:
        from anthropic import AsyncAnthropic
        return AsyncAnthropic()
    except Exception as e:  # pragma: no cover
        logger.warning("Anthropic client unavailable (%s); using mock.", e)
        return None


_client = _make_client()

# Server-side refusal fallback only applies to the Fable/Mythos family on the
# direct Anthropic API. For Opus/Sonnet it is unnecessary, so we use the plain
# (non-beta) messages endpoint there.
_USE_FALLBACK = PROVIDER == "anthropic" and MODEL.startswith(("claude-fable", "claude-mythos"))


def live_enabled():
    return _client is not None


def _messages_api():
    return _client.beta.messages if _USE_FALLBACK else _client.messages


_directory_cache = None


def _vendor_directory(store):
    """Compact, authoritative engine snapshot injected into the system prompt so
    name->code resolution and portfolio/risk questions need no tool round-trip."""
    global _directory_cache
    if _directory_cache is None:
        from ..engine import list_scorecards
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


def _system_for(store):
    return (
        SYSTEM_PROMPT
        + "\n\nVENDOR DIRECTORY (authoritative engine output — "
          "code | name | type | category | score | classification | risk | risk_triggers):\n"
        + _vendor_directory(store)
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


def _request_kwargs(system_full):
    kwargs = dict(
        model=MODEL,
        max_tokens=4096,
        system=[{"type": "text", "text": system_full, "cache_control": {"type": "ephemeral"}}],
        tools=TOOL_DEFS,
        output_config={"effort": "low"},   # retrieval/explain — low effort is faster
    )
    # Disable thinking for speed on non-Fable models (Fable is always-on; disabling 400s).
    # Sonnet 5 defaults to adaptive thinking when omitted — turn it off for this task.
    if not MODEL.startswith(("claude-fable", "claude-mythos")):
        kwargs["thinking"] = {"type": "disabled"}
    if _USE_FALLBACK:
        kwargs["betas"] = ["server-side-fallback-2026-06-01"]
        kwargs["fallbacks"] = [{"model": FALLBACK_MODEL}]
    return kwargs


def _seed_messages(history, question):
    """Build the message list from prior turns + the new question. Keeps only the
    recent user/assistant text turns so follow-ups have context without ballooning."""
    msgs = []
    for m in (history or [])[-10:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    # Ensure the thread starts on a user turn (the API requires it).
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": question})
    return msgs


async def stream_answer(store, question, history=None):
    """Async generator yielding SSE-friendly event dicts."""
    if _client is None:
        for ev in _mock_answer(store, question):
            yield ev
        return

    messages = _seed_messages(history, question)
    system_full = _system_for(store)
    try:
        for _ in range(MAX_ROUNDS):
            async with _messages_api().stream(
                messages=messages, **_request_kwargs(system_full)
            ) as stream:
                async for text in stream.text_stream:
                    yield {"type": "token", "content": text}
                final = await stream.get_final_message()

            messages.append({"role": "assistant", "content": final.content})
            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if final.stop_reason != "tool_use" or not tool_uses:
                break

            results = []
            for tu in tool_uses:
                yield {"type": "tool_use", "name": tu.name, "input": tu.input}
                out = execute(store, tu.name, tu.input)
                for cite in _citations(out):
                    yield {"type": "citation", **cite}
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(out, default=str),
                })
            messages.append({"role": "user", "content": results})
        yield {"type": "done"}
    except Exception as e:  # keep the demo alive on any API hiccup
        logger.exception("LLM stream failed; falling back to mock.")
        yield {"type": "notice", "content": f"(Live model unavailable: {e}. Showing deterministic answer.)"}
        for ev in _mock_answer(store, question):
            yield ev


def _citations(out):
    """Pull vendor_code + record IDs out of a tool result for the UI trail."""
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
def _mock_answer(store, question):
    from ..engine import build_scorecard, list_scorecards

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
