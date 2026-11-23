#!/usr/bin/env bash

# ---------- REQUIRED ----------
export GOOGLE_CLOUD_PROJECT="tredence-fde-1"

# ---------- LOCATIONS ----------
# Document AI processors use regional locations such as us/eu.
export DOCUMENT_AI_LOCATION="us"

# Vertex generation can use global. Embeddings use us-central1 in this lab.
export GOOGLE_CLOUD_LOCATION="global"
export EMBEDDING_LOCATION="us-central1"

# BigQuery dataset location.
export BIGQUERY_LOCATION="US"

# ---------- RESOURCE NAMES ----------
export GCS_BUCKET="${GOOGLE_CLOUD_PROJECT}-tredence-rag-lab"
export BQ_DATASET="tredence_rag_prod"
export BQ_TABLE="chunks"
export DOCUMENT_AI_PROCESSOR_NAME="tredence-rag-layout-parser"

# setup.sh writes the created processor ID here.
export DOCUMENT_AI_PROCESSOR_ID_FILE=".state/document_ai_processor_id"

# ---------- MODELS ----------
export EMBEDDING_MODEL="gemini-embedding-001"
export EMBEDDING_DIMENSION="768"
export GENERATION_MODEL="gemini-2.5-flash"
export RANKING_MODEL="semantic-ranker-default@latest"

# Current documented Layout Parser processor version used by this lab.
export DOCUMENT_AI_PROCESSOR_VERSION="pretrained-layout-parser-v1.5-2025-08-25"

# ---------- CHUNKING ----------
export CHUNK_SIZE="256"
export INCLUDE_ANCESTOR_HEADINGS="true"

# Google Gen AI SDK uses Vertex AI.
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
