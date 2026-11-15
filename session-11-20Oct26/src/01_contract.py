"""
Hands-on 0.1 — Inspect the Model-Visible Tool Contract

Run:
    python src/01_contract.py

The Python function implementation is not what Gemini reads for routing.
Gemini receives a function declaration derived from the function's name,
documentation, type information, and schema.
"""

import json

from google.genai import types

from common import client, get_order


genai_client = client()

try:
    # Convert the Python callable into the declaration Gemini will see.
    declaration = types.FunctionDeclaration.from_callable(
        callable=get_order,
        client=genai_client,
    )

    print(
        json.dumps(
            declaration.to_json_dict(),
            indent=2,
        )
    )
finally:
    genai_client.close()
