-- Retrieval may return multiple versions. Authority is a separate contract.
SELECT
  chunk_id, source_id, status, version, section, content
FROM `tredence-learning.fde_rag_h1.knowledge_chunks`
WHERE LOWER(content) LIKE '%minute%'
ORDER BY
  CASE status WHEN 'APPROVED' THEN 0 WHEN 'SUPERSEDED' THEN 1 ELSE 2 END,
  version DESC;
