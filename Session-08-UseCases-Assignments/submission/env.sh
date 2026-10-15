#!/usr/bin/env bash
# MedEvidence (Session 8, Challenge 01): settings for every script and the ADK agent.
# Usage, from submission/:  source env.sh
#
# Same standard and locations as session-07. Only the resource names are new;
# they end in "vks" so they are easy to spot in the shared course project.

# ---------- REQUIRED ----------
# Shared course project. Authentication comes from
# `gcloud auth application-default login`, so this file holds no secrets.
export GOOGLE_CLOUD_PROJECT="tredence-fde-1"

# ---------- LOCATIONS ----------
# Gemini (answers and the ADK agent). "global" routes each call to a region
# with capacity. ADK and the Gen AI SDK read this exact variable name.
export GOOGLE_CLOUD_LOCATION="global"

# Document AI is only offered in "us" or "eu".
export DOCUMENT_AI_LOCATION="us"

# Embedding model region, proven in session-07.
export EMBEDDING_LOCATION="us-central1"

# BigQuery dataset location; matches Document AI "us".
export BIGQUERY_LOCATION="US"

# Use Vertex AI with your gcloud login instead of an API key.
# Read by the Gen AI SDK and ADK.
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"

# ---------- RESOURCE NAMES ----------
# Cloud Storage: original corpus files go under raw/. Document AI reads its
# input from here, and any step can be re-run from the untouched original.
export GCS_BUCKET="${GOOGLE_CLOUD_PROJECT}-medevidence-vks"
export GCS_RAW_PREFIX="raw"

# BigQuery: our own dataset (dataset names allow underscores, not hyphens).
# Session-07's loader drops its table on every run, so we never share a
# dataset with it. Tables need no suffix: the dataset already marks them as ours.
export BQ_DATASET="medevidence_v1_vks"
export BQ_CHUNKS_TABLE="chunks"           # text chunks + embeddings, used for search
export BQ_DOCUMENTS_TABLE="documents"     # registry: status, country, version, dates, used for filters
export BQ_AE_TABLE="adverse_events"       # adverse-event rates: exact numbers, never embedded

# Document AI Layout Parser: created once by 00_provision.py, and its ID is
# cached in .state/ so every later run reuses the same processor.
export DOCUMENT_AI_PROCESSOR_NAME="medevidence-layout-parser-vks"
export DOCUMENT_AI_PROCESSOR_ID_FILE=".state/document_ai_processor_id"

# Pinned version, so parser output does not change between runs.
export DOCUMENT_AI_PROCESSOR_VERSION="pretrained-layout-parser-v1.5-2025-08-25"

# ---------- CORPUS ----------
# Relative to submission/. Files are read where they are, never copied.
export CORPUS_DIR="../Data-Corpus-v1/01-MedEvidence-Large-Corpus"

# ---------- MODELS ----------
# Vertex AI embeddings: one vector per chunk and per question.
export EMBEDDING_MODEL="gemini-embedding-001"
# 768 numbers per vector: good quality at a quarter of the model's full
# 3072, so storage and search stay fast.
export EMBEDDING_DIMENSION="768"

# One Gemini model for answers and for the agent for now; split only if
# the two ever need different models.
export GENERATION_MODEL="gemini-2.5-flash"

# Vertex AI Ranking API model: re-scores search candidates by relevance.
export RANKING_MODEL="semantic-ranker-default@latest"

# ---------- CHUNKING (Layout Parser built-in) ----------
# A hypothesis to test, not a copy of session-07's 256. A label page is about
# 1,300 tokens, so 512 is roughly one subsection. Step 2 checks that Table 3,
# Table 14 and the bulletin's warning table each land whole in one chunk.
export CHUNK_SIZE="512"

# Each chunk carries its section headings, so a table row keeps its context.
export INCLUDE_ANCESTOR_HEADINGS="true"
