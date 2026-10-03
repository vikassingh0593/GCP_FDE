import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

def client() -> genai.Client:

     project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
     location = os.getenv(
        "GOOGLE_CLOUD_LOCATION",
        "global",
    )

     return genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        http_options=types.HttpOptions(
            api_version="v1",
        ),
    )

def model() -> str:
    """Return the trainer-configured Gemini model ID."""

    return os.getenv(
        "MODEL_ID",
        "gemini-2.5-flash",
    )

def generate(
          vertex_client: genai.Client,
          contents: str,
          config=None
):

    start_time = time.perf_counter()

    response = vertex_client.models.generate_content(
        model=model(),
        contents=contents,
        config=config,
    )

    latency_seconds = time.perf_counter() - start_time

    return response, latency_seconds


def usage(response) -> dict:
    usage_metadata = getattr(response, "usage_metadata", None)

    if usage_metadata is None:
        return {}

    usage_fields = [
        "prompt_token_count",
        "candidates_token_count",
        "cached_content_token_count",
        "thoughts_token_count",
        "total_token_count",
    ]

    return {
        field_name: getattr(
            usage_metadata,
            field_name,
            None,
        )
        for field_name in usage_fields
        if getattr(
            usage_metadata,
            field_name,
            None,
        )
        is not None
    }