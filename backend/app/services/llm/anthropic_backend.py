"""
Claude backend — direct Anthropic API or Claude on Microsoft Foundry (Azure).

Built on Claude Fable 5 with a server-side fallback to Opus 4.8 (Fable's
classifiers can occasionally false-positive on benign work, and the fallback
keeps the demo answering). Foundry does not support server-side fallbacks, so
they are omitted there.
"""

import json
import logging
import os

from ..tools import TOOL_DEFS, execute
from .common import MAX_ROUNDS, MODEL, PROVIDER, citations, seed_messages, system_for

logger = logging.getLogger("vendorlens.llm.anthropic")

FALLBACK_MODEL = os.getenv("VENDORLENS_FALLBACK_MODEL", "claude-opus-4-8")

# Server-side refusal fallback only applies to the Fable/Mythos family on the
# direct Anthropic API. For Opus/Sonnet it is unnecessary, so we use the plain
# (non-beta) messages endpoint there.
_USE_FALLBACK = PROVIDER == "anthropic" and MODEL.startswith(("claude-fable", "claude-mythos"))


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


def live():
    return _client is not None


def _messages_api():
    return _client.beta.messages if _USE_FALLBACK else _client.messages


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


async def stream(store, question, history=None):
    """Async generator yielding SSE-friendly event dicts."""
    messages = seed_messages(history, question)
    system_full = system_for(store)

    for _ in range(MAX_ROUNDS):
        async with _messages_api().stream(
            messages=messages, **_request_kwargs(system_full)
        ) as s:
            async for text in s.text_stream:
                yield {"type": "token", "content": text}
            final = await s.get_final_message()

        messages.append({"role": "assistant", "content": final.content})
        tool_uses = [b for b in final.content if b.type == "tool_use"]
        if final.stop_reason != "tool_use" or not tool_uses:
            break

        results = []
        for tu in tool_uses:
            yield {"type": "tool_use", "name": tu.name, "input": tu.input}
            out = execute(store, tu.name, tu.input)
            for cite in citations(out):
                yield {"type": "citation", **cite}
            results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(out, default=str),
            })
        messages.append({"role": "user", "content": results})

    yield {"type": "done"}
