import os
from google.adk.agents import Agent
from a2ui.adk import A2uiInstruction
from app.a2ui_runtime import A2UI_TOOLSET, PROCESSORS

INSTRUCTION = """
You are an enterprise service-request assistant.
When structured data collection is needed, use the A2UI capability rather than
asking a long sequence of chat questions.

For cloud access collect employee_name, email, project, role (Viewer, Job User,
or Data Editor), duration (7 days, 30 days, or 90 days), urgency (Normal or
High), and justification.

For KYC Form, collect full_name, email, KYC ID, Adhar ID and apply standard validations on that. 

Use only the current A2UI catalog. Never emit executable HTML or JavaScript.
Never claim approval. Submission is validated by deterministic application code.
"""

root_agent = Agent(
    name="enterprise_a2ui_assistant",
    model=os.getenv("MODEL_ID", "gemini-2.5-flash"),
    description="Interactive enterprise service-request assistant.",
    instruction=A2uiInstruction(
        INSTRUCTION,
        a2ui_processor=PROCESSORS.get,
        a2ui_enabled=PROCESSORS.is_enabled,
    ), 
    tools = [A2UI_TOOLSET]
)