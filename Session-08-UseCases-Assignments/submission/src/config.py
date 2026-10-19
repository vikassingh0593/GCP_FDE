"""Central configuration for MedEvidence.

Every pipeline script and the ADK harness import their settings from here
instead of hard-coding them. Values come from env.sh (run `source env.sh`
first), so the same code runs in another project by editing one file.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path


# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

# The submission/ folder. Every path is built from it, so scripts work from
# any working directory.
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"              # parsed chunks (JSON) for inspection
STATE_DIR = ROOT / ".state"               # IDs of resources created once
DEMO_OUTPUTS_DIR = ROOT / "demo_outputs"  # one trace file per demo question


# -----------------------------------------------------------------------------
# Project and locations
# -----------------------------------------------------------------------------

# os.environ[...] rather than os.getenv on purpose: if env.sh was not sourced,
# fail immediately instead of running against the wrong project.
PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

DOCUMENT_AI_LOCATION = os.getenv("DOCUMENT_AI_LOCATION", "us")
VERTEX_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
EMBEDDING_LOCATION = os.getenv("EMBEDDING_LOCATION", "us-central1")
BIGQUERY_LOCATION = os.getenv("BIGQUERY_LOCATION", "US")


# -----------------------------------------------------------------------------
# Cloud Storage: holds the original files that Document AI reads
# -----------------------------------------------------------------------------

GCS_BUCKET = os.environ["GCS_BUCKET"]
GCS_RAW_PREFIX = os.getenv("GCS_RAW_PREFIX", "raw")


# -----------------------------------------------------------------------------
# BigQuery: one dataset, three tables
# -----------------------------------------------------------------------------

BQ_DATASET = os.getenv("BQ_DATASET", "medevidence_v1_vks")
BQ_CHUNKS_TABLE = os.getenv("BQ_CHUNKS_TABLE", "chunks")
BQ_DOCUMENTS_TABLE = os.getenv("BQ_DOCUMENTS_TABLE", "documents")
BQ_AE_TABLE = os.getenv("BQ_AE_TABLE", "adverse_events")


# -----------------------------------------------------------------------------
# Document AI Layout Parser: turns PDFs and DOCX into structured chunks
# -----------------------------------------------------------------------------

PROCESSOR_NAME = os.getenv(
    "DOCUMENT_AI_PROCESSOR_NAME",
    "medevidence-layout-parser-vks",
)
PROCESSOR_ID_FILE = ROOT / os.getenv(
    "DOCUMENT_AI_PROCESSOR_ID_FILE",
    ".state/document_ai_processor_id",
)
PROCESSOR_VERSION = os.getenv(
    "DOCUMENT_AI_PROCESSOR_VERSION",
    "pretrained-layout-parser-v1.5-2025-08-25",
)


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gemini-3.5-flash-lite")  # D69: the answer writer
# Answer writer: -1 = model decides (thinking on, D30 reversed); 0 = off.
GENERATION_THINKING_BUDGET = int(os.getenv("GENERATION_THINKING_BUDGET", "-1"))
# The ADK agent's model (routing); keeps its default thinking.
AGENT_MODEL = os.getenv("AGENT_MODEL", "gemini-3.1-flash-lite")  # D69
# The patient-case classifier, the second signal next to the word patterns (D70).
PATIENT_CHECK_MODEL = os.getenv("PATIENT_CHECK_MODEL", "gemini-3.1-flash-lite")
PATIENT_CHECK_THINKING_BUDGET = int(os.getenv("PATIENT_CHECK_THINKING_BUDGET", "0"))
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "MedEvidence")
ORGANISATION = os.getenv("ORGANISATION", "Medical Affairs")
RANKING_MODEL = os.getenv("RANKING_MODEL", "semantic-ranker-default@latest")


# -----------------------------------------------------------------------------
# Chunking (Layout Parser built-in; see the reasoning in env.sh)
# -----------------------------------------------------------------------------

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
INCLUDE_ANCESTOR_HEADINGS = os.getenv(
    "INCLUDE_ANCESTOR_HEADINGS", "true"
).lower() == "true"


# -----------------------------------------------------------------------------
# Corpus
# -----------------------------------------------------------------------------

# Resolved against ROOT, not the current directory.
CORPUS_DIR = (
    ROOT / os.getenv("CORPUS_DIR", "../Data-Corpus-v1/01-MedEvidence-Large-Corpus")
).resolve()

# Structured data: loaded as BigQuery tables, never embedded.
DOCUMENT_REGISTRY_CSV = CORPUS_DIR / "document_registry.csv"
AE_REGISTRY_CSV = CORPUS_DIR / "adverse_event_registry.csv"

# Our own metadata files (in submission/, never in the corpus folder):
SUPPLEMENT_CSV = ROOT / "metadata_supplement.csv"       # rows for files the registry lacks
OVERRIDES_CSV = ROOT / "metadata_overrides.csv"         # facts stated in a document but missing from the registry
CORPUS_EXPECTATIONS = ROOT / "corpus_expectations.json"  # golden facts the parse gate checks


def _registered_files() -> list[str]:
    """Allowlist = every file named in the registry or the supplement (D44).

    Only controlled documents are ever parsed and embedded. The corpus folder
    also holds TRAINER_GROUND_TRUTH.md (the answer key), README.md and
    CORPUS_SCALE_ESTIMATE.md: none is in the registry, so none can reach the
    index. A new document needs a registry row, not a code edit.
    """
    files: list[str] = []
    for path in (DOCUMENT_REGISTRY_CSV, SUPPLEMENT_CSV):
        if path.exists():
            with path.open(newline="", encoding="utf-8") as f:
                files += [r["filename"].strip() for r in csv.DictReader(f) if (r.get("filename") or "").strip()]
    return list(dict.fromkeys(files))  # keep order, drop duplicates


SOURCE_FILES = _registered_files()


# -----------------------------------------------------------------------------
# Retrieval sizes (§7): tunable without editing code
# -----------------------------------------------------------------------------

TOP_K = int(os.getenv("TOP_K", "20"))                              # candidates from BigQuery
TOP_N = int(os.getenv("TOP_N", "5"))                               # kept by the Ranking API
MAX_EVIDENCE_CHARS = int(os.getenv("MAX_EVIDENCE_CHARS", "24000"))  # ~6,000 tokens to Gemini
MAX_TABLE_ROWS = int(os.getenv("MAX_TABLE_ROWS", "25"))            # rows shown for a table request (D37)
MAX_SQL_BYTES = int(os.getenv("MAX_SQL_BYTES", str(100 * 1024 * 1024)))  # text-to-SQL scan cap (D49)
MAX_SQL_ROWS = int(os.getenv("MAX_SQL_ROWS", "100"))                  # text-to-SQL rows fetched (D49)
MAX_TOOL_CALLS_PER_TURN = int(os.getenv("MAX_TOOL_CALLS_PER_TURN", "3"))  # agent tool calls per turn (D51)
GROUNDING_THRESHOLD = float(os.getenv("GROUNDING_THRESHOLD", "0.6"))     # Check Grounding minimum support (D66)
BQ_ESCALATIONS_TABLE = os.getenv("BQ_ESCALATIONS_TABLE", "escalations")  # hand-off queue (D52)


# -----------------------------------------------------------------------------
# Helpers, so no script builds these strings by hand
# -----------------------------------------------------------------------------

def gcs_uri(filename: str) -> str:
    """Return the Cloud Storage URI of an original corpus file."""
    return f"gs://{GCS_BUCKET}/{GCS_RAW_PREFIX}/{filename}"


def table_id(table: str) -> str:
    """Return a fully qualified BigQuery table ID: project.dataset.table."""
    return f"{PROJECT_ID}.{BQ_DATASET}.{table}"
