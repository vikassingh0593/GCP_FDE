"""
python -m venv venv 
source venv/bin/activate
pip install transformers

"""

from transformers import AutoTokenizer

MODEL_NAME = "gpt2"
MODEL_NAME = "distilbert-base-uncased"

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

text = "Fine-tuning changes model behaviour, while RAG adds context."

encoded = tokenizer(
    text,
    add_special_tokens=True,
    return_attention_mask=True,
    return_tensors = None
)

token_ids = encoded["input_ids"]
tokens = tokenizer.convert_ids_to_tokens(token_ids)

decoded_text = tokenizer.decode(token_ids, skip_special_tokens=False)

print(f"Original text  : {text!r}")
print(f"Token count    : {len(token_ids)}")
print(f"Token IDs      : {token_ids}")
print(f"Tokens.        : {tokens}")
print(f"Decoded text   : {decoded_text!r}")
