#!/usr/bin/env python3
"""Verify the skill: scanner behavior, and that every check ID really exists.

Run: python3 -I .claude/skills/prod_agent_build_trainer/tests/run_checks.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCANNER = SKILL / "scripts" / "scan_project.py"
FIXTURES = SKILL / "tests" / "fixtures"
CHECK_ID = re.compile(r"\b(?:AG|DB|DS|EV|KN|OP|OR|RT|SE|ST|SV)-\d{2}\b")

EXPECTED_BROKEN = {
    "AG-01", "AG-02", "AG-03", "AG-10", "AG-17", "DB-09", "EV-02", "KN-24", "OP-04", "OP-12",
    "OR-21", "RT-04", "SE-01", "SE-06", "SE-11", "ST-01", "ST-04", "ST-05", "ST-06",
    "ST-08", "ST-13", "SV-01", "SV-05", "SV-06", "SV-11",
}


def scan(path: Path) -> dict:
    result = subprocess.run([sys.executable, "-I", str(SCANNER), str(path), "--json"],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def defined_checks() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted((SKILL / "references").glob("stage-*.md")):
        for match in re.finditer(r"^### ([A-Z]{2}-\d{2}) · (\w+) · ", path.read_text(encoding="utf-8"), re.M):
            if match.group(1) in found:
                raise SystemExit(f"Duplicate check ID: {match.group(1)}")
            found[match.group(1)] = match.group(2)
    return found


def main() -> int:
    failures: list[str] = []

    broken = scan(FIXTURES / "broken")["findings"]
    missing = EXPECTED_BROKEN - {item["check"] for item in broken}
    extra = {item["check"] for item in broken} - EXPECTED_BROKEN
    failures += [f"Scanner missed {check}" for check in sorted(missing)]
    failures += [f"Scanner reported unexpected {check}" for check in sorted(extra)]
    leaked = [item for item in broken if "hunter2" in item["message"]]
    failures += ["Scanner printed a secret value"] if leaked else []

    clean = scan(FIXTURES / "clean")["findings"]
    failures += [f"False positive on clean code: {item['check']} {item['file']}:{item['line']}" for item in clean]

    checks = defined_checks()
    scanner_ids = set(CHECK_ID.findall(SCANNER.read_text(encoding="utf-8")))
    failures += [f"Scanner uses undefined check {check}" for check in sorted(scanner_ids - set(checks))]

    for path in [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]:
        for check in set(CHECK_ID.findall(path.read_text(encoding="utf-8"))) - set(checks):
            failures.append(f"{path.name} mentions undefined check {check}")

    scan_marked = {check for path in (SKILL / "references").glob("stage-*.md")
                   for check in re.findall(r"^### ([A-Z]{2}-\d{2}) .*\(scan\)$", path.read_text(encoding="utf-8"), re.M)}
    failures += [f"{check} is marked (scan) but the scanner never reports it" for check in sorted(scan_marked - scanner_ids)]
    failures += [f"{check} is reported by the scanner but not marked (scan)" for check in sorted(scanner_ids - scan_marked)]

    print(f"{len(checks)} checks defined, {len(scanner_ids)} detected by the scanner.")
    if failures:
        print("\n".join(f"FAIL  {item}" for item in failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
