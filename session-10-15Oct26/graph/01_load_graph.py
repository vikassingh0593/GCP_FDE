"""Load instance data from seed.json into Neo4j."""
from pathlib import Path
import json
from db import get_driver

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "data" / "seed.json").read_text())
driver = get_driver()

with driver.session() as s:
    # Lab-only reset so every run starts from a known state.
    s.run("MATCH (n) DETACH DELETE n")
    for c in data["clients"]:
        s.run("CREATE (:Client {client_id:$client_id,name:$name,industry:$industry})", **c)
    for p in data["projects"]:
        s.run("CREATE (:Project {project_id:$project_id,name:$name,status:$status,progress:$progress,planned_progress:$planned_progress,days_to_go_live:$days_to_go_live})", **p)
        s.run("MATCH (p:Project {project_id:$project_id}),(c:Client {client_id:$client_id}) CREATE (p)-[:DELIVERED_FOR]->(c)", **p)
    for sk in data["skills"]:
        s.run("CREATE (:Skill {skill_id:$skill_id,name:$name,category:$category})", **sk)
    for e in data["employees"]:
        s.run("CREATE (:Employee {employee_id:$employee_id,name:$name,role:$role})", **e)
        for pid in e["projects"]: s.run("MATCH (e:Employee {employee_id:$eid}),(p:Project {project_id:$pid}) CREATE (e)-[:WORKS_ON]->(p)", eid=e['employee_id'],pid=pid)
        for sid in e["skills"]: s.run("MATCH (e:Employee {employee_id:$eid}),(sk:Skill {skill_id:$sid}) CREATE (e)-[:HAS_SKILL]->(sk)", eid=e['employee_id'],sid=sid)
    for req in data["requirements"]:
        for sid in req["skills"]: s.run("MATCH (p:Project {project_id:$pid}),(sk:Skill {skill_id:$sid}) CREATE (p)-[:REQUIRES]->(sk)", pid=req['project_id'],sid=sid)
    for m in data["milestones"]:
        s.run("CREATE (:Milestone {milestone_id:$milestone_id,name:$name,type:$type,status:$status})", **m)
        s.run("MATCH (p:Project {project_id:$project_id}),(m:Milestone {milestone_id:$milestone_id}) CREATE (p)-[:HAS_MILESTONE]->(m)", **m)
    for r in data["risks"]:
        s.run("CREATE (:Risk {risk_id:$risk_id,title:$title,severity:$severity,status:$status})", **r)
        s.run("MATCH (p:Project {project_id:$project_id}),(r:Risk {risk_id:$risk_id}) CREATE (p)-[:HAS_RISK]->(r)", **r)
        s.run("MATCH (e:Employee {employee_id:$owner}),(r:Risk {risk_id:$risk_id}) CREATE (e)-[:OWNS]->(r)", **r)
        s.run("MATCH (r:Risk {risk_id:$risk_id}),(m:Milestone {milestone_id:$blocks}) CREATE (r)-[:BLOCKS]->(m)", **r)
    counts=s.run("MATCH (n) OPTIONAL MATCH ()-[r]->() RETURN count(DISTINCT n) AS nodes,count(DISTINCT r) AS relationships").single()
    print(dict(counts))
driver.close()
