""""
    AUTO       → Model chooses: TEXT or TOOL
    ANY        → TOOL required
    NONE       → TEXT only
    VALIDATED  → TEXT or schema-valid TOOL
"""
from google.genai import types

from common import client, get_order, model_id

PROMPT = "Tell me whether ORD-1001 is shipped."

MODES = ("AUTO", "ANY", "NONE", "VALIDATED")

genai_client = client()

try:

    for mode in MODES:
        config = types.GenerateContentConfig(
            tools=[get_order],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=mode
                )
            ),
        )

        response = genai_client.models.generate_content(
            model=model_id(),
            contents=PROMPT,
            config=config,
        )

        print(f"\n=== MODE: {mode} ===")
        print("Function calls:", response.function_calls)
        print("Text          :", response.text)

finally:
    genai_client.close()