"""
LLM retrieve/explain layer.

The rest of the application talks to exactly three names — ``stream_answer``,
``live_enabled`` and ``MODEL`` — so swapping the model provider touches nothing
outside this package. The engine, the read-only tools and the cited-record
trail are provider-neutral by construction: citations are read from tool
results, not from model output.

VENDORLENS_LLM_PROVIDER selects the backend:
  anthropic (default) — direct Anthropic API, Claude Fable 5 + server-side
                        fallback to Opus 4.8.
  foundry             — Claude on Microsoft Foundry (Azure). No server-side
                        fallbacks there.
  gemini              — Google Gemini API (GOOGLE_API_KEY).
  vertex              — Gemini on Vertex AI (GOOGLE_CLOUD_PROJECT).

With no credentials for the selected provider, every path falls back to the
deterministic mock responder, so the demo always answers.
"""

import logging

from .common import MODEL, PROVIDER, mock_answer

logger = logging.getLogger("vendorlens.llm")

_BACKENDS = {
    "anthropic": "anthropic_backend",
    "foundry": "anthropic_backend",
    "gemini": "gemini_backend",
    "vertex": "gemini_backend",
}


def _load_backend():
    name = _BACKENDS.get(PROVIDER)
    if name is None:
        logger.warning("Unknown VENDORLENS_LLM_PROVIDER %r; using mock responder.",
                       PROVIDER)
        return None
    try:
        from importlib import import_module
        return import_module(f".{name}", __name__)
    except Exception as e:  # pragma: no cover - import-time misconfiguration
        logger.warning("Backend %s unavailable (%s); using mock responder.", name, e)
        return None


_backend = _load_backend()


def live_enabled():
    return _backend is not None and _backend.live()


async def stream_answer(store, question, history=None):
    """Async generator yielding SSE-friendly event dicts.

    Event types are the frontend's contract and identical across providers:
    ``token``, ``tool_use``, ``citation``, ``notice``, ``done``.
    """
    if not live_enabled():
        for ev in mock_answer(store, question):
            yield ev
        return

    try:
        async for ev in _backend.stream(store, question, history):
            yield ev
    except Exception as e:  # keep the demo alive on any API hiccup
        logger.exception("LLM stream failed; falling back to mock.")
        yield {"type": "notice",
               "content": f"(Live model unavailable: {e}. Showing deterministic answer.)"}
        for ev in mock_answer(store, question):
            yield ev


__all__ = ["MODEL", "PROVIDER", "live_enabled", "stream_answer"]
