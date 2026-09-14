"""
Live LLM smoke check — run the demo questions against the configured provider
and print the answer next to the engine's authoritative values.

The point is not that the model answers, but that every figure it states is
traceable. For each vendor code the answer mentions, this prints the engine's
own score / classification / risk so you can eyeball the two in one screen
before trusting the model on stage.

Run (from the repo root):

    VENDORLENS_LLM_PROVIDER=gemini GOOGLE_API_KEY=... python scripts/check_llm.py
    VENDORLENS_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... python scripts/check_llm.py

Optional: pass your own questions as arguments instead of the demo set.
"""

import asyncio
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.engine import get_store, list_scorecards  # noqa: E402
from app.services import llm  # noqa: E402

QUESTIONS = [
    "Which of our suppliers are high risk right now, and what's driving it?",
    "Al Wajba Packaging scores 96% but you've flagged them high risk — why?",
    "Which vendors have mandatory documents expiring in the next 30 days?",
]

BOLD, DIM, RED, GREEN, OFF = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[0m"


async def ask(store, question, codes_by_code):
    print(f"\n{BOLD}Q: {question}{OFF}")
    started = time.monotonic()
    text, tools, cites, notices = [], [], set(), []

    async for ev in llm.stream_answer(store, question):
        kind = ev.get("type")
        if kind == "token":
            text.append(ev["content"])
        elif kind == "tool_use":
            tools.append(f'{ev["name"]}({ev.get("input") or {}})')
        elif kind == "citation":
            cites.add(ev.get("record_id"))
        elif kind == "notice":
            notices.append(ev["content"])

    answer = "".join(text).strip()
    elapsed = time.monotonic() - started

    print(answer or f"{RED}(no text returned){OFF}")
    print(f"\n{DIM}{elapsed:.1f}s · {len(tools)} tool call(s) · "
          f"{len(cites)} cited record(s){OFF}")
    for t in tools:
        print(f"{DIM}  tool: {t}{OFF}")
    if cites:
        shown = sorted(cites)[:10]
        print(f"{DIM}  records: {', '.join(shown)}"
              f"{' …' if len(cites) > len(shown) else ''}{OFF}")
    for n in notices:
        print(f"{RED}  {n}{OFF}")

    # Engine ground truth for every vendor code the answer mentions.
    mentioned = sorted(set(re.findall(r"\b(?:SUP|SRV)-\d{4}\b", answer)))
    if mentioned:
        print(f"\n{DIM}  engine says (compare against the answer above):{OFF}")
        for code in mentioned:
            c = codes_by_code.get(code)
            if c is None:
                print(f"{RED}  {code}: NOT A REAL VENDOR CODE{OFF}")
                continue
            print(f"{DIM}  {code}: {c['name']} — score {c['final_score']} · "
                  f"{c['classification']} · {c['risk']} risk{OFF}")
    else:
        print(f"{DIM}  (answer cited no vendor codes — rule 2 asks it to){OFF}")

    return bool(answer) and not notices and llm.live_enabled()


async def main():
    store = get_store()
    codes_by_code = {c["vendor_code"]: c
                     for c in list_scorecards(store, include_sources=False)}

    print(f"{BOLD}provider{OFF} {llm.PROVIDER}   "
          f"{BOLD}model{OFF} {llm.MODEL}   "
          f"{BOLD}live{OFF} {llm.live_enabled()}")
    if not llm.live_enabled():
        print(f"{RED}No credentials for this provider — answers below come from "
              f"the deterministic mock, not the model.{OFF}")

    questions = sys.argv[1:] or QUESTIONS
    results = [await ask(store, q, codes_by_code) for q in questions]

    ok = sum(results)
    colour = GREEN if ok == len(results) else RED
    print(f"\n{colour}{ok}/{len(results)} answered live by {llm.MODEL}.{OFF} "
          f"Check each figure above against the engine lines before the demo.")


if __name__ == "__main__":
    asyncio.run(main())
