from typing import Any
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import root_agent
from app.a2ui_runtime import enable_a2ui


APP_NAME = "tredence_official_a2ui"
USER_ID = "participant"
SESSIONS = InMemorySessionService()
RUNNER = Runner(agent=root_agent, app_name=APP_NAME, session_service=SESSIONS)


async def ensure_session(session_id: str) -> None:
    session = await SESSIONS.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if session is None:
        await SESSIONS.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )


def _messages(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, dict):
        return []
    # Official toolset output; an {"error": ...} response has none, so it is skipped.
    for key in ("validated_a2ui_json", "messages", "a2ui", "payload"):
        nested=value.get(key)
        if isinstance(nested,list):
            return [x for x in nested if isinstance(x,dict)]
        if isinstance(nested,dict):
            return [nested]
    if any(k in value for k in (
        "createSurface","updateComponents","updateDataModel","deleteSurface"
    )):
        return [value]
    return []

async def run_turn(session_id: str, message: str) -> dict:
    await ensure_session(session_id)
    enable_a2ui(session_id)
    content=types.Content(role="user",parts=[types.Part(text=message)])
    a2ui=[]
    text=[]
    async for event in RUNNER.run_async(
        user_id=USER_ID, session_id=session_id, new_message=content
    ):
        event_content=getattr(event,"content",None)
        if not event_content:
            continue
        for part in getattr(event_content,"parts",[]) or []:
            if getattr(part,"text",None):
                text.append(part.text)
            fr=getattr(part,"function_response",None)
            if fr is not None:
                a2ui.extend(_messages(getattr(fr,"response",None)))
    return {"events":[
        {"kind":"a2ui","messages":a2ui},
        {"kind":"text","text":"\n".join(text)}
    ]}
