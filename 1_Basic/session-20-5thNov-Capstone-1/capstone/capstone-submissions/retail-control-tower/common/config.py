"""Central configuration for the Retail Order Exception Control Tower.

The only place that reads lab.env. Scripts, both agents, the web app and the
tests import their settings from here; nothing else calls os.environ.

Rules:
- Run `source lab.env` first. Required values (project, bucket, dataset) have
  no default, so a missing lab.env fails at import instead of writing to the
  wrong dataset.
- No cloud clients and no printing here: importing config must be instant and
  offline, so tests never touch the cloud by accident.
- IDENTITY_SALT is read here but never logged; summary() leaves it out.
"""

from __future__ import annotations

import os
from pathlib import Path


# -----------------------------------------------------------------------------
# Readers: every value is converted once, and a bad value names its setting
# -----------------------------------------------------------------------------

def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"lab.env: {name} is not set. Run `source lab.env` from retail-control-tower/.")
    return value


def _str(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"lab.env: {name} must be a whole number, got {raw!r}") from None


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"lab.env: {name} must be a number, got {raw!r}") from None


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    raise SystemExit(f"lab.env: {name} must be true or false, got {raw!r}")


# -----------------------------------------------------------------------------
# Paths: built from ROOT, so code works from any working directory
# -----------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]          # retail-control-tower/

DATA_DIR = ROOT / "data"
TABLES_DIR = DATA_DIR / "tables"                     # CSVs written by generate_data.py
SCHEMAS_DIR = DATA_DIR / "schemas"                   # BigQuery schema per table
DOCS_DIR = DATA_DIR / "docs"                         # runbook and postmortem PDFs (the only files uploaded)
DOCUMENT_REGISTER_FILE = DOCS_DIR / "document_register.csv"   # metadata per document: the upload allowlist
MANIFEST_FILE = TABLES_DIR / "manifest.json"         # T and row counts of the last generate run
GOLDEN_QUESTIONS_FILE = DATA_DIR / "golden_questions.jsonl"  # answer key: never uploaded

OUTPUT_DIR = (ROOT / _str("OUTPUT_DIR", "output")).resolve()   # logs, escalations, eval results
LOGS_DIR = OUTPUT_DIR / "logs"        # masked JSON lines, one file per service
TRACES_DIR = OUTPUT_DIR / "traces"    # one row per invocation, per service
CACHE_DIR = OUTPUT_DIR / "cache"      # query-embedding and retrieval caches
PARSED_DIR = OUTPUT_DIR / "parsed"    # Document AI results, keyed by file MD5 + parse settings
EVAL_DIR = OUTPUT_DIR / "eval"        # evaluation runs


# -----------------------------------------------------------------------------
# Project and locations
# -----------------------------------------------------------------------------

PROJECT_ID = _required("GOOGLE_CLOUD_PROJECT")
QUOTA_PROJECT_ID = _str("GOOGLE_CLOUD_QUOTA_PROJECT", PROJECT_ID)

VERTEX_LOCATION = _str("GOOGLE_CLOUD_LOCATION", "global")       # Gemini
EMBEDDING_LOCATION = _str("EMBEDDING_LOCATION", "us-central1")
BIGQUERY_LOCATION = _str("BIGQUERY_LOCATION", "US")
GCS_LOCATION = _str("GCS_LOCATION", "US")


# -----------------------------------------------------------------------------
# Cloud Storage: runbook and postmortem PDFs
# -----------------------------------------------------------------------------

GCS_BUCKET = _required("GCS_BUCKET")
GCS_DOCS_PREFIX = _str("GCS_DOCS_PREFIX", "docs").strip("/")


# -----------------------------------------------------------------------------
# Document AI: Layout Parser reads the PDFs (OCR for scans) and chunks them
# -----------------------------------------------------------------------------

DOCUMENT_AI_LOCATION = _str("DOCUMENT_AI_LOCATION", "us")                      # us | eu only
DOCUMENT_AI_PROCESSOR_NAME = _str("DOCUMENT_AI_PROCESSOR_NAME", "retail-control-tower-layout-parser-vks")
# Saved after the processor is created, so later runs reuse it (resolved against ROOT).
DOCUMENT_AI_PROCESSOR_ID_FILE = (ROOT / _str("DOCUMENT_AI_PROCESSOR_ID_FILE",
                                             "output/document_ai_processor_id")).resolve()
# Pinned, so parser output doesn't change between runs.
DOCUMENT_AI_PROCESSOR_VERSION = _str("DOCUMENT_AI_PROCESSOR_VERSION", "pretrained-layout-parser-v1.5-2025-08-25")
# Each chunk carries its section headings, e.g. "Carrier delay > Checks".
INCLUDE_ANCESTOR_HEADINGS = _bool("INCLUDE_ANCESTOR_HEADINGS", True)


# -----------------------------------------------------------------------------
# BigQuery
# -----------------------------------------------------------------------------

BQ_DATASET = _required("BQ_DATASET")

# Operational tables: read live by the tools, never embedded.
# Keys = the CSV and schema file names in data/; values = BigQuery table names.
# The loader loops over this, so adding a table is one line here.
OPERATIONAL_TABLES: dict[str, str] = {
    "orders": _str("BQ_ORDERS_TABLE", "orders"),
    "inventory": _str("BQ_INVENTORY_TABLE", "inventory"),
    "carrier_events": _str("BQ_CARRIER_EVENTS_TABLE", "carrier_events"),
    "warehouse_events": _str("BQ_WAREHOUSE_EVENTS_TABLE", "warehouse_events"),
    "change_log": _str("BQ_CHANGE_LOG_TABLE", "change_log"),
}

# Document register: one row per runbook/postmortem version (ID, version, status, dates).
# Metadata comes from here, never from the file (KN-01).
BQ_DOCUMENT_REGISTER_TABLE = _str("BQ_DOCUMENT_REGISTER_TABLE", "document_register")
# Knowledge: runbook and postmortem chunks with embeddings and metadata.
BQ_DOC_CHUNKS_TABLE = _str("BQ_DOC_CHUNKS_TABLE", "doc_chunks")
# Hand-offs to an analyst (append-only).
BQ_ESCALATIONS_TABLE = _str("BQ_ESCALATIONS_TABLE", "escalations")


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

ORCHESTRATOR_MODEL = _str("ORCHESTRATOR_MODEL", "gemini-3.1-flash-lite")
SPECIALIST_MODEL = _str("SPECIALIST_MODEL", "gemini-3.1-flash-lite")
EMBEDDING_MODEL = _str("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = _int("EMBEDDING_DIMENSION", 768)            # Gate 3
RANKING_MODEL = _str("RANKING_MODEL", "semantic-ranker-default@latest")
# Grades the free-text phrases in evals (evals/ only, never in the request path).
EVAL_JUDGE_MODEL = _str("EVAL_JUDGE_MODEL", ORCHESTRATOR_MODEL)


# -----------------------------------------------------------------------------
# Retrieval (Gates 2, 4, 5, 12)
# -----------------------------------------------------------------------------

CHUNK_SIZE = _int("CHUNK_SIZE", 512)                       # Gate 2
TOP_K = _int("TOP_K", 20)                                  # candidates from BigQuery
TOP_N = _int("TOP_N", 5)                                   # kept after reranking, sent to Gemini
MIN_RELEVANCE_SCORE = _float("MIN_RELEVANCE_SCORE", 0.3)   # below this: no evidence, abstain
GROUNDING_THRESHOLD = _float("GROUNDING_THRESHOLD", 0.6)   # Check Grounding minimum support


# -----------------------------------------------------------------------------
# Freshness (Gate 1): older than this = stale, never used as current evidence
# -----------------------------------------------------------------------------

ORDER_MAX_AGE_MINUTES = _int("ORDER_MAX_AGE_MINUTES", 300)
INVENTORY_MAX_AGE_MINUTES = _int("INVENTORY_MAX_AGE_MINUTES", 300)
CARRIER_SILENCE_HOURS = _int("CARRIER_SILENCE_HOURS", 48)


# -----------------------------------------------------------------------------
# Cache (Gate 10): inventory and the final answer are never cached
# -----------------------------------------------------------------------------

ORDER_CACHE_TTL_SECONDS = _int("ORDER_CACHE_TTL_SECONDS", 0)
RETRIEVAL_CACHE_TTL_SECONDS = _int("RETRIEVAL_CACHE_TTL_SECONDS", 86400)
QUERY_EMBEDDING_CACHE_TTL_SECONDS = _int("QUERY_EMBEDDING_CACHE_TTL_SECONDS", 2592000)


# -----------------------------------------------------------------------------
# Harness budgets (Gate 11): per invocation, enforced in code
# -----------------------------------------------------------------------------

MAX_MODEL_CALLS_PER_INVOCATION = _int("MAX_MODEL_CALLS_PER_INVOCATION", 8)
MAX_TOOL_CALLS_PER_INVOCATION = _int("MAX_TOOL_CALLS_PER_INVOCATION", 10)
MAX_SAME_TOOL_CALLS = _int("MAX_SAME_TOOL_CALLS", 3)
MAX_FAILURES_PER_INVOCATION = _int("MAX_FAILURES_PER_INVOCATION", 2)
MAX_INVOCATION_SECONDS = _int("MAX_INVOCATION_SECONDS", 90)


# -----------------------------------------------------------------------------
# Services and A2A
# -----------------------------------------------------------------------------

APP_NAME = _str("APP_NAME", "retail_control_tower_vks")

WEB_HOST = _str("WEB_HOST", "127.0.0.1")
WEB_PORT = _int("WEB_PORT", 8080)

FULFILMENT_AGENT_HOST = _str("FULFILMENT_AGENT_HOST", "127.0.0.1")
FULFILMENT_AGENT_PORT = _int("FULFILMENT_AGENT_PORT", 8001)
FULFILMENT_AGENT_CARD_URL = _str(
    "FULFILMENT_AGENT_CARD_URL",
    f"http://{FULFILMENT_AGENT_HOST}:{FULFILMENT_AGENT_PORT}/.well-known/agent-card.json",
)
FULFILMENT_TIMEOUT_SECONDS = _int("FULFILMENT_TIMEOUT_SECONDS", 30)


# -----------------------------------------------------------------------------
# Sessions and identity (Gate 8)
# -----------------------------------------------------------------------------

SESSION_BACKEND = _str("SESSION_BACKEND", "local_sqlite")       # local_sqlite | vertex
SESSION_DB_FILE = (ROOT / _str("SESSION_DB_FILE", "output/sessions.db")).resolve()
# Only for SESSION_BACKEND=vertex (production step): the Agent Engine that holds sessions.
VERTEX_AGENT_ENGINE_ID = _str("VERTEX_AGENT_ENGINE_ID", "")
AGENT_ENGINE_LOCATION = _str("AGENT_ENGINE_LOCATION", "us-central1")

# Context budget (Gate 9): after this many turns, older turns are summarized
# (evidence values are kept word for word); the last COMPACTION_OVERLAP turns stay as they are.
COMPACTION_INTERVAL = _int("COMPACTION_INTERVAL", 4)
COMPACTION_OVERLAP = _int("COMPACTION_OVERLAP", 1)

LAB_ENVIRONMENT = _str("LAB_ENVIRONMENT", "training")
IDENTITY_SALT = _required("IDENTITY_SALT")                      # never logged


# -----------------------------------------------------------------------------
# Checks: a typo in lab.env fails here, not halfway through a demo
# -----------------------------------------------------------------------------

def _check() -> None:
    problems: list[str] = []

    if IDENTITY_SALT == "replace-with-any-random-string":
        problems.append("IDENTITY_SALT still has the example value; set any random string")
    if EMBEDDING_DIMENSION not in (768, 1536, 3072):
        problems.append(f"EMBEDDING_DIMENSION must be 768, 1536 or 3072, got {EMBEDDING_DIMENSION}")
    if not 1 <= TOP_N <= TOP_K:
        problems.append(f"need 1 <= TOP_N <= TOP_K, got TOP_N={TOP_N}, TOP_K={TOP_K}")
    if CHUNK_SIZE <= 0:
        problems.append(f"CHUNK_SIZE must be positive, got {CHUNK_SIZE}")
    for name, value in (("MIN_RELEVANCE_SCORE", MIN_RELEVANCE_SCORE), ("GROUNDING_THRESHOLD", GROUNDING_THRESHOLD)):
        if not 0.0 <= value <= 1.0:
            problems.append(f"{name} must be between 0 and 1, got {value}")
    for name, value in (("WEB_PORT", WEB_PORT), ("FULFILMENT_AGENT_PORT", FULFILMENT_AGENT_PORT)):
        if not 1 <= value <= 65535:
            problems.append(f"{name} must be a port between 1 and 65535, got {value}")
    if WEB_PORT == FULFILMENT_AGENT_PORT and WEB_HOST == FULFILMENT_AGENT_HOST:
        problems.append("WEB_PORT and FULFILMENT_AGENT_PORT must differ: they are separate services")
    if DOCUMENT_AI_LOCATION not in ("us", "eu"):
        problems.append(f"DOCUMENT_AI_LOCATION must be us or eu (where Layout Parser runs), got {DOCUMENT_AI_LOCATION!r}")
    if not DOCUMENT_AI_PROCESSOR_VERSION.startswith("pretrained-layout-parser"):
        problems.append(f"DOCUMENT_AI_PROCESSOR_VERSION must be a pinned Layout Parser version, "
                        f"got {DOCUMENT_AI_PROCESSOR_VERSION!r}")
    if SESSION_BACKEND not in ("local_sqlite", "vertex"):
        problems.append(f"SESSION_BACKEND must be local_sqlite or vertex, got {SESSION_BACKEND!r}")
    if SESSION_BACKEND == "vertex" and not VERTEX_AGENT_ENGINE_ID:
        problems.append("SESSION_BACKEND=vertex needs VERTEX_AGENT_ENGINE_ID")
    if not 0 <= COMPACTION_OVERLAP < COMPACTION_INTERVAL:
        problems.append(f"need 0 <= COMPACTION_OVERLAP < COMPACTION_INTERVAL, "
                        f"got {COMPACTION_OVERLAP} and {COMPACTION_INTERVAL}")
    for name, value in (
        ("ORDER_MAX_AGE_MINUTES", ORDER_MAX_AGE_MINUTES),
        ("INVENTORY_MAX_AGE_MINUTES", INVENTORY_MAX_AGE_MINUTES),
        ("CARRIER_SILENCE_HOURS", CARRIER_SILENCE_HOURS),
        ("MAX_MODEL_CALLS_PER_INVOCATION", MAX_MODEL_CALLS_PER_INVOCATION),
        ("MAX_TOOL_CALLS_PER_INVOCATION", MAX_TOOL_CALLS_PER_INVOCATION),
        ("MAX_SAME_TOOL_CALLS", MAX_SAME_TOOL_CALLS),
        ("MAX_INVOCATION_SECONDS", MAX_INVOCATION_SECONDS),
        ("FULFILMENT_TIMEOUT_SECONDS", FULFILMENT_TIMEOUT_SECONDS),
    ):
        if value <= 0:
            problems.append(f"{name} must be positive, got {value}")
    for name, value in (
        ("ORDER_CACHE_TTL_SECONDS", ORDER_CACHE_TTL_SECONDS),
        ("RETRIEVAL_CACHE_TTL_SECONDS", RETRIEVAL_CACHE_TTL_SECONDS),
        ("QUERY_EMBEDDING_CACHE_TTL_SECONDS", QUERY_EMBEDDING_CACHE_TTL_SECONDS),
        ("MAX_FAILURES_PER_INVOCATION", MAX_FAILURES_PER_INVOCATION),
    ):
        if value < 0:
            problems.append(f"{name} cannot be negative, got {value}")
    if FULFILMENT_TIMEOUT_SECONDS >= MAX_INVOCATION_SECONDS:
        problems.append("FULFILMENT_TIMEOUT_SECONDS must be below MAX_INVOCATION_SECONDS, "
                        "or a slow specialist uses the whole budget before the partial answer")

    if problems:
        raise SystemExit("lab.env has invalid settings:\n  - " + "\n  - ".join(problems))


_check()


# -----------------------------------------------------------------------------
# Helpers, so no other file builds these strings by hand
# -----------------------------------------------------------------------------

def table_id(table: str) -> str:
    """Fully qualified BigQuery table ID: project.dataset.table."""
    return f"{PROJECT_ID}.{BQ_DATASET}.{table}"


def dataset_id() -> str:
    """Fully qualified BigQuery dataset ID: project.dataset."""
    return f"{PROJECT_ID}.{BQ_DATASET}"


def gcs_doc_path(local_path: Path) -> str:
    """Object name in the bucket for a file under data/docs/, e.g. docs/runbooks/rb-car-003-carrier-delay.pdf.

    Pure path arithmetic: the file doesn't need to exist locally, so ingest_docs
    (which reads from the bucket) uses the same naming rule as load_data.
    """
    relative = Path(local_path).resolve().relative_to(DOCS_DIR.resolve())
    return f"{GCS_DOCS_PREFIX}/{relative.as_posix()}"


def gcs_uri(object_name: str) -> str:
    """gs:// address of an object in the bucket."""
    return f"gs://{GCS_BUCKET}/{object_name}"


def summary() -> dict:
    """Non-sensitive settings for startup logs and the evaluation report. Never includes IDENTITY_SALT."""
    return {
        "project": PROJECT_ID,
        "dataset": BQ_DATASET,
        "bucket": GCS_BUCKET,
        "docs_prefix": GCS_DOCS_PREFIX,
        "locations": {"vertex": VERTEX_LOCATION, "embedding": EMBEDDING_LOCATION,
                      "bigquery": BIGQUERY_LOCATION, "gcs": GCS_LOCATION, "document_ai": DOCUMENT_AI_LOCATION},
        "document_ai": {"processor": DOCUMENT_AI_PROCESSOR_NAME, "version": DOCUMENT_AI_PROCESSOR_VERSION,
                        "ancestor_headings": INCLUDE_ANCESTOR_HEADINGS},
        "models": {"orchestrator": ORCHESTRATOR_MODEL, "specialist": SPECIALIST_MODEL,
                   "embedding": f"{EMBEDDING_MODEL}@{EMBEDDING_DIMENSION}", "ranking": RANKING_MODEL},
        "retrieval": {"chunk_size": CHUNK_SIZE, "top_k": TOP_K, "top_n": TOP_N,
                      "min_relevance": MIN_RELEVANCE_SCORE, "grounding_threshold": GROUNDING_THRESHOLD},
        "freshness": {"order_max_age_min": ORDER_MAX_AGE_MINUTES,
                      "inventory_max_age_min": INVENTORY_MAX_AGE_MINUTES,
                      "carrier_silence_h": CARRIER_SILENCE_HOURS},
        "budgets": {"model_calls": MAX_MODEL_CALLS_PER_INVOCATION, "tool_calls": MAX_TOOL_CALLS_PER_INVOCATION,
                    "same_tool": MAX_SAME_TOOL_CALLS, "failures": MAX_FAILURES_PER_INVOCATION,
                    "seconds": MAX_INVOCATION_SECONDS},
        "services": {"web": f"{WEB_HOST}:{WEB_PORT}", "specialist_card": FULFILMENT_AGENT_CARD_URL,
                     "specialist_timeout_s": FULFILMENT_TIMEOUT_SECONDS},
        "sessions": SESSION_BACKEND,
        "compaction": {"interval": COMPACTION_INTERVAL, "overlap": COMPACTION_OVERLAP},
        "environment": LAB_ENVIRONMENT,
    }
