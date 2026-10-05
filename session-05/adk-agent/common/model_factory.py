import os
from google.adk.models.lite_llm import LiteLlm

def build_model():

    return LiteLlm(
         model=f"openai/{os.getenv('OPENROUTER_MODEL', 'google/gemini-3.1-pro-preview')}",
            api_base=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            extra_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://example.com"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "ADK Starter"),
            },
    )