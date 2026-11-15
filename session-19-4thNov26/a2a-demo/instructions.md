# Participant Instructions — Topic 21 A2A

Execute in order.

## Stage 1 — Setup

```bash
bash setup.sh
source .venv/bin/activate
source lab.env
python preflight.py
```

If Vertex authentication is needed:

```bash
gcloud config configurations activate "$TREDENCE_GCLOUD_CONFIG"
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_QUOTA_PROJECT"
```

## Stage 2 — Inspect the specialist

Read:

```text
01_fulfilment_specialist/fulfilment_agent/tools.py
01_fulfilment_specialist/fulfilment_agent/agent.py
```

Identify:

```python
root_agent = Agent(...)
a2a_app = to_a2a(...)
```

Mental model:

```text
Agent(...)  = reasoning agent
to_a2a(...) = exposes that agent through A2A
```

## Stage 3 — Start the remote specialist

### Terminal 1

```bash
source .venv/bin/activate
source lab.env

uvicorn fulfilment_agent.agent:a2a_app \
  --app-dir 01_fulfilment_specialist \
  --host "$FULFILMENT_AGENT_HOST" \
  --port "$FULFILMENT_AGENT_PORT"
```

Leave it running.

Expected:

```text
Uvicorn running on http://127.0.0.1:8001
```

## Stage 4 — Resolve the Agent Card yourself

### Terminal 2

```bash
source .venv/bin/activate
source lab.env
curl -s "$FULFILMENT_AGENT_CARD_URL" | python -m json.tool
```

Look for identity, description, endpoint, capabilities and skills.

Ask:

> Can I understand what this agent offers without seeing its source code?

## Stage 5 — Inspect the consumer

Read:

```text
02_customer_orchestrator/customer_orchestrator/agent.py
```

Find:

```python
RemoteA2aAgent(...)
```

Then:

```python
root_agent = Agent(...)
```

Important: there is no import of `get_order` or `check_inventory`.

## Stage 6 — Start the customer application

### Terminal 3

```bash
source .venv/bin/activate
source lab.env
adk web 02_customer_orchestrator --port "$ORCHESTRATOR_PORT"
```

Open:

```text
http://127.0.0.1:8000
```

Select `customer_orchestrator`.

## Stage 7 — Local-only prompt

```text
Hello. What kind of questions can you help me with?
```

Not every turn should require A2A.

## Stage 8 — Real delegation

```text
Can order ORD-1002 be fulfilled from its assigned warehouse?
Explain the reason using current order and inventory evidence.
```

Expected business evidence:

```text
ORD-1002
WH-BLR-02
SKU-4400
required = 40
available = 7
cannot fulfil
```

Conceptually:

```text
Customer Agent
 ↓
RemoteA2aAgent
 ↓
A2A
 ↓
Fulfilment Specialist
 ↓
get_order → check_inventory
 ↓
specialist conclusion
 ↓
A2A
 ↓
Customer Agent / User
```

## Stage 9 — Different outcome

```text
Now check ORD-1001. Can its assigned warehouse fulfil it?
```

Expected:

```text
required = 12
available = 38
can fulfil
```

## Stage 10 — Prove opacity

Using only the Agent Card, identify:

1. agent name,
2. description,
3. endpoint,
4. advertised capabilities/skills.

Then ask whether the card exposes:

5. the system instruction,
6. internal tool implementation.

It should not need to.

## Stage 11 — Break the remote boundary

Stop Terminal 1 with `Ctrl+C`.

Keep ADK Web running.

Ask:

```text
Check whether ORD-1002 can currently be fulfilled.
```

The customer agent exists; its remote specialist does not.

```text
Customer Agent lifecycle != Specialist Agent lifecycle
```

Restart Terminal 1 and retry.

## Stage 12 — Final comparison

```text
MCP: Agent → protocol → capability
A2A: Agent → protocol → independent agent
```

You are complete when you can explain the Agent Card, `RemoteA2aAgent`,
delegation, opacity and independent failure boundary.
