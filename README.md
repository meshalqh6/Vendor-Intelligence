# VendorLens

A client-facing demo of automated, KPI-driven supplier & service-provider
performance evaluation. Business users ask questions in natural language and get
answers **traceable back to source records** — because the scores are computed by
a **deterministic, auditable rules engine**, and the language model only retrieves
and explains them.

Built for a pre-sales meeting: realistic SAP/ETQ-shaped data, defensible numbers,
clean UI. Compliance context: FSSC 22000 v6, ISO 22000:2018, ISO 45001:2018.

---

## Quick start

```bash
docker compose up --build
# open http://localhost:8080
```

The demo runs **fully without an API key** (a deterministic mock answers the Ask
page). To enable live Claude answers:

```bash
cp .env.example .env
# put your key in ANTHROPIC_API_KEY, then:
docker compose up --build
```

### Local dev (without Docker)

```bash
# 1. generate the deterministic SQLite database
python scripts/generate_data.py

# 2. backend  (http://localhost:8000)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. frontend (http://localhost:5173, proxies /api to :8000)
cd frontend && npm install && npm run dev
```

Run the engine tests (the "defensible numbers" proof):

```bash
cd backend && python -m pytest -q
```

---

## Architecture

```
React / Vite (nginx :8080) ──/api──▶ FastAPI (:8000)
                                        ├─▶ Rules Engine (pure Python)  ──▶ SQLite
                                        │     loads config/*.yaml            (data/vendorlens.db)
                                        └─▶ Claude (tool-use, SSE stream)
                                              calls READ-ONLY tools that return engine output only
```

- **`config/scoring.yaml`** — every weight, band and threshold. Change it and the
  scores recompute. Nothing is hard-coded in Python.
- **`config/next_actions.yaml`** — the 4×4 (classification × risk) action matrix.
- **`backend/app/engine/`** — `scoring.py` (KPIs, weighting, classification),
  `risk.py` (risk + the High-Risk hard override), `actions.py`, `store.py`. Pure,
  testable functions. `backend/tests/` asserts every planted scenario's exact output.
- **`backend/app/services/`** — `tools.py` (read-only engine wrappers exposed to
  the model) and `llm/` (the retrieve/explain layer: `common.py` holds the system
  prompt, vendor directory, citations and mock responder; one module per provider).
- **`scripts/generate_data.py`** — seeded SAP/ETQ-shaped SQLite generator (~40
  Gulf-region dairy/FMCG vendors, 24 months). Identical every run.

### Why it's defensible
The model is given **read-only tools** whose results come straight from the
deterministic engine, and is system-prompted to **never compute a number** — it
must call a tool and cite the record IDs it returned. Every figure on screen
traces to an engine result plus the source rows behind it.

## Scoring model

**Supplier KPIs** — Quality 35%, Delivery 25%, Compliance 20%, NCR/CAPA 20%.
**Service-provider KPIs** — SLA 25%, Service Quality 25%, Response 20%, HSE 15%,
Compliance Docs 10%, CAPA 5%.
**Classification** — ≥95 Preferred · 85–94 Approved · 75–84 Conditional · <75
Reassessment Required.
**Risk** is independent of score. Any critical trigger (expired mandatory document,
critical NCR, CAPA overdue beyond limit, HSE incident, blocked/suspended vendor)
forces **High Risk regardless of score** — see `config/scoring.yaml`.

## Open questions (raise with the client)

- **NCR/CAPA weight — 20% vs 15%.** The source requirement document states **20%**
  in the weight column but **"KPI Score × 15%"** in the methodology text. Only 20%
  makes the four supplier weights sum to 100%, so **20% is the default** (see the
  `# TODO` in `config/scoring.yaml`). Please confirm the intended figure.

## LLM & deployment notes

- **Default model:** Claude **Fable 5** (`claude-fable-5`) with a server-side
  fallback to Opus 4.8. Override with `VENDORLENS_MODEL`. The retrieve/explain
  layer streams answers over SSE.
- **Provider-swappable** via `VENDORLENS_LLM_PROVIDER` — the engine, the tools and
  the UI are unchanged in every case, because the model only ever retrieves and
  explains engine output:

  | Provider | Credentials | Notes |
  |---|---|---|
  | `anthropic` (default) | `ANTHROPIC_API_KEY` | Claude Fable 5 + server-side fallback |
  | `foundry` | `ANTHROPIC_API_KEY`, `VENDORLENS_FOUNDRY_RESOURCE` | **Claude on Microsoft Foundry (Azure)** — the enterprise path. No server-side fallbacks. |
  | `gemini` | `GOOGLE_API_KEY` | **Google Gemini API**, default `gemini-3.6-flash` |
  | `vertex` | `GOOGLE_CLOUD_PROJECT` | Gemini on **Vertex AI** |

  With no credentials for the selected provider, VendorLens answers from the
  deterministic mock responder — the demo never goes dark.
- **What differs on Gemini:** three Anthropic-only features are absent —
  server-side refusal fallback, `output_config.effort`, and ephemeral caching of
  the injected vendor directory. Thinking is set low for latency
  (`VENDORLENS_GEMINI_THINKING=low`); Gemini 2.5 models take a numeric budget
  instead, which the backend infers from the value's shape. Streaming, parallel
  tool calls and the cited-record trail are identical on both.
- **Verified live** against `gemini-3.6-flash` on the three `docs/DEMO_SCRIPT.md`
  questions. Every figure, record ID and expiry date matched engine output
  exactly; 2.6–4.0s per answer. Run `python scripts/check_llm.py` to repeat the
  check — it prints each answer next to the engine's authoritative values.

## Not built (per demo scope)
No authentication, multi-tenancy, user management, or real SAP connector. This is a
demo that proves the evaluation logic and the traceable Q&A, not a production system.
