"""Run the complete Level-5 hybrid semantic orchestrator.

Run:
    python src/01_run_semantic_orchestrator.py
"""
from google import genai
from app.orchestrator.engine import SemanticOrchestrator
from app.orchestrator.synthesis import synthesize

OBJECTIVE = "Determine the most likely cause of TKT-7421 and identify the safest next engineering action."

def main() -> None:
    client = genai.Client()
    orchestrator = SemanticOrchestrator(client)
    state, report = orchestrator.run(OBJECTIVE, "TKT-7421")
    print("\n=== ORCHESTRATION TRAJECTORY ===")
    for i, decision in enumerate(state.decisions, 1):
        print(f"{i}. {decision.action} | confidence={decision.confidence:.2f} | {decision.reason}")
    print("\n=== ENGINEERING REPORT ===")
    print(report.model_dump_json(indent=2))
    print("\n=== GROUNDED INVESTIGATION RESULT ===")
    print(synthesize(state, client))

if __name__ == "__main__":
    main()
