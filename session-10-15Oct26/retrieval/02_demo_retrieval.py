"""
Demonstrate Ontology Retrieval and Semantic Expansion

This program shows the TWO stages separately:

1. Semantic Search
   Uses embeddings to find ontology elements related to the question.

2. Ontology Expansion
   Uses ontology relationships and semantic rules to discover
   additional concepts required to understand the question.

This demonstrates why ontology retrieval is more than vector search.
"""

import json
import sys

from ontology_retriever import retrieve_relevant_ontology


# -------------------------------------------------------------------
# 1. Read user's question
# -------------------------------------------------------------------

# Question can be supplied from the command line.
#
# Example:
#
# python retrieval/02_demo_retrieval.py \
#   "Which projects have skill gaps?"
#
# If nothing is supplied, use the default question.

question = " ".join(sys.argv[1:]) or (
    "Which projects have skill gaps?"
)


# -------------------------------------------------------------------
# 2. Retrieve relevant ontology
# -------------------------------------------------------------------

# This performs two important operations:
#
# Stage 1:
#   Embedding-based semantic search finds candidate ontology elements.
#
# Stage 2:
#   Ontology traversal expands those candidates using
#   relationships and semantic rules.

result = retrieve_relevant_ontology(question)


# -------------------------------------------------------------------
# 3. Display original question
# -------------------------------------------------------------------

print("\nQUESTION:")
print(question)


# -------------------------------------------------------------------
# 4. Display semantic search results
# -------------------------------------------------------------------

# These are the ontology elements found using embedding similarity.
#
# At this stage we have only discovered possible entry points
# into the ontology.

print("\nSEMANTIC HITS (embedding stage):")

for hit in result["semantic_hits"]:

    print(
        f"  {hit['score']:.4f}  "
        f"{hit['kind']}: "
        f"{hit['name']}"
    )


# -------------------------------------------------------------------
# 5. Display ontology-expanded result
# -------------------------------------------------------------------

# Now show what the symbolic ontology traversal produced.
#
# This can contain additional:
#
#   - Objects
#   - Relationships
#   - Semantic rules
#
# These elements may NOT have appeared in the original
# embedding search results.
#
# They were added because the ontology says they are
# semantically connected to the retrieved concepts.

print(
    "\nEXPANDED RELEVANT ONTOLOGY "
    "(symbolic stage):"
)


# Remove semantic_hits because we already displayed them above.
expanded_ontology = {
    key: value
    for key, value in result.items()
    if key != "semantic_hits"
}


# Pretty-print the final relevant ontology subgraph.

print(
    json.dumps(
        expanded_ontology,
        indent=2
    )
)