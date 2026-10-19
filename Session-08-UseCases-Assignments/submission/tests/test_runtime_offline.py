"""Offline tests for the search runtime: no Google Cloud call, no cost, no 429s.

They replay responses recorded once from the real services
(tests/fixtures/runtime/, made with MEDEVIDENCE_RECORD=1) and check the code
around them: hard filters, authority roles, exact-ID routing, not-found and
insufficient paths, citation check and Sources links; and (Step 5b) the
historical date filter, document lookups, verbatim tables and the fixed notes
the tools add.

The runtime refuses to create any Google client in offline mode, so these
tests also prove that nothing reached the cloud.

Run from submission/:  pytest tests/
Re-record after changing the corpus, filters or prompts:
    MEDEVIDENCE_RECORD=1 python tests/record_runtime_fixtures.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MEDEVIDENCE_OFFLINE"] = "1"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tredence-fde-1")
os.environ.setdefault("GCS_BUCKET", "tredence-fde-1-medevidence-vks")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))

import rag_runtime as rt  # noqa: E402  (environment must be set before import)


def _docs(chunks):
    return {c["document_id"] for c in chunks}


def test_current_germany_uses_only_current_german_evidence():
    r = rt.answer("Current AX-17 renal guidance in Germany?", mode="current", country="Germany")
    assert r["outcome"] == "answered"
    # Hard filters: the US label and the superseded v3.8 never reach the search.
    assert not _docs(r["candidates"]) & {"US-AX17-PI-050", "DE-AX17-LBL-038", "DE-AX17-HSL-2019-2021"}
    # Table 3 is in the evidence, its card is local guidance, and the link opens page 6.
    table3 = [c for c in r["cards"] if c["chunk"]["table_id"] == "Table 3"]
    assert table3 and table3[0]["role"] == "LOCAL GUIDANCE"
    assert r["citation_check"] == "pass"
    assert "#page=6" in r["sources"]
    assert "25 mg" in r["answer"]


def test_historical_germany_labels_v38_as_historical():
    r = rt.answer("German AX-17 guidance before latest revision?", mode="historical", country="Germany")
    assert r["outcome"] == "answered"
    v38 = [c for c in r["cards"] if c["chunk"]["document_id"] == "DE-AX17-LBL-038"]
    assert v38 and all(c["role"].startswith("HISTORICAL") for c in v38)
    assert "50 mg" in r["answer"]


def test_exact_id_restricts_to_that_document():
    r = rt.answer("What does SB-AX17-2026-09 require?", mode="current", country="Germany")
    assert r["filters"]["document_ids"] == ["SB-AX17-2026-09"]
    assert _docs(r["candidates"]) == {"SB-AX17-2026-09"}
    assert "Day 14" in r["answer"] and r["citation_check"] == "pass"


def test_unknown_country_is_not_found_without_search():
    r = rt.answer("Approved AX-17 dosage in Japan?", mode="current", country="Japan")
    assert r["outcome"] == "not_found"
    assert r["candidates"] == [] and "Japan" in r["answer"]


def test_missing_key_term_is_a_signal_and_gemini_abstains():
    """D66: the key-term check only logs a signal; Gemini's verdict (then Check Grounding) decides."""
    r = rt.answer("Does AX-17 interact with warfarin?", mode="current", country="Germany")
    assert r["outcome"] == "insufficient"
    assert any("warfarin" in reason and reason.startswith("signal") for reason in r["reasons"])
    assert "generate" in r["latency_ms"]


def test_unknown_document_id_is_not_found():
    r = rt.answer("What does HN-SAF-017 say?", mode="current", country="Germany")
    assert r["outcome"] == "not_found" and "HN-SAF-017" in r["answer"]


def test_citation_check_blocks_invented_evidence_ids():
    cards = [{"id": "E1"}, {"id": "E2"}]
    ok, why = rt.check_citations({"verdict": "answered", "answer": "25 mg [E1] and 75 mg [E9]", "citations": ["E1"]}, cards)
    assert not ok and "E9" in why
    ok, _ = rt.check_citations({"verdict": "answered", "answer": "no citation at all", "citations": []}, cards)
    assert not ok


def test_offline_mode_never_creates_a_cloud_client():
    import pytest
    with pytest.raises(RuntimeError, match="Offline mode"):
        rt._bq()


def test_table_values_stay_in_their_column():
    """Regression (Step 4, D30 reversed): Table 3's Severe row has starting dose
    "Specialist review" and maximum "25 mg/day". With thinking off, the answer
    writer twice reported 25 mg/day as the severe STARTING dose, and every check
    passed (the citation was valid and the number exists in the cited card)."""
    r = rt.answer("What is the current renal starting dose of AX-17?", mode="current", country="Germany")
    assert r["outcome"] == "answered" and r["citation_check"] == "pass"
    severe = [line for line in r["answer"].replace(". ", ".\n").splitlines() if "evere" in line]
    assert severe and "specialist review" in " ".join(severe).lower()
    assert not any("starting dose" in line.lower() and "25 mg/day" in line for line in severe)


# -----------------------------------------------------------------------------
# Step 5b: historical, lookups, verbatim tables, fixed notes
# -----------------------------------------------------------------------------

def test_date_before_any_document_says_so_with_earliest_date():
    """D39: no search, no Gemini; the message is built by code from the registry."""
    r = rt.answer("What was the AX-17 renal dose in Germany?", mode="historical", country="Germany", as_of="2018-12-31")
    assert r["outcome"] == "not_found" and r["candidates"] == []
    assert "2018-12-31" in r["answer"] and "2019-01-01" in r["answer"]


def test_historical_date_excludes_later_versions():
    r = rt.answer("What was the renal starting dose for moderate impairment in Germany?", mode="historical",
                  country="Germany", as_of="2025-06-30")
    assert "DE-AX17-LBL-042" not in _docs(r["candidates"])  # v4.2 took effect 2026-09-15
    assert "SB-AX17-2026-09" not in _docs(r["candidates"])  # the bulletin, 2026-10-07
    assert "50 mg" in r["answer"]


def test_current_label_answer_notes_the_earlier_version():
    """D43: a fixed line built by code, not by the model."""
    r = rt.answer("What is the current renal starting dose of AX-17?", mode="current", country="Germany")
    assert any("DE-AX17-LBL-038" in note and "2026-09-15" in note for note in r["notes"])


def test_table_by_number_is_shown_verbatim():
    r = rt.lookup("HN-204", table="Table 14")
    assert r["outcome"] == "answered" and r["citation_check"].startswith("verbatim")
    assert "| Nausea | 12.7 | 6.0 | No |" in r["answer"]
    assert "#page=11" in r["answer"]


def test_table_by_description_matches_the_real_catalogue():
    r = rt.lookup("hn-204", table="the renal table")  # ID in any case
    assert r["outcome"] == "answered" and r["table"] == "Table 18"


def test_missing_table_lists_the_real_tables():
    r = rt.lookup("HN-204", table="Table 5")
    assert r["outcome"] == "not_found"
    assert "Table 14" in r["answer"] and "Table 18" in r["answer"]


def test_vague_table_request_asks_back():
    r = rt.lookup("HN-204", table="the table")
    assert r["outcome"] == "clarify" and "Table 14" in r["answer"] and "Table 18" in r["answer"]


def test_row_filter_keeps_only_the_named_rows():
    r = rt.lookup("HN-311", table="Table 14", rows="Nausea")
    assert "| Nausea |" in r["answer"] and "| Rash |" not in r["answer"]
    assert r["rows_shown"] == 1


def test_superseded_table_is_marked_historical():
    r = rt.lookup("DE-AX17-LBL-038", table="renal dosing")
    assert "HISTORICAL, NOT CURRENT GUIDANCE" in r["answer"]


def test_table_flagged_by_the_faithfulness_check_says_verify():
    r = rt.lookup("US-AX17-PI-050", table="renal")
    assert "VERIFY" in r["answer"]


def test_long_table_is_capped_with_count_and_filter_offer():
    t = {"table_id": "Table 99", "table_title": "Table 99. Long", "page_start": 2, "page_end": 2, "needs_review": False,
         "header": ["Event", "%"], "header_line": "| Event | % |",
         "body_lines": [f"| Event {i} | {i} |" for i in range(40)]}
    doc = rt.registry()["HN-204"]
    text, shown, total = rt.format_table(t, doc)
    assert (shown, total) == (rt.MAX_TABLE_ROWS, 40)
    assert f"Showing {rt.MAX_TABLE_ROWS} of 40 rows" in text


def test_question_about_superseded_document_uses_historical_mode():
    """D36: the document's status decides the mode, not the agent."""
    r = rt.lookup("DE-AX17-LBL-038", question="What did this label say about moderate renal impairment?")
    assert r["mode"] == "historical"
    docs = [c for c in r["cards"] if c["role"] != "REGISTRY FACTS"]  # the register card states facts, not guidance
    assert docs and all(c["role"].startswith("HISTORICAL") for c in docs)


def test_unknown_document_lookup_is_not_found():
    r = rt.lookup("HN-999")
    assert r["outcome"] == "not_found" and "HN-999" in r["answer"]


# The agent tools (harness/tools.py): only tool_context.state is used, so a plain object stands in.

def _tool_context():
    from types import SimpleNamespace
    return SimpleNamespace(state={})


def test_tool_rejects_unreadable_or_future_dates_without_search():
    """D38: the agent turns words into a date; code checks it."""
    import tools
    ctx = _tool_context()
    assert tools.search_historical("q", "Germany", "June 2025", "", ctx)["outcome"] == "clarify"
    assert tools.search_historical("q", "Germany", "2099-01-01", "", ctx)["outcome"] == "clarify"


def test_tool_adds_jurisdiction_note_when_country_changes():
    """D40: a fixed note, built by code, when the country differs from the previous question."""
    import tools
    ctx = _tool_context()
    tools.search_current("Current AX-17 renal guidance in Germany?", "Germany", "", ctx)
    assert not ctx.state[tools.RELAY_KEY][-1].startswith("Note:")
    tools.start_turn_state(ctx.state)  # the next user turn
    tools.search_current("Approved AX-17 dosage in Japan?", "Japan", "", ctx)
    assert ctx.state[tools.RELAY_KEY][-1].startswith("Note: this answer is for Japan. Your previous question was about Germany.")


# -----------------------------------------------------------------------------
# D46 catalogue and D47 no hard-coding: everything about the collection comes from data
# -----------------------------------------------------------------------------

def test_catalogue_lists_every_registry_document_and_its_real_tables():
    text = rt.catalogue()
    assert all(doc_id in text for doc_id in rt.registry())
    assert "Table 3. Renal dose modification" in text and "Table 18. Renal subgroup summary" in text


def test_document_id_shapes_are_learned_from_the_registry():
    assert rt.ids_in_question("What does HN-SAF-017 say?") == ([], ["HN-SAF-017"])   # two dashes: ID-shaped
    assert rt.ids_in_question("Show HN-999") == ([], ["HN-999"])                       # same shape as HN-204
    assert rt.ids_in_question("Is DE-AX17-LBL-042 current?") == (["DE-AX17-LBL-042"], [])
    for text in ("What is AX-17?", "COVID-19 patients", "us-based documents"):          # not document IDs
        assert rt.ids_in_question(text) == ([], [])


def test_filler_words_are_not_key_terms():
    assert rt.key_terms("tell me something present in Ax-17") == []


def test_product_names_come_from_the_registry():
    assert rt.resolve_product("ax17") == "AX-17" and rt.resolve_product(None) == "AX-17"
    r = rt.answer("dose", country="Germany", product="Aspirin")
    assert r["outcome"] == "not_found" and "Products covered: AX-17" in r["answer"]


def test_several_products_and_none_named_asks_which(monkeypatch):
    monkeypatch.setattr(rt, "products", lambda: ["AX-17", "BX-9"])
    r = rt.answer("current dose", country="Germany")
    assert r["outcome"] == "clarify" and "AX-17, BX-9" in r["answer"]


# -----------------------------------------------------------------------------
# Step 6: number check (D50), study comparison (D48), governed text-to-SQL (D49)
# -----------------------------------------------------------------------------

def _card(i, text):
    return {"id": f"E{i}", "text": text}


def test_number_check_blocks_invented_or_calculated_numbers():
    cards = [_card(1, "| Moderate | 30-59 | 25 mg OD | 50 mg/day |")]
    assert rt.check_numbers("Start at 25 mg OD, maximum 50 mg/day [E1].", cards, ["E1"], "q")[0]
    ok, why = rt.check_numbers("Start at 12.5 mg [E1].", cards, ["E1"], "q")
    assert not ok and "12.5" in why
    # a number the user wrote may be repeated (e.g. to say it is not in the documents)
    assert rt.check_numbers("12.5 mg is not in the label; it says 25 mg [E1].", cards, ["E1"], "Is it 12.5 mg?")[0]
    # digits inside document IDs and product names are not values
    assert rt.check_numbers("DE-AX17-LBL-042 for AX-17 says 25 mg [E1].", cards, ["E1"], "q")[0]


def test_compare_demo4_uses_each_study_table_and_code_computed_differences():
    r = rt.compare(["HN-204", "HN-311"], question="Compare AE evidence in HN-204 and HN-311.")
    assert r["outcome"] == "answered" and r["citation_check"] == "pass" and r["number_check"].startswith("pass")
    docs = {c["chunk"]["document_id"] for c in r["cards"]}
    assert {"HN-204", "HN-311"} <= docs and "HN-402" not in docs  # the lookalike table never enters
    assert "#page=11" in r["sources"] and "computed by code" in r["sources"]
    assert "12.7" in r["answer"] and "11.8" in r["answer"]
    assert rt.COMPARISON_CAVEAT in r["notes"]
    assert not any(n.startswith("VERIFY") for n in r["notes"])  # registry CSV and PDF tables agree


def test_compare_one_event_only():
    r = rt.compare(["hn-204", "HN-402"], event="nausea")
    rows = [c for c in r["cards"] if c["role"] == "STRUCTURED DATA"][0]["text"]
    assert "nausea" in rows and "rash" not in rows


def test_compare_rejects_unknown_ids_and_non_studies_without_search():
    assert rt.compare(["HN-204", "HN-999"])["outcome"] == "not_found"
    r = rt.compare(["HN-204", "DE-AX17-LBL-042"])
    assert r["outcome"] == "clarify" and "HN-311" in r["answer"]  # lists the real studies


def test_cross_check_flags_a_registry_value_missing_from_the_report():
    tbl = {"body_lines": ["| Nausea | 12.7 | 6.0 | No |"]}
    assert rt.cross_check([{"study_id": "X", "event": "nausea", "treatment_rate_pct": 12.7, "control_rate_pct": 6.0}], tbl) == []
    assert rt.cross_check([{"study_id": "X", "event": "nausea", "treatment_rate_pct": 13.2, "control_rate_pct": 6.0}], tbl)


def test_sql_checks_block_writes_other_tables_and_base_tables():
    import text2sql
    view = text2sql.view_ids()["v_adverse_events"]
    assert text2sql.check_sql(f"SELECT study_id FROM `{view}` LIMIT 5")[0]
    blocked = [
        f"DROP TABLE `{view}`",
        f"SELECT 1 FROM `{view}`; DELETE FROM `{view}` WHERE TRUE",
        "SELECT chunk_id FROM `tredence-fde-1.medevidence_v1_vks.chunks`",
        "SELECT SUM(treatment_rate_pct) FROM medevidence_v1_vks.adverse_events",  # base table, no backticks
        "SELECT * FROM `region-us`.INFORMATION_SCHEMA.JOBS",
    ]
    for sql in blocked:
        assert not text2sql.check_sql(sql)[0], sql


def test_dry_run_blocks_tables_outside_the_views_even_if_text_checks_missed_it():
    """Second layer: BigQuery reports the base tables a query really reads (recorded dry run)."""
    import text2sql
    ok, why, _ = text2sql.dry_run(BYPASS_SQL)
    assert not ok and "chunks" in why


BYPASS_SQL = "SELECT chunk_id FROM `tredence-fde-1.medevidence_v1_vks.chunks` LIMIT 1"


def test_text_to_sql_answers_with_rows_and_the_sql():
    import text2sql
    r = text2sql.ask("Which study had the highest rash rate?")
    rows = [line for line in r["answer"].splitlines() if line.startswith("|")]
    # The model may select extra columns (e.g. event); the checked fact is HN-402 with 19.7 in one row.
    assert r["outcome"] == "answered" and any("HN-402" in row and "19.7" in row for row in rows)
    assert "SQL:" in r["answer"] and "v_adverse_events" in r["sql"]


def test_text_to_sql_says_so_when_the_data_cannot_answer():
    import text2sql
    assert text2sql.ask("What is the average age of patients in HN-204?")["outcome"] == "insufficient"


def test_step6_tools_relay_through_the_agent_path():
    """Regression (Step 6 smoke test): the tool wrapper crashed on cards without a page.
    Call the tools exactly as the agent does, not only the runtime functions."""
    import tools
    ctx = _tool_context()
    out = tools.compare_studies(["HN-204", "HN-311"], "", "Compare AE evidence in HN-204 and HN-311.", ctx)
    assert out["outcome"] == "answered" and any(e["page"] is None for e in out["evidence"])
    tools.text_to_sql("Which study had the highest rash rate?", ctx)
    assert len(ctx.state[tools.RELAY_KEY]) == 2  # D51: both answers kept for the user
    assert rt.COMPARISON_CAVEAT in ctx.state[tools.RELAY_KEY][0]


# -----------------------------------------------------------------------------
# Step 7: premise check (D55), code-built verdict texts (D54), comparison Sources (D57), escalation (D52)
# -----------------------------------------------------------------------------

def test_premise_value_is_blocked_unless_the_answer_rejects_it():
    cards = [_card(1, "Table 3 · | Severe | 15-29 | Specialist review | 25 mg/day |")]
    q = "Moderate is 25 mg, so severe must be 12.5 mg?"
    assert not rt.check_numbers("Yes, for severe impairment use 12.5 mg [E1].", cards, ["E1"], q)[0]
    assert rt.check_numbers("No. There is no 12.5 mg in Table 3; severe says specialist review, maximum 25 mg/day [E1].",
                            cards, ["E1"], q)[0]


def test_partial_answers_name_what_is_missing_in_a_fixed_line():
    assert rt.partial_note({"verdict": "partial", "missing": "pregnancy data"})[0].startswith(
        "Not covered by the controlled documents: pregnancy data")
    assert rt.partial_note({"verdict": "partial", "missing": "the 12.5 mg dose"}) == []  # clinical figure: dropped
    assert rt.partial_note({"verdict": "answered", "missing": "x"}) == []


def test_insufficient_answers_offer_the_hand_off():
    r = rt.answer("Does AX-17 interact with warfarin?", mode="current", country="Germany")
    assert r["outcome"] == "insufficient" and 'Say "route it"' in r["answer"]


def test_comparison_sources_always_list_each_study_page():
    r = rt.compare(["hn-204", "HN-402"], event="nausea")
    assert r["sources"].count("#page=11") == 2  # HN-204 and HN-402 table pages, even if Gemini cited only the rows


def test_premise_question_is_corrected_not_confirmed():
    r = rt.answer(PREMISE_Q, mode="current", country="Germany")
    assert r["outcome"] in ("answered", "partial") and r["number_check"].startswith("pass")
    assert "12.5" not in r["answer"] or rt.NEGATIONS.search(r["answer"])


PREMISE_Q = "The current moderate starting dose in Germany is 25 mg, so severe must be 12.5 mg, right?"


def test_escalation_strips_patient_values_before_the_general_search(monkeypatch):
    """Code de-identifies the general question: no digit-bearing token reaches the search."""
    import escalation
    seen = {}
    monkeypatch.setattr(escalation.rt, "answer", lambda q, **kw: seen.setdefault("q", q) and {"outcome": "insufficient"})
    escalation.escalate("patient_specific", "My patient...", "renal dosing for eGFR 35 and ALT 4x ULN at 70 years",
                        "Germany")
    assert seen["q"].startswith("renal dosing for eGFR and ALT ULN at years")
    assert "hepatic monitoring and its escalation thresholds for alt" in seen["q"]  # D65: lab NAME kept, value dropped


def test_escalation_records_and_shows_general_reference_only():
    import escalation
    r = escalation.escalate("patient_specific", "My 70-year-old patient has eGFR 35. What dose should I give him?",
                            GENERAL_Q, "Germany")
    assert r["outcome"] == "escalated" and r["escalation_id"].startswith("ESC-")
    assert "General reference from the controlled documents" in r["answer"] and "70-year-old" not in r["answer"]
    assert escalation.escalate("user_request", "Does AX-17 interact with warfarin?")["outcome"] == "escalated"


GENERAL_Q = "renal dosing guidance for moderate impairment and hepatic monitoring"


def test_jurisdiction_note_only_compares_with_the_turn_directly_before():
    """Regression (Step 8, user report): Germany search → a question with no country → a US question
    must NOT say "your previous question was about Germany"."""
    import tools
    ctx = _tool_context()
    tools.search_current("Current AX-17 renal guidance in Germany?", "Germany", "", ctx)
    tools.start_turn_state(ctx.state)  # a turn answered without a country-specific tool (e.g. the catalogue)
    tools.start_turn_state(ctx.state)  # then the Japan question
    tools.search_current("Approved AX-17 dosage in Japan?", "Japan", "", ctx)
    assert not ctx.state[tools.RELAY_KEY][-1].startswith("Note:")


def test_superseded_by_is_derived_from_the_next_version():
    """D62 (evaluation case A3): "which document superseded v3.8?" is answerable from data."""
    assert rt.registry()["DE-AX17-LBL-038"]["superseded_by"] == "DE-AX17-LBL-042"
    assert rt.registry()["DE-AX17-LBL-042"]["superseded_by"] is None
    assert "superseded by DE-AX17-LBL-042" in rt.lookup("DE-AX17-LBL-038")["answer"]
    assert "superseded by DE-AX17-LBL-042" in rt.catalogue()


def test_a_named_document_brings_its_register_facts_as_a_card():
    """Eval A3: "which document superseded v3.8?" needs the register, not v3.8's text."""
    card = rt.registry_card("DE-AX17-LBL-038", 9)
    assert card["id"] == "E9" and "superseded by DE-AX17-LBL-042" in card["text"] and card["source"]


def test_a_tool_failure_is_logged_not_silent(monkeypatch):
    """Regression (user test): a failed search showed a polite message but left no row in agent_log."""
    import json
    import tools
    def boom(*a, **k):
        raise ConnectionResetError("Connection reset by peer")
    monkeypatch.setattr(tools.rt, "answer", boom)
    out = tools.search_current("Current AX-17 renal guidance in Germany?", "Germany", "", _tool_context())
    assert out["outcome"] == "error"
    last = json.loads((rt.OUTPUT_DIR / "agent_log_offline.jsonl").read_text().strip().splitlines()[-1])
    assert last["outcome"] == "error" and last["caller"] == "agent:search_current"


def test_transient_connection_errors_are_retried():
    calls = []
    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionResetError("Connection reset by peer")
        return "ok"
    import time as _t
    sleep, _t.sleep = _t.sleep, lambda s: None
    try:
        assert rt.with_retry(flaky, "test") == "ok" and len(calls) == 2
    finally:
        _t.sleep = sleep


def test_premise_line_names_whatever_value_the_user_stated():
    """D64: dynamic: the user's own dose or rate is checked against the evidence; nothing is hard-coded."""
    cards = [_card(1, "Table 3 · | Moderate | 30-59 | 25 mg OD | 50 mg/day |")]
    answer = "Severe: specialist review [E1]."
    assert rt.premise_notes("so severe must be 12.5 mg, right?", cards, answer) == [
        "The value 12.5 mg in your question does not appear in the controlled documents."]
    assert rt.premise_notes("Was nausea 45% in HN-204?", cards, answer)[0].startswith("The value 45%")
    assert rt.premise_notes("Is the moderate dose 25 mg?", cards, answer) == []          # supported: no line
    assert rt.premise_notes("so 12.5 mg?", cards, "There is no 12.5 mg dose [E1].") == []  # already addressed
    assert rt.premise_notes("ALT is 4x ULN, what now?", cards, answer) == []             # a lab value, not a claim


# -----------------------------------------------------------------------------
# D66: Vertex AI Check Grounding on every generated answer
# -----------------------------------------------------------------------------

def test_an_ungrounded_answer_is_blocked(monkeypatch):
    monkeypatch.setattr(rt, "grounding", lambda text, cards: {"score": 0.12, "claims": [
        {"text": "AX-17 has no interaction with warfarin.", "supported": False}]})
    r = rt.answer("Current AX-17 renal guidance in Germany?", mode="current", country="Germany")
    assert r["outcome"] == "blocked" and r["grounding_check"].startswith("BLOCKED: support 0.12")
    assert "warfarin" in r["grounding_check"]  # the unsupported claim is logged


def test_wrong_column_answer_fails_grounding():
    """Regression for the Step 4 bug the number check cannot catch: "50 mg" exists in Table 3 (as the
    MAXIMUM), so numbers pass, but "starting dose 50 mg" is not supported (recorded Check Grounding call)."""
    cards = rt.answer("Current AX-17 renal guidance in Germany?", mode="current", country="Germany")["cards"]
    assert rt.check_numbers(WRONG_COLUMN, cards, [c["id"] for c in cards], "q")[0]   # numbers: pass
    assert rt.grounding(WRONG_COLUMN, cards)["score"] < rt.GROUNDING_THRESHOLD      # grounding: blocked


WRONG_COLUMN = "For moderate renal impairment the starting dose is 50 mg once daily [E2]."


def test_computed_card_has_ax17_minus_control_per_study():
    """User test: "the difference between AX-17 and control" must be computable from the card (code)."""
    rows = [{"study_id": "HN-204", "event": "nausea", "treatment_rate_pct": 12.7, "control_rate_pct": 6.0},
            {"study_id": "HN-402", "event": "nausea", "treatment_rate_pct": 14.1, "control_rate_pct": 6.0}]
    lines = rt.differences(rows, ["HN-204", "HN-402"])
    assert "HN-204 nausea: treatment % minus control % = +6.7 points" in lines
    assert "HN-402 nausea: treatment % minus control % = +8.1 points" in lines
