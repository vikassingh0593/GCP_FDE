"""Shared Vertex AI helper for the Tredence FDE demos."""
import os
import time
from typing import Any
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

def vertex_client() -> genai.Client:
    """Create a Google Gen AI SDK client backed by Vertex AI."""
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        http_options=types.HttpOptions(api_version="v1"),
    )

def model_id() -> str:
    """Return the trainer-configured Gemini model."""
    return os.getenv("MODEL_ID", "gemini-2.5-flash")

def generate(prompt: str, *, config=None, model: str | None = None) -> tuple[Any, float]:
    """Generate content and return response plus wall-clock latency."""
    started = time.perf_counter()
    response = vertex_client().models.generate_content(
        model=model or model_id(),
        contents=prompt,
        config=config,
    )
    return response, time.perf_counter() - started
