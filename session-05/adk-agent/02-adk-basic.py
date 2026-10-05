from datetime import datetime, timezone
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from common.model_factory import build_model



load_dotenv()

agent = LlmAgent(
    name = "Basic Assistant",
    model = build_model(),
    description = "A basic assistant that can answer questions.",
    instructions = "You are a basic assistant that can answer questions.",
)

