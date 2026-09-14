"""
Google Gemini backend — Gemini API (API key) or Vertex AI (enterprise path).

Same contract as the Claude backend: the model can only RETRIEVE and EXPLAIN
engine output through the read-only tools in ``tools.py``. The tool schemas,
the system prompt and the citation trail are shared verbatim via ``common`` —
only the wire shape differs.

Three Anthropic-only features have no Gemini equivalent and are absent here:
server-side refusal fallback, ``output_config.effort``, and ephemeral prompt
caching of the injected vendor directory. Everything the demo depends on —
streaming, parallel tool calls, cited records — works on both.

Selected with VENDORLENS_LLM_PROVIDER=gemini (or =vertex for Vertex AI).
"""

import inspect
import json
import logging
import os

from ..tools import TOOL_DEFS, execute
from .common import MAX_ROUNDS, MODEL, PROVIDER, citations, seed_messages, system_for

logger = logging.getLogger("vendorlens.llm.gemini")

# How hard the model should think before answering. Retrieval/explain wants
# little of it, so "low" is the default.
#
# The two model families disagree on the field name: Gemini 3.x takes a
# thinking_level ("low"/"high"), and rejects the thinking_budget integer that
# Gemini 2.5 takes with a bare 400 INVALID_ARGUMENT. So a numeric value here is
# sent as a budget and a word is sent as a level — and if the server rejects
# either, _open_stream drops thinking entirely and retries once.
#   low | high   -> thinking_level   (Gemini 3.x)
#   0 | 1024 | … -> thinking_budget  (Gemini 2.5; 0 disables)
#   auto         -> omit, let the model decide
_THINKING = os.getenv(
    "VENDORLENS_GEMINI_THINKING",
    os.getenv("VENDORLENS_GEMINI_THINKING_BUDGET", "low"),
).strip().lower()

# Flipped off permanently the first time the server rejects a thinking config,
# so one bad request costs one retry rather than one per question.
_thinking_ok = True


def _make_client():
    try:
        from google import genai
    except Exception as e:
        logger.warning("google-genai not installed (%s); using mock. "
                       "Add google-genai to backend/requirements.txt.", e)
        return None

    if PROVIDER == "vertex":
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            logger.warning("GOOGLE_CLOUD_PROJECT not set; using mock responder.")
            return None
        try:  # pragma: no cover - deployment-specific
            return genai.Client(vertexai=True, project=project, location=location)
        except Exception as e:  # pragma: no cover
            logger.warning("Vertex client unavailable (%s); using mock.", e)
            return None

    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        logger.warning("GOOGLE_API_KEY not set; using deterministic mock responder.")
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:  # pragma: no cover
        logger.warning("Gemini client unavailable (%s); using mock.", e)
        return None


_client = _make_client()


def live():
    return _client is not None


def _function_declarations():
    """Translate the shared Anthropic-shaped tool defs into Gemini's shape.

    The schemas themselves carry over unchanged — both sides take the same
    JSON Schema subset (type/properties/required/enum/description). Only the
    key name differs, and Gemini rejects an object schema with no properties,
    so a no-argument tool declares no parameters at all.
    """
    from google.genai import types

    decls = []
    for t in TOOL_DEFS:
        schema = t.get("input_schema") or {}
        kwargs = {"name": t["name"], "description": t["description"]}
        if schema.get("properties"):
            kwargs["parameters"] = schema
        decls.append(types.FunctionDeclaration(**kwargs))
    return decls


def _thinking_config(types):
    """A numeric setting is a Gemini 2.5 budget, a word is a Gemini 3 level."""
    if not _thinking_ok or _THINKING in ("", "auto", "default"):
        return None
    try:
        if _THINKING.lstrip("-").isdigit():
            return types.ThinkingConfig(thinking_budget=int(_THINKING))
        return types.ThinkingConfig(thinking_level=_THINKING)
    except (AttributeError, ValueError):  # pragma: no cover - older SDK
        logger.warning("Ignoring VENDORLENS_GEMINI_THINKING=%r.", _THINKING)
        return None


def _config(system_full):
    from google.genai import types

    kwargs = dict(
        system_instruction=system_full,
        tools=[types.Tool(function_declarations=_function_declarations())],
        max_output_tokens=4096,
        temperature=0.0,
    )

    # Tool calls are executed here, against the engine — never by the SDK.
    try:
        kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
            disable=True
        )
    except AttributeError:  # pragma: no cover - older SDK
        pass

    thinking = _thinking_config(types)
    if thinking is not None:
        kwargs["thinking_config"] = thinking

    return types.GenerateContentConfig(**kwargs)


def _jsonable(out):
    """Tool results must be a JSON-serialisable dict on Gemini's wire format."""
    coerced = json.loads(json.dumps(out, default=str))
    return coerced if isinstance(coerced, dict) else {"result": coerced}


async def _open_stream(model, contents, system_full):
    """Open the response stream, retrying once without the thinking config if
    the server rejects it.

    Gemini 3.x answers a thinking_budget with a bare 400 INVALID_ARGUMENT that
    names no field, so the only way to tell that setting apart from a genuinely
    malformed request is to drop it and see.
    """
    global _thinking_ok

    async def go():
        # The aio streaming call returns an async iterator, awaitable in some
        # SDK versions and returned directly in others. Accept both.
        maybe = _client.aio.models.generate_content_stream(
            model=model, contents=contents, config=_config(system_full)
        )
        return await maybe if inspect.isawaitable(maybe) else maybe

    try:
        return await go()
    except Exception as e:
        if not _thinking_ok or "INVALID_ARGUMENT" not in str(e):
            raise
        logger.warning(
            "Model rejected the thinking config (%s=%r); retrying without it.",
            "VENDORLENS_GEMINI_THINKING", _THINKING)
        _thinking_ok = False
        return await go()


async def stream(store, question, history=None):
    """Async generator yielding SSE-friendly event dicts."""
    from google.genai import types

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in seed_messages(history, question)
    ]
    system_full = system_for(store)

    for _ in range(MAX_ROUNDS):
        model_parts, calls = [], []

        async for chunk in await _open_stream(MODEL, contents, system_full):
            for cand in (chunk.candidates or []):
                content = getattr(cand, "content", None)
                for part in (getattr(content, "parts", None) or []):
                    if getattr(part, "thought", False):
                        continue  # reasoning trace, not an answer
                    model_parts.append(part)
                    if part.text:
                        yield {"type": "token", "content": part.text}
                    elif getattr(part, "function_call", None):
                        calls.append(part.function_call)

        if model_parts:
            contents.append(types.Content(role="model", parts=model_parts))

        if not calls:
            break

        # Parallel calls in one turn come back as several parts — answer them
        # all in a single user turn, as Gemini expects.
        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            yield {"type": "tool_use", "name": call.name, "input": args}
            out = execute(store, call.name, args)
            for cite in citations(out):
                yield {"type": "citation", **cite}
            result_parts.append(
                types.Part.from_function_response(
                    name=call.name, response=_jsonable(out)
                )
            )
        contents.append(types.Content(role="user", parts=result_parts))

    yield {"type": "done"}
