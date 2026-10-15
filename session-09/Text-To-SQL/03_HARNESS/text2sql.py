"""
Governed Text-to-SQL pipeline for the H2 standalone hands-on.

DESIGN PATTERN
==============

USER QUESTION
      |
      v
HYBRID METADATA RAG
      |
      +---- Lexical Search
      |
      +---- Semantic Search
      |       using Vertex AI embeddings
      |
      +---- Hybrid Fusion
      |
      v
Knowledge Catalog + Semantic Catalog
      |
      v
Authoritative BigQuery Physical Schema
      |
      v
Gemini SQL Generation
      |
      v
Deterministic SQL Guardrails
      |
      v
BigQuery Dry Run + Cost Gate
      |
      +---- failure ---> One Bounded Repair
      |
      v
Controlled BigQuery Execution


IMPORTANT
=========

Hybrid search is being applied to METADATA.

We are not embedding the actual sales/inventory business rows.

The purpose of metadata retrieval is to help Gemini understand:

    - which data objects are relevant;
    - what those objects mean;
    - how tables relate;
    - what business metrics mean.

For this small six-table training lab, build_schema_context() still provides
all six authoritative physical schemas to Gemini.

In a larger enterprise architecture, hybrid metadata retrieval could also be
used to determine which physical schemas should be supplied to the LLM.
"""

import json
import math
import os
import re
from typing import Any

from google import genai
from google.cloud import bigquery


# =============================================================================
# 1. Runtime configuration
# =============================================================================

PROJECT = os.getenv(
    "GOOGLE_CLOUD_PROJECT",
    "tredence-learning",
)

LOCATION = os.getenv(
    "GOOGLE_CLOUD_LOCATION",
    "us-central1",
)

DATASET = os.getenv(
    "TEXT2SQL_DATASET",
    "tredence_fde_text2sql",
)

MODEL = os.getenv(
    "TEXT2SQL_MODEL",
    "gemini-2.5-flash",
)

EMBEDDING_MODEL = os.getenv(
    "TEXT2SQL_EMBEDDING_MODEL",
    "gemini-embedding-001",
)


# -----------------------------------------------------------------------------
# Hybrid retrieval settings
# -----------------------------------------------------------------------------

KNOWLEDGE_TOP_K = int(
    os.getenv(
        "TEXT2SQL_KNOWLEDGE_TOP_K",
        "6",
    )
)

METRIC_TOP_K = int(
    os.getenv(
        "TEXT2SQL_METRIC_TOP_K",
        "3",
    )
)

LEXICAL_WEIGHT = float(
    os.getenv(
        "TEXT2SQL_LEXICAL_WEIGHT",
        "0.40",
    )
)

SEMANTIC_WEIGHT = float(
    os.getenv(
        "TEXT2SQL_SEMANTIC_WEIGHT",
        "0.60",
    )
)


# -----------------------------------------------------------------------------
# SQL governance settings
# -----------------------------------------------------------------------------

MAX_BYTES = int(
    os.getenv(
        "TEXT2SQL_MAX_BYTES",
        "1000000000",
    )
)

MAX_ROWS = int(
    os.getenv(
        "TEXT2SQL_MAX_ROWS",
        "100",
    )
)

MAX_REPAIR_ATTEMPTS = int(
    os.getenv(
        "TEXT2SQL_REPAIR_ATTEMPTS",
        "1",
    )
)


# =============================================================================
# 2. Google Cloud clients
# =============================================================================

# BigQuery uses Application Default Credentials.
bq = bigquery.Client(
    project=PROJECT,
)

# Explicit Vertex AI configuration prevents the SDK from looking for
# a separate Gemini API key.
gemini = genai.Client(
    vertexai=True,
    project=PROJECT,
    location=LOCATION,
)


# =============================================================================
# 3. Deterministic SQL security policy
# =============================================================================
#
# IMPORTANT DESIGN PRINCIPLE:
#
# Do not rely on the LLM to police itself.
#
# Even though the prompt tells Gemini to produce SELECT-only SQL,
# deterministic code checks the generated SQL again.
# =============================================================================


BLOCKED_SQL = re.compile(
    r"\b("
    r"INSERT|"
    r"UPDATE|"
    r"DELETE|"
    r"MERGE|"
    r"DROP|"
    r"ALTER|"
    r"CREATE|"
    r"TRUNCATE|"
    r"GRANT|"
    r"REVOKE|"
    r"CALL|"
    r"EXPORT"
    r")\b",
    re.IGNORECASE,
)


# =============================================================================
# 4. Small BigQuery helper
# =============================================================================


def query_rows(
    sql: str,
) -> list[dict[str, Any]]:
    """Execute a metadata query and return dictionaries."""

    return [
        dict(row)
        for row in bq.query(sql).result()
    ]


# =============================================================================
# 5. Embedding helper
# =============================================================================


def generate_embedding(
    text: str,
) -> list[float]:
    """
    Generate an embedding for runtime semantic retrieval.

    During bootstrap:
        metadata -> embedding

    During runtime:
        user question -> embedding

    We then compare the question vector with stored metadata vectors.
    """

    response = gemini.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )

    if not response.embeddings:
        raise RuntimeError(
            "Vertex AI returned no embedding."
        )

    return list(
        response.embeddings[0].values
    )


# =============================================================================
# 6. Lexical scoring
# =============================================================================


def tokenize(
    text: str,
) -> set[str]:
    """
    Convert text into simple lowercase lexical tokens.

    Example:

        "Show net sales by store"

    becomes approximately:

        {
            "show",
            "net",
            "sales",
            "by",
            "store"
        }

    This intentionally remains simple for training.
    """

    return set(
        re.findall(
            r"[a-z0-9_]+",
            text.lower(),
        )
    )


def lexical_score(
    question: str,
    item: dict[str, Any],
) -> float:
    """
    Calculate normalized keyword overlap.

    This represents the LEXICAL side of hybrid search.

    It is useful when the user uses exact terminology such as:

        supplier
        sales
        inventory
        net_sales
    """

    # Hey, I am Mayur Patil from India and love to be here
    # hey, ,, I, am, may, ur, pati, il, .....
    question_words = tokenize(
        question
    )

    # Ignore the embedding itself when creating searchable text.
    searchable_values = [
        str(value or "")
        for key, value in item.items()
        if key != "embedding"
    ]

    searchable_text = " ".join(
        searchable_values
    )

    metadata_words = tokenize(
        searchable_text
    )

    if not question_words:
        return 0.0

    overlap = (
        question_words
        & metadata_words
    )

    return len(overlap) / len(
        question_words
    )


# =============================================================================
# 7. Semantic similarity
# =============================================================================


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """
    Calculate cosine similarity between two embedding vectors.

    Result is normally near:

        1.0  -> very similar
        0.0  -> unrelated
       -1.0  -> opposite direction

    For semantic embeddings in this lab, scores will generally be positive.
    """

    if not vector_a or not vector_b:
        return 0.0

    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = sum(
        a * b
        for a, b in zip(
            vector_a,
            vector_b,
        )
    )

    magnitude_a = math.sqrt(
        sum(
            value * value
            for value in vector_a
        )
    )

    magnitude_b = math.sqrt(
        sum(
            value * value
            for value in vector_b
        )
    )

    if magnitude_a == 0:
        return 0.0

    if magnitude_b == 0:
        return 0.0

    return (
        dot_product
        / (magnitude_a * magnitude_b)
    )


# =============================================================================
# 8. Hybrid score
# =============================================================================


def hybrid_score(
    question: str,
    question_embedding: list[float],
    item: dict[str, Any],
) -> dict[str, float]:
    """
    Combine lexical relevance and semantic relevance.

    TRAINING FORMULA
    ----------------

        hybrid_score =
            40% lexical
            +
            60% semantic

    The weights come from environment variables.

    IMPORTANT:
    These are demonstration weights.

    A production system should evaluate/tune ranking against a representative
    query set rather than assuming that 40/60 is universally correct.
    """

    lexical = lexical_score(
        question,
        item,
    )

    semantic = cosine_similarity(
        question_embedding,
        item.get("embedding") or [],
    )

    final_score = (
        LEXICAL_WEIGHT * lexical
        +
        SEMANTIC_WEIGHT * semantic
    )

    return {
        "lexical_score": lexical,
        "semantic_score": semantic,
        "hybrid_score": final_score,
    }


# =============================================================================
# 9. Hybrid Schema-RAG
# =============================================================================


def retrieve_catalog_context(
    question: str,
) -> dict[str, list[dict[str, Any]]]:
    """
    Retrieve relevant Knowledge Catalog and Semantic Catalog entries.

    THIS IS THE MAIN HYBRID-RAG FUNCTION.

    Flow:

        User Question
             |
             v
        Generate Question Embedding
             |
        +----+-------------------+
        |                        |
        v                        v
    Lexical Score          Semantic Score
    keyword overlap        cosine similarity
        |                        |
        +-----------+------------+
                    |
                    v
              Hybrid Score
                    |
                    v
              Rank Metadata
                    |
             +------+------+
             |             |
             v             v
        Knowledge       Semantic
         Catalog         Catalog

    Knowledge Catalog answers:

        "Which data objects are relevant and how do they relate?"

    Semantic Catalog answers:

        "Which governed business definition should be used?"
    """

    # -------------------------------------------------------------------------
    # Step 1:
    # Convert the user's natural-language question into a semantic vector.
    # -------------------------------------------------------------------------

    question_embedding = generate_embedding(
        question
    )

    # -------------------------------------------------------------------------
    # Step 2:
    # Load approved Knowledge Catalog metadata.
    #
    # For this tiny training dataset we load all metadata records and rank
    # them in Python.
    #
    # For hundreds of thousands of metadata objects, this would normally
    # move to an indexed retrieval implementation.
    # -------------------------------------------------------------------------

    knowledge = query_rows(
        f"""
        SELECT
            object_type,
            object_name,
            parent_object,
            description,
            synonyms,
            join_hint,
            embedding
        FROM `{PROJECT}.{DATASET}.knowledge_catalog`
        WHERE status = 'APPROVED'
        """
    )

    # -------------------------------------------------------------------------
    # Step 3:
    # Load approved governed business metrics.
    # -------------------------------------------------------------------------

    metrics = query_rows(
        f"""
        SELECT
            metric_name,
            business_definition,
            sql_expression,
            grain,
            synonyms,
            embedding
        FROM `{PROJECT}.{DATASET}.semantic_catalog`
        WHERE status = 'APPROVED'
        """
    )

    # -------------------------------------------------------------------------
    # Step 4:
    # Score every Knowledge Catalog entry using BOTH:
    #
    #     lexical relevance
    #     +
    #     semantic relevance
    # -------------------------------------------------------------------------

    scored_knowledge = []

    for item in knowledge:

        scores = hybrid_score(
            question=question,
            question_embedding=question_embedding,
            item=item,
        )

        scored_item = dict(item)

        # Do not send large embedding vectors to Gemini.
        scored_item.pop(
            "embedding",
            None,
        )

        # Keep scores because they are useful for explainability and training.
        scored_item.update(
            scores
        )

        scored_knowledge.append(
            scored_item
        )

    scored_knowledge.sort(
        key=lambda item: item["hybrid_score"],
        reverse=True,
    )

    # -------------------------------------------------------------------------
    # Step 5:
    # Score Semantic Catalog entries in exactly the same way.
    # -------------------------------------------------------------------------

    scored_metrics = []

    for item in metrics:

        scores = hybrid_score(
            question=question,
            question_embedding=question_embedding,
            item=item,
        )

        scored_item = dict(item)

        scored_item.pop(
            "embedding",
            None,
        )

        scored_item.update(
            scores
        )

        scored_metrics.append(
            scored_item
        )

    scored_metrics.sort(
        key=lambda item: item["hybrid_score"],
        reverse=True,
    )

    # -------------------------------------------------------------------------
    # Step 6:
    # Keep only the strongest metadata candidates.
    #
    # This is the RETRIEVAL step of RAG.
    # -------------------------------------------------------------------------

    relevant_knowledge = (
        scored_knowledge[
            :KNOWLEDGE_TOP_K
        ]
    )

    relevant_metrics = (
        scored_metrics[
            :METRIC_TOP_K
        ]
    )

    return {
        "knowledge": relevant_knowledge,
        "metrics": relevant_metrics,
    }


# =============================================================================
# 10. Authoritative physical BigQuery schema
# =============================================================================


def build_schema_context() -> str:
    """
    Read the REAL BigQuery schemas.

    Why do this?

    The Knowledge Catalog gives Gemini business meaning and relationships.

    But BigQuery itself remains authoritative for:

        actual table names
        actual column names
        actual data types

    Therefore Gemini does not have to invent columns.

    NOTE:
    This training lab has only six analytical tables, so all six schemas are
    supplied.

    In a much larger implementation, hybrid metadata retrieval could first
    identify candidate tables and this function could retrieve only those
    physical schemas.
    """

    analytical_tables = [
        "sales",
        "inventory",
        "stores",
        "products",
        "suppliers",
        "product_suppliers",
    ]

    schema_lines: list[str] = []

    for table_name in analytical_tables:

        table = bq.get_table(
            f"{PROJECT}.{DATASET}.{table_name}"
        )

        columns = ", ".join(
            f"{field.name} {field.field_type}"
            for field in table.schema
        )

        schema_lines.append(
            f"{table_name}({columns})"
        )

    return "\n".join(
        schema_lines
    )


# =============================================================================
# 11. Clean Gemini SQL response
# =============================================================================


def extract_sql_v0(
    model_text: str,
) -> str:
    """
    Remove accidental Markdown SQL fences from the model response.
    """

    text = model_text.strip()

    fenced = re.search(
        r"```(?:sql)?\s*(.*?)```",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if fenced:
        text = fenced.group(1).strip()

    return text.rstrip(";").strip()


def extract_sql(model_text: str) -> str:
    """
    Clean Gemini's response and return executable GoogleSQL only.

    Gemini may occasionally return:

        ```sql
        SELECT ...
        ```

    or:

        ```googlesql
        SELECT ...
        ```

    or even:

        googlesql
        SELECT ...

    This function removes those presentation labels before validation.
    """

    text = model_text.strip()

    # -------------------------------------------------------------------------
    # Remove Markdown fenced code blocks.
    #
    # Supports:
    #   ```sql
    #   ```googlesql
    #   ```
    # -------------------------------------------------------------------------

    fenced = re.search(
        r"```(?:sql|googlesql)?\s*(.*?)```",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if fenced:
        text = fenced.group(1).strip()

    # -------------------------------------------------------------------------
    # Gemini can sometimes return the language label without Markdown fences:
    #
    #   googlesql
    #   SELECT ...
    #
    # or:
    #
    #   sql
    #   SELECT ...
    #
    # Remove that label.
    # -------------------------------------------------------------------------

    text = re.sub(
        r"^\s*(?:googlesql|sql)\s*[\r\n]+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # -------------------------------------------------------------------------
    # Remove trailing semicolon because our validator treats embedded
    # semicolons as possible multiple statements.
    # -------------------------------------------------------------------------

    return text.rstrip(";").strip()
# =============================================================================
# 12. Gemini SQL generation
# =============================================================================


def generate_sql(
    question: str,
    catalog_context: dict[
        str,
        list[dict[str, Any]],
    ],
    previous_sql: str = "",
    previous_error: str = "",
) -> str:
    """
    Generate SQL or repair one failed SQL candidate.

    Gemini receives:

        1. User question
        2. Authoritative physical BigQuery schema
        3. Hybrid-retrieved Knowledge Catalog metadata
        4. Hybrid-retrieved Semantic Catalog metrics
        6. Return the raw executable SQL statement only.
        7. The first word of your response MUST be SELECT or WITH.
        8. Do not return Markdown code fences.
        9. Do not return language labels such as sql or googlesql.
        10. Do not return explanations.

    This is the AUGMENT + GENERATE part of RAG.
    """

    physical_schema = (
        build_schema_context()
    )

    prompt = f"""
You generate safe GoogleSQL for BigQuery.

PROJECT
{PROJECT}

ALLOWED DATASET
{DATASET}

AUTHORITATIVE PHYSICAL SCHEMA
{physical_schema}

HYBRID-RETRIEVED KNOWLEDGE CATALOG
{json.dumps(
    catalog_context["knowledge"],
    indent=2,
    default=str,
)}

HYBRID-RETRIEVED SEMANTIC CATALOG
{json.dumps(
    catalog_context["metrics"],
    indent=2,
    default=str,
)}

RULES

1. Return SQL only.
2. Do not return Markdown or explanation.
3. Produce exactly one analytical SELECT query.
4. WITH/CTEs are allowed.
5. Read only from `{PROJECT}.{DATASET}`.
6. Use fully-qualified BigQuery table names.
7. Never invent a table, column, join or business definition.
8. If a governed metric matches the question, use its approved SQL expression.
9. Add LIMIT {MAX_ROWS} to detail/list queries.
10. Aggregated queries do not require LIMIT unless the user asks for top/bottom rows.
11. CURRENT_DATE() is allowed for relative-date questions.

USER QUESTION
{question}
"""

    # -------------------------------------------------------------------------
    # Repair context is added only after a deterministic failure.
    # -------------------------------------------------------------------------

    if previous_error:

        prompt += f"""

THE PREVIOUS SQL FAILED VALIDATION OR BIGQUERY DRY RUN.

PREVIOUS SQL
{previous_sql}

DETERMINISTIC ERROR
{previous_error}

Correct the SQL while preserving the user's business intent.

Return SQL only.
"""
    response = gemini.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    return extract_sql(
        response.text or ""
    )


# =============================================================================
# 13. Deterministic SQL guardrails
# =============================================================================


def validate_sql(
    sql: str,
) -> tuple[bool, str]:
    """
    Apply deterministic checks BEFORE BigQuery execution.

    This is intentionally simple for the training hands-on.

    Production systems should normally use an SQL parser / AST-based policy
    engine for richer validation.
    """

    clean_sql = sql.strip()

    # -------------------------------------------------------------------------
    # Analytical reads only.
    # -------------------------------------------------------------------------

    if not re.match(
        r"^(SELECT|WITH)\b",
        clean_sql,
        re.IGNORECASE,
    ):
        return (
            False,
            "Only SELECT or WITH queries are allowed.",
        )

    # -------------------------------------------------------------------------
    # Block destructive/privileged SQL.
    # -------------------------------------------------------------------------

    if BLOCKED_SQL.search(
        clean_sql
    ):
        return (
            False,
            "DDL, DML and privileged SQL statements are blocked.",
        )

    # -------------------------------------------------------------------------
    # Exactly one SQL statement.
    # -------------------------------------------------------------------------

    if ";" in clean_sql:
        return (
            False,
            "Multiple SQL statements are not allowed.",
        )

    # -------------------------------------------------------------------------
    # Any fully-qualified table reference must remain inside our dataset.
    # -------------------------------------------------------------------------

    allowed_prefix = (
        f"{PROJECT}.{DATASET}."
    )

    references = re.findall(
        r"`([^`]+)`",
        clean_sql,
    )

    for reference in references:

        if (
            "." in reference
            and not reference.startswith(
                allowed_prefix
            )
        ):
            return (
                False,
                f"Table outside allowed dataset: {reference}",
            )

    return True, ""


# =============================================================================
# 14. BigQuery dry run and cost gate
# =============================================================================


def dry_run_sql(
    sql: str,
) -> tuple[bool, str, int]:
    """
    Compile the query and estimate scan cost BEFORE execution.

    BigQuery validates:

        syntax
        tables
        columns
        functions

    and estimates:

        bytes processed

    No actual business query is executed at this stage.
    """

    try:

        dry_run_job = bq.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
            ),
        )

        bytes_processed = int(
            dry_run_job.total_bytes_processed
            or 0
        )

        if bytes_processed > MAX_BYTES:

            return (
                False,
                (
                    f"Estimated scan {bytes_processed} bytes "
                    f"exceeds the lab budget of "
                    f"{MAX_BYTES} bytes."
                ),
                bytes_processed,
            )

        return (
            True,
            "",
            bytes_processed,
        )

    except Exception as exc:

        # The exact BigQuery error is useful repair context.
        return (
            False,
            str(exc),
            0,
        )


# =============================================================================
# 15. Controlled BigQuery execution
# =============================================================================


def execute_sql(
    sql: str,
) -> list[dict[str, Any]]:
    """
    Execute SQL only after BOTH:

        deterministic validation
        BigQuery dry run

    have approved it.
    """

    job_config = (
        bigquery.QueryJobConfig(
            maximum_bytes_billed=MAX_BYTES,
        )
    )

    query_job = bq.query(
        sql,
        job_config=job_config,
    )

    return [
        dict(row)
        for row in query_job.result(
            max_results=MAX_ROWS
        )
    ]


# =============================================================================
# 16. Main ADK tool / orchestrator
# =============================================================================


def text_to_sql(
    question: str,
) -> dict[str, Any]:
    """
    Answer a warehouse question through the governed Text-to-SQL pipeline.

    COMPLETE PIPELINE
    =================

    Question
       |
       v
    Generate Question Embedding
       |
       v
    Hybrid Metadata RAG
       |
       +---- Lexical
       |
       +---- Semantic
       |
       +---- Fusion
       |
       v
    Knowledge + Semantic Context
       |
       v
    Physical BigQuery Schema
       |
       v
    Gemini SQL Generation
       |
       v
    Deterministic Validation
       |
       v
    BigQuery Dry Run
       |
       +---- failure
       |        |
       |        v
       |    One Repair
       |        |
       |        +---- back through validation
       |
       v
    Execute
       |
       v
    Rows + SQL + Retrieval Metadata
    """

    # -------------------------------------------------------------------------
    # Stage 1:
    # Hybrid retrieval over metadata.
    # -------------------------------------------------------------------------

    catalog_context = (
        retrieve_catalog_context(
            question
        )
    )

    # -------------------------------------------------------------------------
    # Stage 2:
    # Ground Gemini and generate the first SQL candidate.
    # -------------------------------------------------------------------------

    sql = generate_sql(
        question=question,
        catalog_context=catalog_context,
    )

    repair_attempts = 0
    last_error = ""

    # -------------------------------------------------------------------------
    # Stage 3:
    # Governed validation / repair loop.
    #
    # MAX_REPAIR_ATTEMPTS defaults to 1.
    # -------------------------------------------------------------------------

    while (
        repair_attempts
        <= MAX_REPAIR_ATTEMPTS
    ):

        # ---------------------------------------------------------------------
        # Gate 1:
        # Deterministic policy validation.
        # ---------------------------------------------------------------------

        valid, error = validate_sql(
            sql
        )

        # ---------------------------------------------------------------------
        # Gate 2:
        # BigQuery compilation and cost estimation.
        # ---------------------------------------------------------------------

        if valid:

            (
                valid,
                error,
                bytes_processed,
            ) = dry_run_sql(
                sql
            )

        else:

            bytes_processed = 0

        # ---------------------------------------------------------------------
        # Execute ONLY when both gates approve the query.
        # ---------------------------------------------------------------------

        if valid:

            rows = execute_sql(
                sql
            )

            return {
                "status": "SUCCESS",
                "question": question,
                "sql": sql,
                "bytes_processed": bytes_processed,
                "repair_attempts": repair_attempts,

                # -------------------------------------------------------------
                # Retrieval provenance.
                #
                # These are useful during training because participants can see
                # which metadata objects influenced the SQL generation.
                # -------------------------------------------------------------

                "knowledge_context": [
                    {
                        "object": item[
                            "object_name"
                        ],
                        "lexical_score": round(
                            item[
                                "lexical_score"
                            ],
                            4,
                        ),
                        "semantic_score": round(
                            item[
                                "semantic_score"
                            ],
                            4,
                        ),
                        "hybrid_score": round(
                            item[
                                "hybrid_score"
                            ],
                            4,
                        ),
                    }
                    for item
                    in catalog_context[
                        "knowledge"
                    ]
                ],

                "semantic_metrics_used": [
                    {
                        "metric": item[
                            "metric_name"
                        ],
                        "lexical_score": round(
                            item[
                                "lexical_score"
                            ],
                            4,
                        ),
                        "semantic_score": round(
                            item[
                                "semantic_score"
                            ],
                            4,
                        ),
                        "hybrid_score": round(
                            item[
                                "hybrid_score"
                            ],
                            4,
                        ),
                    }
                    for item
                    in catalog_context[
                        "metrics"
                    ]
                ],

                "rows": rows,
            }

        # ---------------------------------------------------------------------
        # Remember the exact deterministic failure.
        # ---------------------------------------------------------------------

        last_error = error

        # ---------------------------------------------------------------------
        # Stop rather than creating an uncontrolled self-correction loop.
        # ---------------------------------------------------------------------

        if (
            repair_attempts
            >= MAX_REPAIR_ATTEMPTS
        ):
            break

        # ---------------------------------------------------------------------
        # One bounded repair.
        #
        # Gemini receives:
        #
        #     original question
        #     original metadata context
        #     failed SQL
        #     exact deterministic error
        #
        # It is then asked to correct the SQL.
        # ---------------------------------------------------------------------

        sql = generate_sql(
            question=question,
            catalog_context=catalog_context,
            previous_sql=sql,
            previous_error=error,
        )

        repair_attempts += 1

    # -------------------------------------------------------------------------
    # Controlled failure.
    # -------------------------------------------------------------------------

    return {
        "status": "FAILED",
        "question": question,
        "sql": sql,
        "repair_attempts": repair_attempts,
        "error": last_error,
    }