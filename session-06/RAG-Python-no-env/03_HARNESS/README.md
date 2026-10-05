# Run the ADK Harness

From the project root, first load the same environment used during setup:

```bash
source 01_SETUP/lab.env
cd 03_HARNESS
adk web --port 8001
```

Select `harness_agent` in ADK Web.

## What to watch in the trace

- `Hi` should be answered directly by the root Gemini agent. **No RAG tool call.**
- Policy questions should hand off to `hybrid_rag_agent`, which calls `hybrid_policy_search`.
- Analytical questions should hand off to `text_to_sql_agent`, which calls the safe placeholder.
- Follow-up prompts should demonstrate that routing happens with conversation context, not as isolated keyword matching.
