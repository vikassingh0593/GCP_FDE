"""Deterministic business validation."""
from typing import Literal
from pydantic import BaseModel, EmailStr, Field

class AccessRequest(BaseModel):
    employee_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    project: str = Field(min_length=2, max_length=120)
    role: Literal["Viewer", "Job User", "Data Editor"]
    duration: Literal["7 days", "30 days", "90 days"]
    urgency: Literal["Normal", "High"]
    justification: str = Field(min_length=10, max_length=1000)


class FeedbackRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    feedback: str = Field(min_length=3, max_length=2000)
    rating: int = Field(ge=1, le=5)


def _norm(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


# The model names form fields freely (fullName, full_name, employeeName...),
# so keys are normalised to the canonical snake_case names before validation.
_ALIASES = {
    "fullname": "full_name", "name": "full_name", "employeename": "employee_name",
    "emailaddress": "email", "comments": "feedback", "comment": "feedback",
    "starrating": "rating", "stars": "rating",
    "businessjustification": "justification",
}
_CANONICAL = {_norm(k): k for k in (
    *AccessRequest.model_fields, *FeedbackRequest.model_fields)}


def canonicalize(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        n = _norm(key)
        out[_ALIASES.get(n) or _CANONICAL.get(n) or key] = value
    return out


def validate_submission(values: dict) -> BaseModel:
    """Pick the schema from the submitted fields, then validate server-side."""
    data = canonicalize(values)
    model = FeedbackRequest if ({"feedback", "rating"} & data.keys()) else AccessRequest
    if model is FeedbackRequest and isinstance(data.get("rating"), float) \
            and data["rating"].is_integer():
        data["rating"] = int(data["rating"])
    return model.model_validate(data)
