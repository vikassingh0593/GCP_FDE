""""
python -m venv venv
--> Mac OS + Linux OS
source venv/bin/activate
--> Windows
venv\Scripts\activate

pip install openai requests
"""

import os
import json
import requests
from openai import OpenAI


def get_weather(city):
    dummy_weather = {
        "Nashik": {
            "temperature": 26,
            "condition": "Partly Cloudy",
            "humidity": 68
        },
        "Pune": {
            "temperature": 24,
            "condition": "Rainy",
            "humidity": 78
        },
        "Mumbai": {
            "temperature": 29,
            "condition": "Cloudy",
            "humidity": 84
        }
    }


    result = dummy_weather.get(
        city,
        {
            "temperature": 25,
            "condition": "Unknown",
            "humidity": 60
        }
    )

    return result


def execute_tool(function_name: str, arguments: dict):

    if function_name == "get_weather":
        return get_weather(**arguments)



client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Get current weather information for a city."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name such as Pune or Mumbai"
                    }
                },
                "required": ["city"],
                "additionalProperties": False
            }
        }
    }
]

messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant."
    },
    {
        "role": "user",
        #"content" : "what is the weather of Pune"
       "content" : "Tell me a joke about machine learning"
        #"content" : "is it raining in pune?"
        # "content" : "create a pdf for me with some random text"
    }
]

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=messages,
    tools = tools,
    tool_choice= "auto"
)

print(response)


if response.choices[0].message.tool_calls :
     for tool_call in response.choices[0].message.tool_calls:
            function_name = tool_call.function.name

            arguments = json.loads(
                tool_call.function.arguments
            )

            result = execute_tool(function_name, arguments)

            print("\n--------------------------------")
            print("LLM SELECTED TOOL")
            print("--------------------------------")
            print("Function :", function_name)
            print("Arguments:", arguments)


            print("\n--------------------------------")
            print("Result: ", result)

else:
     print("Generated Text with No Function Calls"  )
     print(response.choices[0].message.content)