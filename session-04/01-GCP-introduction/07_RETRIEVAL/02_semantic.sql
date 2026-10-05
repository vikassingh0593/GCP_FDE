WITH q AS (
  SELECT AI.EMBED(
    'How old can inventory information be when making a stockout decision?',
    endpoint => 'text-embedding-005'
  ).result AS embedding
)
SELECT
  base.chunk_id, base.source_id, base.status, base.version,
  base.section, base.content, distance
FROM VECTOR_SEARCH(
  TABLE `tredence-fde-1.vikasragv1.knowledge_embeddings`,
  'embedding',
  (SELECT embedding FROM q),
  query_column_to_search => 'embedding',
  top_k => 6,
  distance_type => 'COSINE'
)
ORDER BY distance DESC;
