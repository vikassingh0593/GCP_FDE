"""Governed text-to-SQL (Step 6, decision D49): Gemini writes the SQL, code decides whether it runs.

For analytical questions a search cannot answer exactly: "Which study had the
highest rash rate?", "How many approved documents per country?". Known
questions use verified SQL instead (compare_studies, in rag_runtime.py).

Pattern from session-09 `Text-To-SQL/03_HARNESS/text2sql.py`, adapted:
  - No catalogue RAG: two curated views, so the whole schema fits in the prompt.
    It is built from BigQuery's own metadata (columns + descriptions), never
    written by hand, so a new column reaches the prompt by itself.
  - A stronger allowlist. Session 09 checks the dataset prefix with a regex. Here
    (1) every table named in the SQL text must be an allowed view, and (2) the
    dry run reports the BASE tables the query really reads (views expanded, WITH
    clauses included), which must be exactly the tables behind the allowed views.
    A query that reaches `chunks`, the logs or INFORMATION_SCHEMA never runs.
  - The rows are the answer: shown word for word with the SQL, no Gemini prose
    on top (D31), so no number is reworded after the query ran.

Pipeline: schema → Gemini writes SQL → code checks → dry run (tables, bytes) →
one repair with the error → run (byte cap, row cap) → rows + SQL.

Command line (from submission/, after `source env.sh`):
    python src/text2sql.py "Which study had the highest rash rate?"
"""

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from datetime import datetime
from functools import lru_cache

from google.cloud import bigquery
from google.genai import types

import rag_runtime as rt
import replay
from config import (BQ_DATASET, GENERATION_MODEL, MAX_SQL_BYTES, MAX_SQL_ROWS, MAX_TABLE_ROWS, PROJECT_ID,
                    VERTEX_LOCATION, table_id)
from policy import BLOCKED_SQL, SQL_VIEWS


MAX_REPAIRS = 1  # session 09: one repair with the BigQuery error, then give up honestly


def view_ids() -> dict[str, str]:
    """Allowed view name → fully qualified ID (the only objects the SQL may name)."""
    return {v: table_id(v) for v in SQL_VIEWS}


MAX_EXAMPLE_VALUES = 20  # a text column with at most this many distinct values shows them all to the model


@lru_cache(maxsize=1)
def schema() -> list[dict]:
    """Columns, descriptions and, for short text columns, their REAL values, read from BigQuery.

    Example values are the standard text-to-SQL fix for wrong literals: without them Gemini
    wrote event = 'Rash' while the data says 'rash' (0 rows, found by the offline tests).
    """
    def fetch():
        out = []
        for name, full in view_ids().items():
            tbl = rt._bq().get_table(full)
            columns = []
            for f in tbl.schema:
                col = {"name": f.name, "type": f.field_type + (" (repeated)" if f.mode == "REPEATED" else ""),
                       "description": f.description or ""}
                if f.field_type == "STRING" and f.mode != "REPEATED":
                    rows = rt._bq().query(f"SELECT DISTINCT `{f.name}` AS v FROM `{full}` WHERE `{f.name}` IS NOT NULL "
                                          f"LIMIT {MAX_EXAMPLE_VALUES + 1}").result()
                    values = [r["v"] for r in rows]
                    if len(values) <= MAX_EXAMPLE_VALUES and all(len(v) <= 60 for v in values):
                        col["values"] = sorted(values)
                columns.append(col)
            out.append({"view": full, "description": tbl.description or "", "columns": columns})
        return out
    return replay.call("sql_schema", {"views": list(SQL_VIEWS)}, fetch)


@lru_cache(maxsize=1)
def allowed_base_tables() -> set[str]:
    """The base tables behind the allowed views, learned by dry-running each view."""
    def fetch():
        bases = set()
        for full in view_ids().values():
            job = rt._bq().query(f"SELECT * FROM `{full}`", job_config=bigquery.QueryJobConfig(dry_run=True))
            bases |= {f"{t.project}.{t.dataset_id}.{t.table_id}" for t in job.referenced_tables}
        return sorted(bases)
    return set(replay.call("sql_bases", {"views": list(SQL_VIEWS)}, fetch))


def schema_text() -> str:
    lines = []
    for v in schema():
        lines.append(f"`{v['view']}`" + (f": {v['description']}" if v["description"] else ""))
        lines += [f"  - {c['name']} {c['type']}" + (f": {c['description']}" if c["description"] else "")
                  + (f" Values: {', '.join(repr(x) for x in c['values'])}." if c.get("values") else "") for c in v["columns"]]
    return "\n".join(lines)


# Shared by the fixed pipeline below and the SQL analyst agent (harness/sql_agent.py, D67): one copy.
SQL_STYLE_RULES = """- Use only the views above, always fully qualified with backticks exactly as written.
- One SELECT statement (WITH ... SELECT allowed). No semicolon. Never change data.
- Select only the columns the answer needs, never SELECT *. When listing documents include document_id and
  status; when listing study rows include study_id.
- Rankings ("highest", "top 3") use ORDER BY and LIMIT, and also select the value they are ranked by (e.g. the
  rate), so the user sees why. Always end with LIMIT {max_rows} or less.
- Rates are percentages per study. Never add or average rates across studies unless the question asks for it.
- `countries` is an array: use UNNEST to filter or group by country.
- Use text values exactly as listed under Values; compare free text case-insensitively (LOWER(col) = 'x').
- Give every computed column a readable name (e.g. AVG(treatment_rate_pct) AS avg_treatment_rate_pct)."""

SQL_RULES = """You write ONE BigQuery Standard SQL query that answers the question from these views only:

{schema}

Rules:
""" + SQL_STYLE_RULES + """
- If the views cannot answer the question, return an empty sql and say why in reason.
Return JSON: sql, reason."""

SQL_SCHEMA = {"type": "object", "properties": {"sql": {"type": "string"}, "reason": {"type": "string"}},
              "required": ["sql", "reason"]}


def write_sql(question: str, previous: str = "", error: str = "") -> dict:
    """Gemini writes the SQL (JSON output, temperature 0); on a repair it sees its SQL and the error."""
    key = {"question": question, "previous": previous, "error": error, "model": GENERATION_MODEL, "views": list(SQL_VIEWS)}
    return replay.call("sql_write", key, lambda: _write_sql_remote(question, previous, error))


def _write_sql_remote(question: str, previous: str, error: str) -> dict:
    prompt = SQL_RULES.replace("{schema}", schema_text()).replace("{max_rows}", str(MAX_SQL_ROWS))
    prompt += f"\n\nQuestion: {question}"
    if previous:
        prompt += f"\n\nYour previous SQL was rejected.\nSQL: {previous}\nReason: {error}\nWrite a corrected query."
    response = rt.with_retry(lambda: rt._genai(VERTEX_LOCATION).models.generate_content(
        model=GENERATION_MODEL, contents=prompt,
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                           response_schema=SQL_SCHEMA),
    ), "gemini-sql")
    return json.loads(response.text)


def check_sql(sql: str) -> tuple[bool, str]:
    """Code checks BEFORE BigQuery sees the query (session 09, plus the view allowlist)."""
    clean = sql.strip().rstrip(";").strip()
    if not re.match(r"^(SELECT|WITH)\b", clean, re.IGNORECASE):
        return False, "only SELECT or WITH queries are allowed"
    if ";" in clean:
        return False, "only one statement is allowed"
    if BLOCKED_SQL.search(clean):
        return False, "statements that change data or permissions are blocked"
    if re.search(r"INFORMATION_SCHEMA", clean, re.IGNORECASE):
        return False, "metadata tables are not allowed"
    allowed = {f.lower() for f in view_ids().values()}
    for ref in re.findall(r"`([^`]+)`", clean):
        if "." in ref and ref.lower() not in allowed:
            return False, f"only the curated views may be read, not {ref}"
    # Without backticks a table can still be named (medevidence_v1_vks.adverse_events): once
    # the allowed views are removed, our dataset or project must not appear anywhere. The
    # dry run alone would not catch this one: the base table IS behind an allowed view.
    rest = clean.lower()
    for full in sorted(allowed, key=len, reverse=True):
        rest = rest.replace(f"`{full}`", " ").replace(full, " ")
    if BQ_DATASET.lower() in rest or PROJECT_ID.lower() in rest:
        return False, "only the curated views may be read (a base table or other object is named)"
    return True, "ok"


def dry_run(sql: str) -> tuple[bool, str, int]:
    """BigQuery compiles the query without running it: syntax, columns, base tables read, bytes."""
    def fetch():
        try:
            job = rt._bq().query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            return {"bases": sorted(f"{t.project}.{t.dataset_id}.{t.table_id}" for t in job.referenced_tables),
                    "bytes": int(job.total_bytes_processed or 0), "error": ""}
        except Exception as exc:  # the BigQuery error is the repair hint
            return {"bases": [], "bytes": 0, "error": str(exc)[:500]}
    out = replay.call("sql_dry", {"sql": sql}, fetch)
    if out["error"]:
        return False, out["error"], 0
    outside = sorted(set(out["bases"]) - allowed_base_tables())
    if outside:
        return False, f"the query reads tables outside the curated views: {', '.join(outside)}", out["bytes"]
    if out["bytes"] > MAX_SQL_BYTES:
        return False, f"the query would scan {out['bytes']:,} bytes (limit {MAX_SQL_BYTES:,})", out["bytes"]
    return True, "ok", out["bytes"]


def run_sql(sql: str) -> tuple[list[dict], int]:
    """Run with a byte cap and fetch at most MAX_SQL_ROWS rows; returns (rows, total rows)."""
    def fetch():
        job = rt._bq().query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_SQL_BYTES))
        it = job.result(max_results=MAX_SQL_ROWS)
        return {"rows": [dict(r.items()) for r in it], "total": int(it.total_rows or 0)}
    out = replay.call("sql_run", {"sql": sql}, lambda: rt.with_retry(fetch, "bigquery-sql"))
    return out["rows"], out["total"]


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(value, (list, tuple)):
        return ", ".join(_cell(v) for v in value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).replace("|", "/")


def format_rows(rows: list[dict], total: int, sql: str) -> str:
    """Rows word for word (≤ MAX_TABLE_ROWS shown), then the SQL and what was read."""
    views = sorted({v for v, full in view_ids().items() if full in sql})
    lines = [f"Result of a read-only query on {', '.join(views)} ({total} row{'s' if total != 1 else ''}):", ""]
    if rows:
        cols = list(rows[0])
        lines += ["| " + " | ".join(cols) + " |", "|" + "|".join(["-"] * len(cols)) + "|"]
        lines += ["| " + " | ".join(_cell(r[c]) for c in cols) + " |" for r in rows[:MAX_TABLE_ROWS]]
        if total > MAX_TABLE_ROWS:
            lines.append(f"\nShowing {MAX_TABLE_ROWS} of {total} rows. Ask a narrower question to see the rest.")
    else:
        lines.append("The query returned no rows.")
    lines += ["", "SQL:", sql.strip()]
    return "\n".join(lines)


def ask(question: str, caller: str = "cli") -> dict:
    """The governed pipeline; returns a result shaped like rag_runtime's, logged to agent_log."""
    t0 = time.perf_counter()
    rt._retries.clear()
    result = {"log_id": uuid.uuid4().hex, "question": question, "mode": "sql", "country": None,
              "filters": {"views": list(SQL_VIEWS)}, "candidates": [], "reranked": [], "cards": [], "reasons": [],
              "latency_ms": {}, "sources": "", "notes": [], "citation_check": "rows shown verbatim (no generation)"}
    previous, error, attempts = "", "", []
    lat = result["latency_ms"]  # per stage, so a slow question shows which stage (66 s seen in testing)
    try:
        for attempt in range(MAX_REPAIRS + 1):
            t = time.perf_counter(); out = write_sql(question, previous, error)
            lat["write_sql"] = lat.get("write_sql", 0) + round((time.perf_counter() - t) * 1000)
            sql = (out.get("sql") or "").strip().rstrip(";").strip()
            if not sql:  # the model says the views cannot answer it: honest, not a failure to hide
                result.update(outcome="insufficient", reasons=[out.get("reason", "")],
                              answer="This can't be answered from the structured data "
                                     f"({out.get('reason') or 'no matching columns'}). Ask me with a country or a "
                                     "document ID and I'll search the documents instead.")
                break
            ok, error = check_sql(sql)
            if ok:
                t = time.perf_counter(); ok, error, scanned = dry_run(sql)
                lat["dry_run"] = lat.get("dry_run", 0) + round((time.perf_counter() - t) * 1000)
            attempts.append({"sql": sql, "ok": ok, "error": "" if ok else error})
            if ok:
                t = time.perf_counter(); rows, total = run_sql(sql)
                lat["run_sql"] = round((time.perf_counter() - t) * 1000)
                result.update(outcome="answered", sql=sql, answer=format_rows(rows, total, sql),
                              rows_total=total, bytes_scanned=scanned)
                break
            previous = sql
        else:
            result.update(outcome="blocked", sql=attempts[-1]["sql"], reasons=[a["error"] for a in attempts],
                          answer=f"I couldn't build a safe query for this question ({attempts[-1]['error'][:200]}). "
                                 "Try asking it more simply, or ask with a country to search the documents.")
    except Exception as exc:  # never crash the conversation
        result.update(outcome="error", reasons=[str(exc)[:200]],
                      answer="The data service is busy right now; please try again in a minute.")
    result["filters"]["attempts"] = attempts
    result["latency_ms"]["total"] = round((time.perf_counter() - t0) * 1000)
    rt.log_question(result, caller)
    return result


if __name__ == "__main__":
    r = ask(" ".join(sys.argv[1:]) or "Which study had the highest rash rate?")
    print(f"OUTCOME: {r['outcome']}\nATTEMPTS: {json.dumps(r['filters']['attempts'], indent=1)}\n\n{r['answer']}")
