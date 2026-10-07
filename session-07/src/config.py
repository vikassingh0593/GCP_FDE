"""Central configuration for Project 1.

The lab intentionally reads configuration from environment variables so the
same source code can run in different participant projects without edits.
"""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
STATE_DIR = ROOT / ".state"
DATA_DIR = ROOT / "data"

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
DOCUMENT_AI_LOCATION = os.getenv("DOCUMENT_AI_LOCATION", "us")
VERTEX_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
EMBEDDING_LOCATION = os.getenv("EMBEDDING_LOCATION", "us-central1")
BIGQUERY_LOCATION = os.getenv("BIGQUERY_LOCATION", "US")

GCS_BUCKET = os.environ["GCS_BUCKET"]
BQ_DATASET = os.getenv("BQ_DATASET", "tredence_rag_prod")
BQ_TABLE = os.getenv("BQ_TABLE", "chunks")

PROCESSOR_NAME = os.getenv("DOCUMENT_AI_PROCESSOR_NAME", "tredence-rag-layout-parser")
PROCESSOR_ID_FILE = ROOT / os.getenv(
    "DOCUMENT_AI_PROCESSOR_ID_FILE",
    ".state/document_ai_processor_id",
)
PROCESSOR_VERSION = os.getenv(
    "DOCUMENT_AI_PROCESSOR_VERSION",
    "pretrained-layout-parser-v1.5-2025-08-25",
)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gemini-2.5-flash")
RANKING_MODEL = os.getenv("RANKING_MODEL", "semantic-ranker-default@latest")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
INCLUDE_ANCESTOR_HEADINGS = os.getenv(
    "INCLUDE_ANCESTOR_HEADINGS", "true"
).lower() == "true"

SOURCE_PDF = DATA_DIR / "Aurelia_Retail_AI_Operations_Report.pdf"
GCS_SOURCE_URI = f"gs://{GCS_BUCKET}/{SOURCE_PDF.name}"
