CREATE OR REPLACE TABLE `tredence-fde-1.mayurragv1.knowledge_embeddings` AS
SELECT
  *,
  AI.EMBED(
    content,
    endpoint => 'text-embedding-005'
  ).result AS embedding
FROM `tredence-fde-1.mayurragv1.knowledge_chunks`;

SELECT
  COUNT(*) AS embedded_chunks,
  COUNTIF(embedding IS NULL) AS null_embeddings,
  MIN(ARRAY_LENGTH(embedding)) AS min_dimensions,
  MAX(ARRAY_LENGTH(embedding)) AS max_dimensions
FROM `tredence-learning.fde_rag_h1.knowledge_embeddings`;
