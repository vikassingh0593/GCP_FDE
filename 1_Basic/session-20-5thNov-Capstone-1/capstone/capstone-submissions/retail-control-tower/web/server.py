"""Web app + orchestrator entry point (terminal 2).

Run from retail-control-tower/ (start the Fulfilment Specialist first):
    source .venv/bin/activate && source lab.env
    python -m web.server

Open http://127.0.0.1:8080
"""

from __future__ import annotations

import uvicorn

from common import config
from common.harness.logs import configure_stdlib_logging


def main() -> None:
    configure_stdlib_logging()
    print(f"Control tower on http://{config.WEB_HOST}:{config.WEB_PORT} | orchestrator {config.ORCHESTRATOR_MODEL} "
          f"| sessions {config.SESSION_BACKEND} | specialist {config.FULFILMENT_AGENT_CARD_URL}")
    uvicorn.run("web.api:api", host=config.WEB_HOST, port=config.WEB_PORT, reload=False, log_level="warning")


if __name__ == "__main__":
    main()
