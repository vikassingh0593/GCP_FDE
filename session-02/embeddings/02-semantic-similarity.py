""""
pip install sentence-transformers
"""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

model = SentenceTransformer(MODEL_NAME)

sentences = [
    "The customer wants to reduce support ticket resolution time.",
    "The organisation wants faster incident resolution.",
    "The weather in Pune is pleasant today.",
]

# I am happy, I am glad

# queen ==> king - male + female

embeddings = model.encode(
    sentences,
    normalize_embeddings=True,
)

similarities = model.similarity(embeddings, embeddings)

print(similarities)