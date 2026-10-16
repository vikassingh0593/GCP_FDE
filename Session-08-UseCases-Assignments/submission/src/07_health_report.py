"""Health report (Step 8): ingestion, evaluation, agent usage and hand-offs on one page.

Read-only. Every value is rated green / amber / red against health_thresholds.json
(data, not code) and compared with the previous evaluation run, so a drop shows
as a trend, not as a one-off printout. Test traffic (run_tag eval / demo / smoke /
record, D60) is kept apart from real usage.

Sources (BigQuery): pipeline_health (ingestion checks + eval metrics),
agent_log (every question), escalations (hand-offs).
In production the same queries feed a Looker Studio dashboard and Cloud
Monitoring alerts (§13).

Run from submission/:  source env.sh && python src/07_health_report.py
Output: output/health_report.md (and printed).
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud import bigquery

from config import BQ_ESCALATIONS_TABLE, OUTPUT_DIR, PROJECT_ID, table_id
from eval_scoring import load_thresholds, rate
from health import HEALTH_TABLE

ICON = {"green": "🟢", "amber": "🟠", "red": "🔴", "n/a": "⚪"}
DAYS = 7


def q(client: bigquery.Client, sql: str) -> list[dict]:
    return [dict(r.items()) for r in client.query(sql).result()]


def has_column(client: bigquery.Client, table: str, column: str) -> bool:
    try:
        return column in {f.name for f in client.get_table(table_id(table)).schema}
    except Exception:
        return False


def row(name: str, value, rule: dict | None, note: str = "") -> str:
    rating = rate(value, rule) if rule else "n/a"
    shown = "n/a" if value is None else (f"{value:.3g}" if isinstance(value, float) else value)
    limits = f"{'≤' if rule.get('direction') == 'below' else '≥'} {rule['green']} / {rule['amber']}" if rule else ""
    return f"| {ICON[rating]} | {name} | {shown} | {limits} | {note} |"


def main() -> None:
    client = bigquery.Client(project=PROJECT_ID)
    th = load_thresholds()
    out = [f"# MedEvidence health report · {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", "",
           "| | metric | value | green / amber | note |", "|---|---|---|---|---|"]

    # 1. Ingestion: the latest pipeline run.
    runs = q(client, f"""SELECT run_id, MAX(recorded_at) AS last_at FROM `{table_id(HEALTH_TABLE)}`
                         WHERE stage != 'eval' GROUP BY run_id ORDER BY last_at DESC LIMIT 1""")
    problems = []
    if runs:
        rid = runs[0]["run_id"]
        checks = q(client, f"""SELECT stage, `check`, document_id, status, details FROM `{table_id(HEALTH_TABLE)}`
                               WHERE run_id = '{rid}'""")
        fails = [c for c in checks if c["status"] == "fail"]
        warns = [c for c in checks if c["status"] == "warn"]
        problems = fails + warns
        out.append("| | **Ingestion** (latest run) | | | |")
        out.append(row("failed checks", len(fails), th["ingestion"]["fail_checks"], f"run {rid}, {len(checks)} checks"))
        out.append(row("warnings", len(warns), th["ingestion"]["warn_checks"]))

    # 2. Evaluation: the last two runs, with the trend.
    eval_runs = q(client, f"""SELECT run_id, MAX(recorded_at) AS last_at FROM `{table_id(HEALTH_TABLE)}`
                              WHERE stage = 'eval' GROUP BY run_id ORDER BY last_at DESC LIMIT 2""")
    if eval_runs:
        ids = ", ".join(f"'{r['run_id']}'" for r in eval_runs)
        values = q(client, f"""SELECT run_id, `check`, value FROM `{table_id(HEALTH_TABLE)}`
                               WHERE stage = 'eval' AND run_id IN ({ids})""")
        latest = {v["check"]: v["value"] for v in values if v["run_id"] == eval_runs[0]["run_id"]}
        previous = {v["check"]: v["value"] for v in values if len(eval_runs) > 1 and v["run_id"] == eval_runs[1]["run_id"]}
        out.append(f"| | **Evaluation** (run {eval_runs[0]['run_id']}) | | | |")
        for name, rule in th["eval"].items():
            if name in latest:
                before = previous.get(name)
                trend = "" if before is None else ("→ same" if before == latest[name] else f"was {before:.3g}")
                out.append(row(name, latest[name], rule, trend))

    # 3. Agent usage (last DAYS days): real use apart from tagged test traffic.
    tagged = "run_tag IS NOT NULL" if has_column(client, "agent_log", "run_tag") else "FALSE"
    usage = q(client, f"""
        SELECT IF({tagged}, 'test', 'real') AS kind, COUNT(*) AS n,
               COUNTIF(outcome = 'error') AS errors, COUNTIF(outcome = 'blocked') AS blocked,
               COUNTIF(outcome IN ('insufficient', 'not_found')) AS abstained,
               COUNTIF(retries IS NOT NULL AND retries != '{{}}') AS busy,
               APPROX_QUANTILES(CAST(JSON_VALUE(latency_ms, '$.total') AS INT64), 100)[OFFSET(95)] / 1000 AS p95_s
        FROM `{table_id('agent_log')}`
        WHERE logged_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {DAYS} DAY)
        GROUP BY kind""")
    for u in sorted(usage, key=lambda u: u["kind"]):
        out.append(f"| | **Agent questions, {u['kind']}** (last {DAYS} days: {u['n']}) | | | |")
        n = u["n"] or 1
        out.append(row("error rate", u["errors"] / n, th["agent"]["error_rate"]))
        out.append(row("blocked rate (citation / number checks)", u["blocked"] / n, th["agent"]["blocked_rate"]))
        out.append(row("busy (429/503) retry rate", u["busy"] / n, th["agent"]["busy_retry_rate"]))
        out.append(row("p95 latency (s)", u["p95_s"], th["agent"]["latency_p95_s"],
                       f"abstained {u['abstained']} of {u['n']}"))

    # 4. Hand-offs waiting for a person.
    if has_column(client, BQ_ESCALATIONS_TABLE, "status"):
        tag = "run_tag IS NULL AND caller != 'record_fixtures'" if has_column(client, BQ_ESCALATIONS_TABLE, "run_tag") \
            else "caller != 'record_fixtures'"
        esc = q(client, f"""SELECT COUNTIF({tag}) AS real_open, COUNTIF(NOT ({tag})) AS test_open
                            FROM `{table_id(BQ_ESCALATIONS_TABLE)}` WHERE status = 'OPEN'""")[0]
        out.append("| | **Escalations** | | | |")
        out.append(row("open, real", esc["real_open"], th["escalations"]["open"],
                       f"{esc['test_open']} open from test runs (tagged)"))

    if problems:
        out += ["", "## Ingestion checks to look at", ""]
        out += [f"- **{c['status']}** · {c['stage']} · {c['check']}" + (f" · {c['document_id']}" if c["document_id"] else "")
                + (f": {c['details']}" if c["details"] else "") for c in problems[:20]]
    out += ["", "Rows from before Step 8 carry no run tag and count as real use."]
    text = "\n".join(out) + "\n"
    (OUTPUT_DIR / "health_report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
