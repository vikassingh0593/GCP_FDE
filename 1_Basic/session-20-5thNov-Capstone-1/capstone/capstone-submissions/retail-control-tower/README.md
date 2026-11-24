# Retail Order Exception & Supply Chain Control Tower

Capstone 02 (session 20). An analyst asks why an order is delayed. The system investigates live order, inventory, carrier, warehouse and change data, uses runbooks and postmortems as guidance, and answers with cited evidence, or says what to check next.

**Action boundary (v1):** read-only. It investigates and recommends. It never changes orders, inventory, reservations, payment holds or carrier bookings, and never rolls back a change. The one write is an escalation row, saved only after the analyst confirms it.

- Design decisions: [`../../02-Retail-Order-Exception-Supply-Chain-Control-Tower.md`](../../02-Retail-Order-Exception-Supply-Chain-Control-Tower.md) (decision matrix and Gates 1–14)
- How it fits together: [`../architecture.md`](../architecture.md) (diagrams, request flow, failure paths)
- Submission documents (architecture, decision sheet, evaluation report, production readiness, demo) sit one level up, in [`capstone-submissions/`](../); this folder holds only what is needed to run the system.

---

## Status

Built, run on GCP and evaluated (2026-11-23 and 24). **142 offline tests pass** (`python -m pytest -q tests`).

| Step | What | Status |
|---|---|---|
| 1 | Sample data, answer key, golden questions (`data/`) | ✅ |
| 2 | Load: BigQuery tables, document register, docs bucket (`scripts/load_data.py`) | ✅ run on GCP: 6 tables, 13 PDFs, 12 checks pass |
| 3 | Ingest: register → bucket → Document AI (OCR) → section chunks → embeddings (`scripts/ingest_docs.py`) | ✅ run on GCP: 62 chunks, 4 search probes pass |
| 4 | Retrieval: hybrid (dense + exact codes) + RRF + rerank, current versions from the register, whole document to the model (`orchestrator/retrieval/`) | ✅ Gates 2–5 measured: hit@1 0.917, hit@5 1.0 |
| 5 | Harness on both services: correlation ID, masking, trace, blocking budgets, allowlist, citation check (`common/harness/`) | ✅ |
| 6 | Orchestrator tools (`orchestrator/tools/`) | ✅ |
| 7 | Fulfilment Specialist over A2A; its verdict and numbers are set by code (`fulfilment_specialist/`) | ✅ correlation ID confirmed across both services on GCP |
| 8 | Orchestrator agent, A2A client, **answer guard** (code checks the OUTCOME / CAUSE / FULFILABLE header against the trace) | ✅ |
| 9 | Sessions (SQLite), signed analyst token on every API call, web app (`web/`) | ✅ |
| 10 | Evaluation: golden-set runner with a pass/fail gate, retrieval experiments, scoring (`evals/`) | ✅ run on GCP, 7 end-to-end runs; safety checks 1.0 in the last three; quality checks vary run to run (see `../evaluation_report.md`) |
| 11 | Submission docs (one level up) | ✅ demo recording pending |

## Submission checklist

| Required | File / folder | Status |
|---|---|---|
| README | `README.md` | ✅ |
| Architecture + diagram | `../architecture.md` (Mermaid diagrams inside) | ✅ |
| Completed decision sheet | `../decision_sheet.md` (+ the capstone design doc) | ✅ |
| Evaluation report | `../evaluation_report.md` | ✅ retrieval experiments and end-to-end runs |
| setup.sh, requirements, lab.env.example | `setup.sh`, `requirements.txt` + `requirements.lock` (exact tested versions), `lab.env.example` | ✅ |
| Code | `scripts/`, `common/`, `orchestrator/`, `fulfilment_specialist/`, `web/` | ✅ |
| Tests / evals | `tests/` (offline), `evals/`, `data/golden_questions.jsonl` | ✅ |
| Sample data / instructions | `data/` + "What's in data/" and "Run order" below | ✅ |
| Working web experience | `web/` | ✅ |
| 5-minute demo | `../demo.md` | ✅ script; recording pending |
| One-page production-readiness assessment | `../production_readiness.md` | ✅ |

---

## Folder structure

```text
retail-control-tower/
├── README.md                     this file (submission documents are one level up, in capstone-submissions/)
├── setup.sh                      venv, install, check gcloud auth (creates no cloud resources)
├── requirements.txt              version ranges
├── requirements.lock             exact tested versions (setup.sh installs these)
├── lab.env.example               every setting, no secrets
├── .gitignore                    lab.env, output/, .venv/
│
├── data/                         sample data (see "What's in data/")
│
├── scripts/                      run by hand, not part of the services
│   ├── load_data.py              truncate + load BigQuery tables, register and the docs bucket; verify
│   ├── ingest_docs.py            register → bucket → Document AI Layout Parser (OCR) → chunks → embeddings → doc_chunks
│   └── check_gcp.py              read-only preflight before a demo or eval run
│
├── common/                       shared by BOTH services; no agent logic
│   ├── config.py                 reads lab.env, validates it
│   ├── utils.py                  log(), fail(), parse_utc() for scripts
│   ├── inputs.py                 one definition of valid IDs and numbers, for every tool
│   ├── results.py                one result contract for every tool (status, evidence ID, source time, freshness)
│   ├── freshness.py              fresh / stale and hour arithmetic, decided in code
│   ├── masking.py                mask before logging; pseudonymous IDs
│   ├── clients.py                cloud clients built once, retry on transient errors, refuse under tests
│   └── harness/                  ADK plugin on both Runners
│       ├── context.py            RequestContext: correlation ID + user, from RunConfig or A2A metadata
│       ├── policy.py             budgets from config
│       ├── trace.py              per-invocation trace (session 13 events + evidence, citations, details)
│       ├── plugin.py             HarnessPlugin: fail closed, blocking budgets, allowlist, masking, citation check
│       ├── logs.py               masked JSON lines per service (output/logs, output/traces)
│       └── report.py             readable report of a trace (terminal runner)
│
├── orchestrator/                 service 1 (with the web app): Order Exception Orchestrator
│   ├── order_exception_agent/    agent.py: instruction, answer format, tools, App(plugins, compaction)
│   ├── tools/                    orders, events (carrier, warehouse, changes, before/after), knowledge,
│   │                             escalation (needs confirmation), preferences (user: state)
│   ├── retrieval/                search (hybrid + RRF + rerank + register check), embeddings, cache
│   ├── a2a_client.py             check_fulfilment: the specialist as one tool; timeout → "unavailable"
│   ├── answer_guard.py           code checks the answer's OUTCOME / CAUSE / FULFILABLE against the trace
│   ├── runtime.py                Runner + sessions; correlation ID per message; confirmations; request deadline
│   ├── sessions.py               DatabaseSessionService (SQLite) or Vertex AI sessions
│   ├── identity.py               training identity → pseudonymous analyst ID + signed token
│   └── cli.py                    terminal runner with the trace report (use instead of adk web)
│
├── fulfilment_specialist/        service 2: own process and port; imports nothing from orchestrator/
│   ├── fulfilment_agent/         agent.py (agent, harness, A2A app), reply.py (code sets the verdict),
│   │                             schema.py (reply contract), card.py (one-skill Agent Card)
│   ├── tools/                    inventory.py: order line, inventory, reservations, stock elsewhere
│   └── server.py                 python -m fulfilment_specialist.server
│
├── web/                          FastAPI app (api.py, server.py) + static/index.html
│
├── evals/                        cost money, run on purpose
│   ├── run_evals.py              the 34 golden cases through the real system
│   ├── retrieval_eval.py         Gates 2–5 experiments (chunk size, dimension, legs, rerank)
│   └── scoring.py                deterministic checks (+ optional judge for free-text phrases)
│
├── tests/                        offline, free, every change (scripted model, fake BigQuery/Storage/Document AI)
│
└── output/                       created at runtime, git-ignored: logs, traces, caches, parsed docs, sessions, evals
```

### Where each part comes from

| Folder | Earlier module | Production additions here |
|---|---|---|
| `data/` | s8 metadata + eval set, s13/s19 `data/` | Regenerates with fresh times, answer key, Gate 13 categories, PDFs + register |
| `scripts/` | s8 `00_provision`, `01_load_tables`, `02_parse`, `03_embed_and_load` | Rerunnable, `--dry-run`, verify at the end, register as the allowlist |
| `common/harness/` | s13 `app/harness/` + `callbacks.py` | One plugin on both Runners; fails closed; budgets block; masking; citation check |
| `orchestrator/` | s19 `customer_orchestrator/`, s13/s17 `app/agent` | Fixed answer format, routing rules, specialist as a tool with a partial-answer path |
| `orchestrator/tools/` | s13 `enterprise/tools` + `errors` | Source time and freshness on every result, evidence IDs, confirmed write |
| `orchestrator/retrieval/` | s8 `rag_runtime` | Hybrid with RRF, register checked at question time, versioned cache keys |
| `orchestrator/runtime.py`, `sessions.py`, `identity.py` | s17 `runtime`, `services`, `identity` | Correlation ID per message, confirmation flow |
| `fulfilment_specialist/` | s19 `01_fulfilment_specialist/` | BigQuery, reply contract, own harness, hand-built Agent Card |
| `web/` | s17 `api`, `server`, `web/static` | Investigation inspector, escalation confirmation |
| `evals/`, `tests/` | s8 `06_evaluate`, `eval_scoring`, `tests/*_offline` | Trajectory, A2A, session and cache cases; scripted-model tests |

### Rules the structure enforces

1. **The specialist never imports from `orchestrator/`.** They talk only over A2A (a test checks this).
2. **`common/` has no agent logic.** Config, the result contract, freshness, masking, clients and the harness.
3. **Retrieval is a tool inside the orchestrator, not an agent.** `scripts/ingest_docs.py` writes the chunks; `orchestrator/retrieval/` only reads them.
4. **`tests/` and `evals/` are separate.** Tests are free and run on every change; evals call Gemini and BigQuery and run on purpose.

---

## What's in `data/`

| Path | What it is |
|---|---|
| `generate_data.py` | Writes the 5 tables with times relative to the run (T). Same rows every run; checks the planted facts. `--as-of <UTC time>` fixes T. |
| `tables/*.csv` | orders (24), inventory (17), carrier_events (25), warehouse_events (4), change_log (4) |
| `tables/manifest.json` | T and row counts for the last run |
| `schemas/*.json` | BigQuery schema for each table |
| `scenarios.md` | Answer key: S1–S12, evidence, right answer, what must not be concluded |
| `golden_questions.jsonl` | 34 Gate 13 cases (10 answerable, 5 insufficient, 5 exact ID, 5 paraphrase, 3 delegation, 2 remote failure, 2 session isolation, 2 stale cache) |
| `build_docs.py` | Renders `docs_source/` into the PDFs and the document register; deterministic. Run only when a source document changes. |
| `docs_source/**/*.md` | Authoring source of the runbooks and postmortems. Never uploaded. |
| `docs/runbooks/*.pdf` | 6 current runbooks + RB-ALLOC-002 v2 (superseded) |
| `docs/postmortems/*.pdf` | 6 postmortems, including the trap (PM-2026-009) and the genuine hint (PM-2026-017). PM-2025-052 is an **image-only scan**: Document AI must run OCR. |
| `docs/document_register.csv` | One row per document version. **Metadata comes from here, not the file**, and it is the upload allowlist. Loaded to BigQuery as `document_register`. |

Sensitive fields (customer name, phone, address, payment status) exist only in `orders`. No document contains customer details, and no tool returns name, phone or address.

---

## Setup (once)

```bash
cp lab.env.example lab.env        # then set IDENTITY_SALT to any random string
bash setup.sh                     # venv, install, gcloud checks
gcloud auth application-default login
```

## Run order

Run from `retail-control-tower/`, after `source .venv/bin/activate && source lab.env`.

| Step | Command | Needs GCP | How often |
|---|---|---|---|
| 0 | `python data/build_docs.py` | No | Only when a document in `data/docs_source/` changes |
| 1 | `python data/generate_data.py` | No | Before each test or demo session |
| 2 | `python -m scripts.load_data` | Yes | Right after step 1 |
| 3 | `python -m scripts.ingest_docs` | Yes | When docs, chunking or the embedding model change |
| 4 | `python -m fulfilment_specialist.server` | Yes | Terminal 1, each session |
| 5 | `python -m web.server` → http://127.0.0.1:8080 | Yes | Terminal 2, each session |
| 6 | `python -m scripts.check_gcp` | Yes (read-only) | Before a demo or eval run |
| 7 | `python -m evals.retrieval_eval` and `python -m evals.run_evals` | Yes | After any change |
| — | `python -m orchestrator.cli -q "Investigate ORD-78421."` | Yes | Debugging (prints the trace report) |
| — | `python -m pytest -q tests` | No | Every change |

Every script in `scripts/` follows the same contract: safe to rerun, has `--dry-run` (except the read-only check), verifies its own result at the end, and stops with a clear error. Script names are verb + object, with no numbers; this table holds the order.

**Freshness window:** fresh rows are minutes old at T and stale rows are 2 days old. With `ORDER_MAX_AGE_MINUTES` and `INVENTORY_MAX_AGE_MINUTES` at 300, one load covers about 4 h 50 min of testing; after that, run steps 1 and 2 again.

**Why not `adk web`?** The harness refuses any request without a correlation ID (fail closed), and ADK Web doesn't send one. Use the web app or the terminal runner.

## Following one request

```bash
grep <correlation ID from the UI> output/logs/*.jsonl output/traces/*.jsonl
```

The same ID appears in the web app's orchestrator logs, the A2A call, and the specialist's own tool calls.
