"""Hybrid ontology retriever: semantic discovery + symbolic ontology expansion.

Stage 1: cosine similarity finds likely entry points.
Stage 2: ontology structure expands those seeds through relationships, rules and hierarchy.
The second stage is what makes this more than plain schema-vector search.
"""
from pathlib import Path
import json, os
import numpy as np
from google import genai

ROOT=Path(__file__).resolve().parents[1]
ONTOLOGY=json.loads((ROOT/"ontology"/"ontology.json").read_text())
INDEX_PATH=ROOT/"retrieval"/"ontology_index.json"

def _cosine(a,b):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    return float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))

def retrieve_relevant_ontology(question, top_k=4):
    index=json.loads(INDEX_PATH.read_text())
    client=genai.Client(vertexai=True,project=os.environ["GOOGLE_CLOUD_PROJECT"],location=os.getenv("GOOGLE_CLOUD_LOCATION","us-central1"))
    q=client.models.embed_content(model=os.getenv("EMBEDDING_MODEL","text-embedding-005"),contents=question).embeddings[0].values

    # 1) SEMANTIC DISCOVERY: find likely ontology entry points.
    ranked=sorted(index,key=lambda x:_cosine(q,x["embedding"]),reverse=True)[:top_k]
    seed_names={x["name"] for x in ranked}

    # 2) SYMBOLIC EXPANSION: use explicit ontology semantics.
    concepts=set(); rels=[]; rules=[]; hierarchy=[]
    for obj in ONTOLOGY["object_types"]:
        if obj["name"] in seed_names: concepts.add(obj["name"])
    for rule in ONTOLOGY["semantic_rules"]:
        if rule["name"] in seed_names or seed_names.intersection(rule["concepts"]) or seed_names.intersection(rule["relationships"]):
            rules.append(rule); concepts.update(rule["concepts"]); seed_names.update(rule["relationships"])

    # Expand relationships touching discovered concepts or explicitly discovered relationship types.
    changed=True
    while changed:
        changed=False
        for rel in ONTOLOGY["relationships"]:
            if rel in rels: continue
            if rel["type"] in seed_names or rel["from"] in concepts or rel["to"] in concepts:
                # Keep only useful one-hop expansions; added concepts may expose connecting paths.
                rels.append(rel)
                before=len(concepts); concepts.update([rel["from"],rel["to"]])
                changed |= len(concepts)>before
        # Stop broad expansion after first connected closure for this small lab.
        if len(rels)>=6: break

    # Include hierarchy statements connected to selected concepts.
    for h in ONTOLOGY.get("hierarchy",[]):
        if h["child"] in concepts or h["parent"] in concepts:
            hierarchy.append(h)

    objects=[o for o in ONTOLOGY["object_types"] if o["name"] in concepts]
    return {"semantic_hits":[{"kind":x["kind"],"name":x["name"],"score":round(_cosine(q,x["embedding"]),4)} for x in ranked],"object_types":objects,"relationships":rels,"hierarchy":hierarchy,"semantic_rules":rules}
