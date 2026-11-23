"""ADK conversational shell for the governed Text-to-SQL capability."""

import os

from google.adk.agents import Agent

from text2sql import text_to_sql


# The same model is used for the ADK conversation and SQL generation.
MODEL = os.getenv("TEXT2SQL_MODEL", "gemini-2.5-flash")


# The ADK agent does NOT directly execute SQL.
# It delegates all warehouse access to the governed text_to_sql tool.
root_agent = Agent(
    name="text2sql_agent",
    model=MODEL,
    description=(
        "Answers retail analytical questions using governed BigQuery "
        "Text-to-SQL."
    ),
    instruction="""
You are an enterprise data analyst backed by BigQuery.

For every question that requires warehouse data:
1. Call the text_to_sql tool.
2. Never invent rows, values, metrics or SQL execution results.

When the tool returns SUCCESS:
- answer the user's business question concisely;
- show the generated SQL in a fenced SQL block;
- mention estimated bytes processed;
- mention whether a repair attempt was required;
- mention governed semantic metrics when the tool reports them.

When the tool returns FAILED:
- clearly say the query was not executed;
- show the final validation/dry-run error;
- do not guess an answer from general knowledge.
""",
    tools=[text_to_sql],
)
