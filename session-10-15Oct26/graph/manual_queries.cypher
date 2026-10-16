// Entire small instance graph
MATCH (n)-[r]->(m) RETURN n,r,m;

// Skill gaps: semantic path is Project-REQUIRES->Skill plus Employee-WORKS_ON->Project-HAS_SKILL->Skill
MATCH (p:Project)-[:REQUIRES]->(s:Skill)
WHERE NOT EXISTS { MATCH (e:Employee)-[:WORKS_ON]->(p) MATCH (e)-[:HAS_SKILL]->(s) }
RETURN p.project_id AS project, s.name AS missing_skill;
