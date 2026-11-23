"""Shared Neo4j connection helper."""
import os
from neo4j import GraphDatabase

def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "ontology123")),
    )
