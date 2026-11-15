from __future__ import annotations

from google.adk.tools import ToolContext


_ALLOWED_PREFERENCES = {
    "preferred_region",
    "maintenance_window",
    "communication_style",
    "product_area",
}

_TEACHING_STATE_KEYS = (
    "current_case",
    "user:name",
    "user:preferred_region",
    "user:maintenance_window",
    "user:communication_style",
    "user:product_area",
    "app:lab_topic",
    "temp:last_state_tool",
)

def remember_user_preference(
        preference_name: str,
        value: str,
        tool_context: ToolContext,
)-> dict:

    key = preference_name.strip().lower()
    cleaned_value = value.strip()

    if key not in _ALLOWED_PREFERENCES:
        return {
            "status": "error",
            "message": f"Preference '{key}' is not allowed. Allowed preferences: {_ALLOWED_PREFERENCES}"
        }

    if not cleaned_value:
        return {
            "status": "error",
            "message": f"Preference value for '{key}' cannot be empty."
        }

    tool_context.state[f"users:{key}"] = cleaned_value
    tool_context.state["temp:last_state_tool"] = "remember_user_preference"

    return {
        "status": "stored",
        "scope": "user",
        "key": f"user:{key}",
        "value": cleaned_value,
    }


def set_current_case(
        case_topic: str,
        tool_context: ToolContext,) -> dict:

    cleaned_topic = case_topic.strip()
    if not cleaned_topic:
        return {
            "status": "error",
            "message": "Case topic cannot be empty."
        }
    
    tool_context.state["current_case"] = cleaned_topic
    tool_context.state["temp:last_state_tool"] = "set_current_case"

    return {
        "status": "stored",
        "scope": "session",
        "key": "current_case",
        "value": cleaned_topic,
    }

def inspect_visible_state(tool_context: ToolContext) -> dict:

    visible_state: dict[str, object] = {}

    for key in _TEACHING_STATE_KEYS:
        value = tool_context.state.get(key)

        if value is not None:
            visible_state[key] = value

    return {
        "status": "success",
        "visible_state": visible_state,
    }