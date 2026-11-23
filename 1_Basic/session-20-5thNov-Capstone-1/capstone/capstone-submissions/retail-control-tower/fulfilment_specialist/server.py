"""Start the Fulfilment Specialist as its own service (terminal 1).

Run from retail-control-tower/:
    source .venv/bin/activate && source lab.env
    python -m fulfilment_specialist.server

Then check the Agent Card (terminal 2):
    curl -s "$FULFILMENT_AGENT_CARD_URL" | python -m json.tool

Stop it with Ctrl+C to show the orchestrator's partial answer (remote failure).
"""

from __future__ import annotations

import uvicorn

from common import config
from common.harness.logs import configure_stdlib_logging


def main() -> None:
    configure_stdlib_logging()
    from fulfilment_specialist.fulfilment_agent.agent import build_a2a_app

    print(f"Fulfilment Specialist on http://{config.FULFILMENT_AGENT_HOST}:{config.FULFILMENT_AGENT_PORT} "
          f"| card {config.FULFILMENT_AGENT_CARD_URL} | model {config.SPECIALIST_MODEL}")
    uvicorn.run(build_a2a_app(), host=config.FULFILMENT_AGENT_HOST, port=config.FULFILMENT_AGENT_PORT,
                log_level="warning")


if __name__ == "__main__":
    main()
