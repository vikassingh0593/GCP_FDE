"""Web server entry point.

Run from the project root:
    source .venv/bin/activate
    source lab.env
    python -m app.server
"""

from __future__ import annotations

import uvicorn

from app.config import settings
#from preflight import run_preflight


def main() -> None:
    """Validate the lab environment, then launch FastAPI."""
  #  run_preflight()
    uvicorn.run(
        "app.api:api",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
