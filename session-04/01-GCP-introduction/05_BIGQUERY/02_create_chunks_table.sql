CREATE OR REPLACE TABLE `tredence-fde-1.mayurragv1.knowledge_chunks` (
  chunk_id STRING,
  source_id STRING,
  title STRING,
  status STRING,
  version FLOAT64,
  section STRING,
  content STRING,
  source_uri STRING
);

LOAD DATA INTO `tredence-fde-1.mayurragv1.knowledge_chunks`
FROM FILES (
  format = 'JSON',
  uris = ['gs://mayur-rag-v1/derived/chunks/generated_chunks.jsonl']
);

SELECT
  chunk_id, source_id, status, version, section,
  SUBSTR(content,1,100) AS content_preview
FROM `tredence-fde-1.mayurragv1.knowledge_chunks`
ORDER BY source_id, chunk_id;
