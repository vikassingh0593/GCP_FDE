"""
Hands-on 0.1 — Structured Tool Failure

Run:
    python src/05_errors.py

The requested order does not exist. The tool returns a bounded operational
error instead of throwing an unhandled exception or allowing fabricated data.
"""

from common import client, get_order, model_id


genai_client = client()

try:
    response = genai_client.models.generate_content(
        model=model_id(),
        contents=(
            "Show order ORD-9999. "
            "Do not invent information if the order does not exist."
        ),
        config={
            "tools": [get_order],
        },
    )

    print(response.text)

finally:
    genai_client.close()
