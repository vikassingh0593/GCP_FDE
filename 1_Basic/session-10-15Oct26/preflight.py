"""Basic environment and Neo4j connectivity checks."""
from pathlib import Path
import os, sys
from neo4j import GraphDatabase
root=Path(__file__).resolve().parent
print("Python:",sys.executable)
print("Correct venv:",Path(sys.prefix).resolve()==(root/'.venv').resolve())
for k in ["GOOGLE_CLOUD_PROJECT","GOOGLE_CLOUD_LOCATION","NEO4J_URI"]: print(k,os.getenv(k,"<missing>"))
d=GraphDatabase.driver(os.getenv("NEO4J_URI","bolt://localhost:7687"),auth=(os.getenv("NEO4J_USER","neo4j"),os.getenv("NEO4J_PASSWORD","ontology123")))
d.verify_connectivity(); d.close(); print("Neo4j: OK")
