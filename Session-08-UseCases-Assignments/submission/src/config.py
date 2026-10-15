"""Central configuration for MedEvidence.

Every pipeline script and the ADK harness import their settings from here
instead of hard-coding them. Values come from env.sh (run `source env.sh`
first), so the same code runs in another project by editing one file.
"""

from __future__ import annotations

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
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gemini-2.5-flash")
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

# Allowlist: only these files are ever parsed and embedded. The corpus folder
# also holds TRAINER_GROUND_TRUTH.md (the answer key), README.md and
# CORPUS_SCALE_ESTIMATE.md, which must never reach the index. A new document
# needs a one-line edit here until automatic ingestion replaces this list.
SOURCE_FILES = [
    "DE_AX17_Current_Label_v4.2.pdf",
    "DE_AX17_Superseded_Label_v3.8.pdf",
    "US_AX17_Prescribing_Information_v5.0.pdf",
    "HN-204_Clinical_Study.pdf",
    "HN-311_Clinical_Study.pdf",
    "HN-402_Clinical_Study.pdf",
    "DE_AX17_Historical_Scanned_Safety_Letters_2019_2021.pdf",
    "SB_AX17_2026_09_Safety_Bulletin.docx",
]

# Structured data: loaded as BigQuery tables, never embedded.
DOCUMENT_REGISTRY_CSV = CORPUS_DIR / "document_registry.csv"
AE_REGISTRY_CSV = CORPUS_DIR / "adverse_event_registry.csv"


# -----------------------------------------------------------------------------
# Helpers, so no script builds these strings by hand
# -----------------------------------------------------------------------------

def gcs_uri(filename: str) -> str:
    """Return the Cloud Storage URI of an original corpus file."""
    return f"gs://{GCS_BUCKET}/{GCS_RAW_PREFIX}/{filename}"


def table_id(table: str) -> str:
    """Return a fully qualified BigQuery table ID: project.dataset.table."""
    return f"{PROJECT_ID}.{BQ_DATASET}.{table}"
