-- Every chunk must retain provenance.
SELECT COUNT(*) AS broken_provenance_rows
FROM `tredence-learning.fde_rag_h1.knowledge_chunks`
WHERE source_id IS NULL OR section IS NULL OR content IS NULL OR source_uri IS NULL;

-- Both current and superseded evidence should exist.
SELECT status, COUNT(*) AS chunks
FROM `tredence-learning.fde_rag_h1.knowledge_chunks`
GROUP BY status
ORDER BY status;

-- Exact clause must survive chunking.
SELECT chunk_id, source_id, status, section, content
FROM `tredence-learning.fde_rag_h1.knowledge_chunks`
WHERE section LIKE '7.4.2%';
