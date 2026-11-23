# Topic 4 — Prompting Patterns & Structured Output

The goal is not to memorize prompt templates. Make the task, evidence, rules and output contract explicit enough that an application can use the response safely.

## Zero-Shot Prompting

Give the task and constraints **without examples**. Use it when the task is familiar and the expected behavior is easy to describe.

```text
Classify as: shipping, billing, account, other.
Return only the category.

Request: "My parcel says delivered but I do not have it."
```

## Few-Shot Prompting

Provide a few representative input/output examples when the desired boundary or pattern is easier to demonstrate than describe.

```text
"My card was charged twice." -> billing
"I cannot reset my password." -> account
"Tracking has not changed." -> shipping

Now classify:
"The parcel says delivered but I do not have it."
```

**FDE point:** Examples consume context. Add them because they improve behavior, not because few-shot is automatically better.

## Rules + Context

Separate **instructions** from **evidence**.

```text
ROLE
You are a support-triage component.

RULES
- Use only supplied evidence.
- Do not invent live order status.
- If evidence is insufficient, say so.

CONTEXT
Customer: "Order 412 is late."
Carrier data: No current carrier event.

TASK
Is the cause of delay established?
```

## JSON Schema / Structured Output

When software consumes the result, prefer a machine-readable contract over prose.

```python
class TriageDecision(BaseModel):
    category: Literal["shipping", "billing", "account", "other"]
    priority: Literal["low", "medium", "high"]
    needs_human_review: bool
    next_action: str
```

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=TriageDecision,
    temperature=0.1,
)
```

**Remember:** `Syntactic validity != semantic reliability`.

## Hands-On

```bash
python 01_prompting_demo.py
```

It runs zero-shot, few-shot, rules/context and typed structured-output examples.
