""""
Sentence -> Token -> token ids -> token vector embeddings

pip install torch transformers
"""

import torch
from transformers import AutoModel, AutoTokenizer

MODEL_NAME = "distilbert-base-uncased"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)

text = "Fine-tuning changes model behaviour, while RAG adds context."

inputs = tokenizer(text, return_tensors="pt")
input_ids = inputs["input_ids"]

embedding_layer = model.get_input_embeddings()

with torch.no_grad():
    raw_token_embeddings = embedding_layer(input_ids)


tokens = tokenizer.convert_ids_to_tokens(input_ids[0])

print("*" * 80)
print(f"\nTokens: {tokens}")
print(f"\nToken Ids: {input_ids[0].tolist()}")
print(f"Embedding Shape : {raw_token_embeddings.shape}")

print(raw_token_embeddings[0][10].tolist())