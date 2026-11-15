from google.genai import types

from common import client, get_order, model_id

genai_client = client()

try:

    config = types.GenerateContentConfig(
        tools=[get_order],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    )

    user_content = types.Content(
        role="user",
        parts = [
            types.Part.from_text(
                #text="Show me order ORD-1001."
                text = "Tell me more about Machine Learning and AI."
            )
        ]
    )

    first_response = genai_client.models.generate_content(
        model=model_id(),
        contents=[user_content],
        config=config,
    )

    function_calls = first_response.function_calls or []

    if not function_calls:
        print("Gemini did not request a function call.")
        print(first_response.text)
        raise SystemExit(0)

    print("Model Tool Selection")
    print("Tool :", function_calls[0].name)
    print("Args :", dict(function_calls[0].args))

    tool_result = get_order(**dict(function_calls[0].args))

    print("Deterministic Tool Result")
    print(tool_result)


finally:
    genai_client.close()
