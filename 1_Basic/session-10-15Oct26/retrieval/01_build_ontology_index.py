"""
Build Semantic Index for Ontology Elements

This program creates embeddings for the ONTOLOGY SCHEMA,
not for the actual enterprise/graph instance data.

We create embeddings for:
    1. Object types
    2. Relationships
    3. Semantic rules

Important:
Embeddings are used only to discover candidate ontology concepts.
Actual semantic meaning comes from ontology relationships and rules.
"""

from pathlib import Path
import json
import os

from google import genai


# -------------------------------------------------------------------
# 1. Locate project and load ontology
# -------------------------------------------------------------------

# Get the root directory of the project.
ROOT = Path(__file__).resolve().parents[1]

# Load the ontology schema from JSON.
ontology_file = ROOT / "ontology" / "ontology.json"

ontology = json.loads(
    ontology_file.read_text()
)


# -------------------------------------------------------------------
# 2. Connect to Vertex AI
# -------------------------------------------------------------------

# Gemini client using Vertex AI authentication.
client = genai.Client(
    vertexai=True,
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.getenv(
        "GOOGLE_CLOUD_LOCATION",
        "us-central1"
    ),
)

# Embedding model used for semantic search.
embedding_model = os.getenv(
    "EMBEDDING_MODEL",
    "text-embedding-005"
)


# -------------------------------------------------------------------
# 3. Prepare ontology records for indexing
# -------------------------------------------------------------------

# Each record represents ONE ontology element.
#
# Example:
#   object:Project
#   relationship:REQUIRES
#   rule:SkillGap
#
# We are NOT indexing actual projects, employees, risks, etc.

records = []


# -------------------------------------------------------------------
# 4. Add ontology object types
# -------------------------------------------------------------------

# Convert each ontology object into searchable text.
#
# Example:
#
# Project:
# "A customer delivery engagement.
#  Properties: project_id, name, status..."

for obj in ontology["object_types"]:

    record = {
        "id": f"object:{obj['name']}",
        "kind": "object",
        "name": obj["name"],
        "text": (
            f"{obj['name']}: "
            f"{obj['description']}. "
            f"Properties: {', '.join(obj['properties'])}"
        ),
    }

    records.append(record)


# -------------------------------------------------------------------
# 5. Add ontology relationships
# -------------------------------------------------------------------

# Relationships contain important semantic information.
#
# Example:
#
# Project REQUIRES Skill
#
# Employee HAS_SKILL Skill
#
# These relationships will later help us expand from
# initially retrieved concepts into a meaningful ontology subgraph.

for rel in ontology["relationships"]:

    record = {
        "id": f"relationship:{rel['type']}",
        "kind": "relationship",
        "name": rel["type"],
        "text": (
            f"{rel['from']} "
            f"{rel['type']} "
            f"{rel['to']}: "
            f"{rel['meaning']}"
        ),
    }

    records.append(record)


# -------------------------------------------------------------------
# 6. Add semantic rules
# -------------------------------------------------------------------

# Semantic rules capture business meaning that may not be obvious
# from individual nodes or relationships.
#
# Example:
#
# SkillGap:
# A project requires a skill that is not possessed by
# employees currently working on that project.

for rule in ontology["semantic_rules"]:

    record = {
        "id": f"rule:{rule['name']}",
        "kind": "rule",
        "name": rule["name"],
        "text": (
            f"{rule['name']}: "
            f"{rule['description']}"
        ),
    }

    records.append(record)


# -------------------------------------------------------------------
# 7. Generate embeddings
# -------------------------------------------------------------------

# Generate one embedding vector for every ontology element.
#
# These vectors allow us to perform semantic similarity search
# when a user asks a natural-language question.

for record in records:

    result = client.models.embed_content(
        model=embedding_model,
        contents=record["text"]
    )

    # Store the embedding vector with the ontology record.
    record["embedding"] = (
        result.embeddings[0].values
    )


# -------------------------------------------------------------------
# 8. Save the ontology semantic index
# -------------------------------------------------------------------

# The generated index contains:
#
#   ontology element
#   description
#   type
#   embedding vector
#
# Later, our ontology retriever searches this index.

output_file = (
    ROOT
    / "retrieval"
    / "ontology_index.json"
)

output_file.write_text(
    json.dumps(records)
)


# -------------------------------------------------------------------
# 9. Display result
# -------------------------------------------------------------------

print(
    f"Indexed {len(records)} ontology elements "
    f"-> {output_file}"
)