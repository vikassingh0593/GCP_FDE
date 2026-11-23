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
os.environ.setdefault("MEDEVIDENCE_RUN_TAG", "record")  # test traffic is tagged (D60)
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

# Step 5b: historical with a date (one before the first document, D39) and document lookups (D36, D37).
AS_OF = [
    ("What was the AX-17 renal dose in Germany?", "Germany", "2018-12-31"),
    ("What was the renal starting dose for moderate impairment in Germany?", "Germany", "2025-06-30"),
]
LOOKUPS = [  # (document_id, table, rows, question)
    ("HN-204", "Table 14", "", ""),
    ("HN-311", "Table 14", "Nausea", ""),
    ("DE-AX17-LBL-038", "renal dosing", "", ""),
    ("US-AX17-PI-050", "renal", "", ""),
    ("DE-AX17-LBL-038", "", "", "What did this label say about moderate renal impairment?"),
]

for question, mode, country in QUESTIONS:
    result = rt.answer(question, mode=mode, country=country, caller="record_fixtures")
    print(f"recorded  {result['outcome']:12} {question}")
for question, country, as_of in AS_OF:
    result = rt.answer(question, mode="historical", country=country, as_of=as_of, caller="record_fixtures")
    print(f"recorded  {result['outcome']:12} {question} (as of {as_of})")
print(f"recorded  catalogue ({len(rt.catalogue().splitlines())} lines)")  # D46: registry + all tables
for doc, table, rows, question in LOOKUPS:
    result = rt.lookup(doc, table=table, rows=rows, question=question, caller="record_fixtures")
    print(f"recorded  {result['outcome']:12} lookup {doc} {table or question or 'facts'}")

# Step 6: study comparison (D48) and governed text-to-SQL (D49).
import text2sql  # noqa: E402
for ids, event in [(["HN-204", "HN-311"], ""), (["hn-204", "HN-402"], "nausea"), (["HN-204", "DE-AX17-LBL-042"], "")]:
    q = "Compare AE evidence in HN-204 and HN-311." if not event and "HN-311" in ids else ""
    result = rt.compare(ids, event=event, question=q, caller="record_fixtures")
    print(f"recorded  {result['outcome']:12} compare {ids} {event}")
for question in ["Which study had the highest rash rate?", "What is the average age of patients in HN-204?"]:
    result = text2sql.ask(question, caller="record_fixtures")
    print(f"recorded  {result['outcome']:12} sql: {question}")
print("recorded  dry run of a bypass query:", text2sql.dry_run(
    "SELECT chunk_id FROM `tredence-fde-1.medevidence_v1_vks.chunks` LIMIT 1")[:2])

# Step 7: a premise question (D55) and the patient hand-off with its general reference (D52).
# Note: recording writes one real row per run to BigQuery `escalations` (caller record_fixtures).
import escalation  # noqa: E402
result = rt.answer("The current moderate starting dose in Germany is 25 mg, so severe must be 12.5 mg, right?",
                   mode="current", country="Germany", caller="record_fixtures")
print(f"recorded  {result['outcome']:12} premise question ({result.get('number_check')})")
result = escalation.escalate("patient_specific", "My 70-year-old patient has eGFR 35. What dose should I give him?",
                             "renal dosing guidance for moderate impairment and hepatic monitoring", "Germany",
                             caller="record_fixtures")
print(f"recorded  {result['outcome']:12} escalation {result.get('escalation_id')}")

# D66: a wrong-column answer checked by Check Grounding (regression for the Step 4 bug).
cards = rt.answer("Current AX-17 renal guidance in Germany?", mode="current", country="Germany", caller="record_fixtures")["cards"]
g = rt.grounding("For moderate renal impairment the starting dose is 50 mg once daily [E2].", cards)
print(f"recorded  grounding of a wrong-column answer: support {g['score']}")

# D67: queries the SQL analyst's tools are tested with offline (dry run + run recorded).
view = text2sql.view_ids()["v_adverse_events"]
for sql in (f"SELECT study_id, treatment_rate_pct FROM `{view}` WHERE event = 'rash' ORDER BY treatment_rate_pct DESC LIMIT 1",
            f"SELECT study_id, treatment_rate_pct FROM `{view}` WHERE event = 'Rash' ORDER BY treatment_rate_pct DESC LIMIT 1"):
    print("recorded  dry run + run:", text2sql.dry_run(sql)[:2], text2sql.run_sql(sql)[1], "rows")

# D70: the patient-case classifier's verdicts (tests/patient_cases.json), also runnable on their own.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_patient_fixtures  # noqa: E402

record_patient_fixtures.record()
