"""Record the runtime responses the offline tests replay (needs Google Cloud once).

Run from submission/ after `source env.sh`:
    MEDEVIDENCE_RECORD=1 python tests/record_runtime_fixtures.py

Re-run after changing the corpus, filters, prompts or models, then commit the
updated tests/fixtures/runtime/ files.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if os.getenv("MEDEVIDENCE_RECORD") != "1":
    raise SystemExit("Set MEDEVIDENCE_RECORD=1 to record fixtures.")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import rag_runtime as rt  # noqa: E402

QUESTIONS = [
    ("Current AX-17 renal guidance in Germany?", "current", "Germany"),
    ("German AX-17 guidance before latest revision?", "historical", "Germany"),
    ("What does SB-AX17-2026-09 require?", "current", "Germany"),
    ("Approved AX-17 dosage in Japan?", "current", "Japan"),
    ("Does AX-17 interact with warfarin?", "current", "Germany"),
    ("What does HN-SAF-017 say?", "current", "Germany"),
    # Regression (Step 4): thinking off put "25 mg/day" (the maximum) in the starting-dose column.
    ("What is the current renal starting dose of AX-17?", "current", "Germany"),
]

for question, mode, country in QUESTIONS:
    result = rt.answer(question, mode=mode, country=country, caller="record_fixtures")
    print(f"recorded  {result['outcome']:12} {question}")
