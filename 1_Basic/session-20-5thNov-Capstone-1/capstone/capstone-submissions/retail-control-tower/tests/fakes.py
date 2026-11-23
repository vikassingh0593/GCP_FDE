"""Test doubles shared by the offline tests: a scripted model and canned BigQuery rows.

The scripted model replaces Gemini inside a real ADK Runner, so the tests run
the real harness, tools, session service and confirmation flow, with no cloud.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

NOW = datetime.now(timezone.utc)


def ago(**kwargs) -> datetime:
    return NOW - timedelta(**kwargs)


Step = Callable[[LlmRequest], types.Content]


def call(name: str, **args) -> Step:
    return lambda request: types.Content(role="model", parts=[types.Part(
        function_call=types.FunctionCall(name=name, args=args))])


def say(text_or_fn) -> Step:
    def step(request: LlmRequest) -> types.Content:
        text = text_or_fn(request) if callable(text_or_fn) else text_or_fn
        return types.Content(role="model", parts=[types.Part(text=text)])
    return step


def last_responses(request: LlmRequest) -> dict[str, dict]:
    """Function responses in the request so far, by tool name (latest wins)."""
    found = {}
    for content in request.contents or []:
        for part in content.parts or []:
            if part.function_response:
                found[part.function_response.name] = part.function_response.response or {}
    return found


class ScriptedModel(BaseLlm):
    """Returns the next scripted step on every call; repeats the last one when the script runs out."""

    model: str = "scripted"
    steps: list[Any] = []
    calls: int = 0

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False
                                     ) -> AsyncGenerator[LlmResponse, None]:
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        yield LlmResponse(content=step(llm_request), usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=10))


ORDER_ROWS = {
    "ORD-78421": {"order_id": "ORD-78421", "order_type": "B2B", "sku": "SKU-74512", "quantity": 40,
                  "warehouse_id": "WH-BLR-01", "status": "ALLOCATION_PENDING", "status_reason_code": "ALLOC-E101",
                  "payment_status": "AUTHORIZED", "carrier": None, "tracking_number": None,
                  "placed_at": ago(hours=48), "promised_delivery_at": ago(hours=4),
                  "last_updated_at": ago(hours=48), "extracted_at": ago(minutes=5)},
}


def fake_query_rows(table_rows: dict[str, list[dict]]):
    """query_rows replacement: picks rows by the table name in the SQL and the first STRING parameter."""
    def run(sql: str, params=None, what: str = "", timeout: float = 30.0) -> list[dict]:
        for table, rows in table_rows.items():
            if f".{table}`" in sql:
                values = {getattr(p, "value", None) for p in params or []}
                return [r for r in rows if values & set(map(str, r.values())) or not params]
        return []
    return run
