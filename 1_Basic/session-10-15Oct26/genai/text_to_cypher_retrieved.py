"""Production-pattern demo: retrieve a relevant ontology subgraph before Text-to-Cypher."""
from pathlib import Path
import json, os, re, sys
from google import genai
from neo4j import GraphDatabase

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"retrieval"))
from ontology_retriever import retrieve_relevant_ontology

QUESTION=" ".join(sys.argv[1:]) or "Which projects have skill gaps and what skills are missing?"

# Retrieve only the semantically relevant portion of the ontology.
relevant=retrieve_relevant_ontology(QUESTION)
ontology_context={k:v for k,v in relevant.items() if k!="semantic_hits"}
print("\nSEMANTIC HITS:",json.dumps(relevant["semantic_hits"],indent=2))
print("\nONTOLOGY SUBGRAPH SENT TO LLM:",json.dumps(ontology_context,indent=2))

client=genai.Client(vertexai=True,project=os.environ["GOOGLE_CLOUD_PROJECT"],location=os.getenv("GOOGLE_CLOUD_LOCATION","us-central1"))
prompt=f"""You generate READ-ONLY Neo4j Cypher. Use ONLY the relevant ontology below.
Return ONLY Cypher. Never generate CREATE, MERGE, SET, DELETE, REMOVE, DROP or CALL.

RELEVANT ONTOLOGY:
{json.dumps(ontology_context,indent=2)}

USER QUESTION:
{QUESTION}
"""
resp=client.models.generate_content(model=os.getenv("ADK_MODEL","gemini-2.5-flash"),contents=prompt)
cypher=re.sub(r'^```(?:cypher)?|```$','',resp.text.strip(),flags=re.I|re.M).strip()
forbidden=("CREATE","MERGE"," SET ","DELETE","REMOVE","DROP"," CALL ")
if any(x in f" {cypher.upper()} " for x in forbidden): raise ValueError(f"Unsafe generated query rejected: {cypher}")
print("\nGENERATED CYPHER:", cypher, sep="\n")

driver=GraphDatabase.driver(os.getenv("NEO4J_URI","bolt://localhost:7687"),auth=(os.getenv("NEO4J_USER","neo4j"),os.getenv("NEO4J_PASSWORD","ontology123")))
with driver.session() as s: rows=[dict(r) for r in s.run(cypher)]
driver.close()
print("\nGRAPH RESULT:", json.dumps(rows,indent=2,default=str), sep="\n")

answer_prompt=f"Answer using ONLY these Neo4j facts. Question: {QUESTION}\nFacts: {json.dumps(rows,default=str)}"
answer=client.models.generate_content(model=os.getenv("ADK_MODEL","gemini-2.5-flash"),contents=answer_prompt)
print("\nGROUNDED ANSWER:", answer.text, sep="\n")
