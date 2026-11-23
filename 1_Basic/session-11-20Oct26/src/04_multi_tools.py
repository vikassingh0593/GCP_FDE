
from google.genai import types

from common import (
    client,
    get_customer,
    get_inventory,
    get_order,
    model_id,
)


PROMPTS = (
    "Show order ORD-1002.",
    "Who is customer CUST-101?",
    "Is SKU-MONITOR-27 available?",
    "Check order ORD-1001 and SKU-LAPTOP-14.",
)


genai_client = client()


try:

    config = types.GenerateContentConfig(
        tools=[
            get_order,
            get_customer,
            get_inventory,
        ],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    )

    for prompt in PROMPTS:
        response = genai_client.models.generate_content(
            model=model_id(),
            contents=prompt,
            config=config,
        )

        print(f"\nPROMPT: {prompt}")

        function_calls = response.function_calls or []


        if not function_calls:
            print("No tool selected.")
            print("Text:", response.text)
            continue

        for function_call in function_calls:
            print("******* CALL: ")
            print("Tool selected:", function_call.name)
            print("Arguments:", function_call.args)


finally:
    genai_client.close()