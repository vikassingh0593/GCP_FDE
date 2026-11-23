""""
python -m venv venv 
source venv/bin/activate
pip install tiktoken
"""

import tiktoken

def demo_tiktoken(text: str, encoding_name: str = "gpt2") -> None:

    encoding = tiktoken.get_encoding(encoding_name)

    token_ids = encoding.encode(text)

    restructured_text = encoding.decode(token_ids)

    print("=" * 70)
    print(f"Encoding       : {encoding_name}")
    print(f"Original text  : {text!r}")
    print(f"Token count    : {len(token_ids)}")
    print(f"Token IDs      : {token_ids}")
    print(f"Decoded text   : {restructured_text!r}")


if __name__ == "__main__":
    sample_text = "Fine-tuning changes model behaviour, while RAG adds context."
    demo_tiktoken(sample_text, encoding_name="gpt2")