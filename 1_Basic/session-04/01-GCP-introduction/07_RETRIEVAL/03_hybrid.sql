SELECT
  base.chunk_id, base.source_id, base.status, base.version,
  base.section, base.content, distance
FROM VECTOR_SEARCH(
  TABLE `tredence-fde-1.vikasragv1.knowledge_embeddings`,
  'embedding',
  query_value => AI.EMBED(
    'What does clause 7.4.2 allow for an offline store?',
    endpoint => 'text-embedding-005'
  ).result,
  lexical_search_columns => ['section','content'],
  lexical_search_query_value => 'What does clause 7.4.2 allow for an offline store?',
  top_k => 8,
  distance_type => 'COSINE'
)
ORDER BY distance;
