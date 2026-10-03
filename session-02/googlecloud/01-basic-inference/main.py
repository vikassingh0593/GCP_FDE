from typing import Literal

from google.genai import types
from pydantic import BaseModel, Field

from common import client, generate, usage


vertex_client = client()

simple_prompt = "Tell me difference between Fine Tuning and RAG"


response, latency = generate(
    vertex_client,
    simple_prompt,
)

print("*"* 80)
print(f"Prompt: {simple_prompt}")
print(f"\nResponse: {response.text}")

print(f"\n\nLatency: {latency:.2f} seconds")
print(f"Usage  : {usage(response)}")