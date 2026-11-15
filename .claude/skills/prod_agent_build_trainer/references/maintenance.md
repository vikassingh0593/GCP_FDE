# Keeping this skill up to date

When a new session or project teaches something, fold it in here. The skill should grow by adding checks, not by adding length to `SKILL.md`.

## When a new module arrives

A new session folder, or a new topic added to an existing one, means `concepts.md`, `arch.md` and this skill all get checked and updated in the same pass, so none of them falls behind. Add only what is relevant: if a topic is already covered, leave it alone.

1. **Find what's new.** Compare the session folders with the Coverage table below. Sessions often start as a copy of the one before, so diff a new folder against the previous session.
2. **Read all of it:** code, guides, `instructions.md`, raw notes and assignment briefs. Don't run the session's code to do this.
3. **List the new topics.** For each one, work out what a builder must understand and what breaks in production without it.
4. **Update `concepts.md`.** Put each topic in its matching section, or in a new section in build order, with the same fixed headings. Leave out module tags, setup steps and project specifics. Update the quick map and the "Covers Sessions" line.
5. **Update `arch.md`** if the module adds or changes a flow: the diagram, its GCP and Databricks table, and the list at the top. If no flow changed, leave the file alone and say so.
6. **Update this skill,** using the table below. Add checks to the matching stage, and errors to `troubleshooting.md`.
7. **Finish.** Add the session to the Coverage table, run the self-check, and report the new topics and which files changed.

## What belongs where

| What you learned | Where it goes |
|---|---|
| Something a builder must get right | A new check in the matching `stage-*.md` |
| A concept or service explanation | `concepts.md`, in the matching section |
| A new architecture flow or step | `arch.md` |
| An error message and its cause | `troubleshooting.md` |
| A mistake that code can detect | A rule in `scripts/scan_project.py`, plus a test |
| A retired model | `RETIRED_MODELS` in `scripts/scan_project.py` |
| A change in how the trainer behaves | `SKILL.md` |

Explanations stay in `concepts.md` and `arch.md`. Stage files hold checks and point to those files, so each fact lives in one place.

## How to add a check

1. Read the new session's material, and work out what would go wrong in production without it.
2. Add a check with the next free ID in that stage, using this exact shape:
   ```markdown
   ### OR-19 · High · The rule, stated as what good looks like
   - **Look for:** what to find in the code or design.
   - **Why:** the production failure, in plain words.
   - **Fix:** the specific change.
   ```
3. Never renumber an existing check. IDs are referenced by the scanner, the troubleshooting table and past reviews.
4. Add `(scan)` to the heading if the scanner detects it.
5. If it needs a new stage, add it to the table in `SKILL.md`.
6. Add a question to the stage's **Defend it** list if the new idea is one a person should be able to explain.
7. Update the coverage table below.

## What to keep out

- Project IDs, bucket names, customer names and values from env files.
- Anything specific to one class exercise. Keep the general lesson. A real incident is welcome as an example, without identifying details.
- Advice that hasn't been checked. Confirm ADK behavior against the installed source.

## How to verify a change

```bash
python3 -I .claude/skills/prod_agent_build_trainer/tests/run_checks.py
```

This confirms that the scanner catches the planted bugs, stays quiet on clean code, and that every check ID mentioned anywhere exists in a stage file. Fix any failure before finishing.

For a change to how the trainer behaves, also try the prompts in `evals/` in a new session.

## Coverage

| Session | Topic | Stage |
|---|---|---|
| 1 | Tokenizers and token basics | concepts.md §10 |
| 2 | Calling Gemini on Vertex AI | 4 |
| 3 | Prompting, structured output, model selection, security, governance | 2, 4, 10 |
| 4 | Advanced RAG patterns | 2 |
| 5 | Function calling, ADK basics | 4 |
| 6 | Harness: routing, hybrid search, reranking, text-to-SQL tool | 2, 3, 5 |
| 7 | Google-native RAG: Document AI, BigQuery, Ranking API | 2 |
| 8 | MedEvidence: end-to-end build, evaluation, guardrails | 2, 4, 5, 9, 11 |
| 9 | Text-to-SQL with validation and catalog retrieval | 3 |
| 10 | Ontology, knowledge graph, Text-to-Cypher | 3 |
| 11 | Function-calling contract, manual loop, modes | 4 |
| 12 | ADK runtime pieces, callbacks, plugins, failure taxonomy | 6 |
| 13 | Enterprise runtime harness, trusted context, compliance challenge | 6, 10 |
| 14 | Semantic orchestrator | 5 |
| 15 | Enterprise semantic orchestration challenge, discovery | 1, 5, 9, 11 |
| 16 | Sessions, state, memory | 7 |
| 17 | Serving the agent through an API and web UI | 7, 8 |
| 18 | MCP: tools on an MCP server, `McpToolset` client | 4, 5 |
| 19 | A2A: `to_a2a` specialist, Agent Card, `RemoteA2aAgent`, independent failure | 5 |
| 20 | Capstones (pending: folded in after the capstone is worked through, so the notes don't give away its answers) | — |
| Beyond the course | Action agents, MCP and A2A, responsible AI, platform security, reliability, delivery | 4, 5, 10, 11 |

Enterprise additions that weren't taught stay marked "beyond the course" in `concepts.md` and `arch.md`.
