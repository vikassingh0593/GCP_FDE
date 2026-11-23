"""Human-readable report for one trace row (session 13 report.py).

Used by the terminal runner (orchestrator/cli.py) and the evals, so a run can
be read without opening the JSON lines.
"""

from __future__ import annotations


def render_report(row: dict) -> str:
    b = row.get("budgets", {})
    lines = [
        "",
        "=" * 72,
        f"INVOCATION REPORT  ({row.get('service')})",
        "=" * 72,
        f"Correlation ID : {row.get('correlation_id')}",
        f"Parent         : {row.get('parent_correlation_id') or '-'}",
        f"Session        : {row.get('session_id')}",
        f"User           : {row.get('user')}",
        f"Environment    : {row.get('environment')}",
        f"Termination    : {row.get('termination')}",
        f"Elapsed        : {row.get('latency_s')}s / {b.get('seconds')}s",
        "",
        "BUDGET / USAGE",
        f"Model calls    : {row.get('model_calls')} / {b.get('model_calls')}",
        f"Tool calls     : {row.get('tool_calls')} / {b.get('tool_calls')}",
        f"Failures       : {row.get('failures')} / {b.get('failures')}",
        f"Tokens in/out  : {row.get('tokens', {}).get('in')} / {row.get('tokens', {}).get('out')}",
        f"Closing call   : {'used' if row.get('closing_call_used') else 'no'}"
        f"{'  (hard stop)' if row.get('hard_stop') else ''}",
        "",
        "TOOLS",
    ]
    for t in row.get("tools", []):
        lines.append(f"  - {t.get('tool'):<26} {t.get('outcome'):<14} {t.get('freshness') or ''}")
    for d in row.get("details", []):
        if d.get("strategy"):
            lines.append(f"  retrieval: {d.get('strategy')} | cache {d.get('cache')} | docs {d.get('docs')}")
        elif d.get("a2a"):
            lines.append(f"  a2a: {d.get('a2a')} | {d.get('outcome')} | {d.get('latency_ms')} ms")
    lines += ["", f"Evidence IDs   : {len(row.get('evidence_ids', []))} returned, "
                  f"{len(row.get('cited_ids', []))} cited, "
                  f"{len(row.get('invalid_citations', []))} unverified"]
    for bad in row.get("invalid_citations", []):
        lines.append(f"  UNVERIFIED     {bad}")
    lines += ["", "TRACE"]
    for i, event in enumerate(row.get("events", []), start=1):
        detail = {k: v for k, v in event.items() if k not in ("kind", "t")}
        lines.append(f"{i:02d}. +{event.get('t', 0):>7.3f}s {event.get('kind'):<24} {detail}")
    lines.append("=" * 72)
    return "\n".join(lines)
