"""Analyst preferences in user: state (session 17 remember_user_preference, Gate 8).

user: state follows the analyst into every new session. Only presentation
preferences live here: never order data, never a past conclusion (that would
let an old answer become "memory" and skip the live checks).
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from common import results

ALLOWED = {"answer_detail": ("brief", "full")}


def remember_preference(name: str, value: str, tool_context: ToolContext) -> dict:
    """Remember how this analyst wants answers, across sessions. Only name = answer_detail,
    value = brief | full. Use only when the analyst states the preference.
    """
    if name not in ALLOWED or value not in ALLOWED[name]:
        return results.error("session:user_state", "invalid_argument",
                             "only answer_detail = brief | full can be remembered")
    tool_context.state[f"user:{name}"] = value
    return results.ok("PREF", f"{name}={value}", "session:user_state", {"name": name, "value": value})
