SELECT chunk_id, source_id, status, version, section, content
FROM `tredence-fde-1.mayurragv1.knowledge_chunks`
WHERE SEARCH(section, '7.4.2')
   OR SEARCH(content, '7.4.2');
