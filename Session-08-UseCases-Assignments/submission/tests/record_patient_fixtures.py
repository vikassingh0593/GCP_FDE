"""Record the patient-case classifier's verdicts the offline tests replay (D70; needs Google Cloud once).

Run from submission/ after `source env.sh` (also run at the end of record_runtime_fixtures.py):
    MEDEVIDENCE_RECORD=1 python tests/record_patient_fixtures.py

Re-run after changing tests/patient_cases.json, policy.PATIENT_CASE_QUESTION or PATIENT_CHECK_MODEL.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CASES = json.loads((TESTS / "patient_cases.json").read_text(encoding="utf-8"))


def record() -> None:
    if os.getenv("MEDEVIDENCE_RECORD") != "1":
        raise SystemExit("Set MEDEVIDENCE_RECORD=1 to record fixtures.")
    sys.path.insert(0, str(TESTS.parent / "src"))
    import patient_check

    for expected, messages in (("patient", CASES["patient"]), ("information", CASES["information"])):
        for message in messages:
            verdict = patient_check.classify(message)
            flag = "" if (verdict["patient_case"] != "no") == (expected == "patient") else "   ← NOT AS EXPECTED"
            print(f"[patient_check] {verdict['patient_case']:6} [{expected}] {message[:70]}{flag}")


if __name__ == "__main__":
    record()
