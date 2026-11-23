-- ============================================================
-- H1: Explicit Hybrid Scoring / RRF Reciprocal Rank Fusion Experiment
-- Query:
-- What does clause 7.4.2 allow for an offline store?
-- ============================================================

WITH semantic_results AS (

  -- 1. SEMANTIC-ONLY RETRIEVAL
  SELECT
    base.chunk_id,
    base.source_id,
    base.status,
    base.version,
    base.section,
    base.content,
    distance AS semantic_distance,

    ROW_NUMBER() OVER (
      ORDER BY distance ASC
    ) AS semantic_rank

  FROM VECTOR_SEARCH(
    TABLE `tredence-class.fde_rag_h1.knowledge_embeddings`,
    'embedding',

    query_value => AI.EMBED(
      'What does clause 7.4.2 allow for an offline store?',
      endpoint => 'text-embedding-005'
    ).result,

    top_k => 12,
    distance_type => 'COSINE'
  )
),

lexical_results AS (

  -- 2. LEXICAL-ENABLED RETRIEVAL
  SELECT
    base.chunk_id,

    ROW_NUMBER() OVER (
      ORDER BY distance ASC
    ) AS lexical_rank

  FROM VECTOR_SEARCH(
    TABLE `tredence-learning.fde_rag_h1.knowledge_embeddings`,
    'embedding',

    query_value => AI.EMBED(
      'What does clause 7.4.2 allow for an offline store?',
      endpoint => 'text-embedding-005'
    ).result,

    lexical_search_columns => ['section', 'content'],

    lexical_search_query_value =>
      'What does clause 7.4.2 allow for an offline store?',

    top_k => 12,
    distance_type => 'COSINE'
  )
),

combined AS (

  -- 3. JOIN BOTH RANKINGS
  SELECT
    s.chunk_id,
    s.source_id,
    s.status,
    s.version,
    s.section,
    s.content,
    s.semantic_distance,
    s.semantic_rank,
    l.lexical_rank

  FROM semantic_results s

  LEFT JOIN lexical_results l
    ON s.chunk_id = l.chunk_id
),

scored AS (

  -- 4. CALCULATE EXPLICIT RRF COMPONENT SCORES
  SELECT
    *,

    -- RRF constant k = 60
    1.0 / (60 + semantic_rank) AS semantic_score,

    CASE
      WHEN lexical_rank IS NULL THEN 0
      ELSE 1.0 / (60 + lexical_rank)
    END AS lexical_score

  FROM combined
)

-- ============================================================
-- 5. FINAL RESULTS
-- ============================================================

SELECT
  chunk_id,
  source_id,
  status,
  version,
  section,

  semantic_distance,

  semantic_rank,
  ROUND(semantic_score, 6) AS semantic_score,

  lexical_rank,
  ROUND(lexical_score, 6) AS lexical_score,

  ROUND(
    semantic_score + lexical_score,
    6
  ) AS hybrid_score,

  content

FROM scored

ORDER BY hybrid_score DESC

LIMIT 8;