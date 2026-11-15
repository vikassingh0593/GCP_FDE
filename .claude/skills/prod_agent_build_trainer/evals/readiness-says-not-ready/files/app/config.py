"""Environment-backed configuration for Topic 19.

Configuration is intentionally supplied through `lab.env`:
    source lab.env

No dotenv loader is used; this keeps the lab consistent with the
training convention used by the other hands-ons.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    """Runtime settings already exported by lab.env."""

    app_name: str = os.getenv(
        "APP_NAME", "customer_success_lab"
    )
    model_id: str = os.getenv("MODEL_ID", "gemini-2.5-flash")
    host: str = os.getenv("LAB_HOST", "127.0.0.1")
    port: int = int(os.getenv("LAB_PORT", "8080"))

    session_backend: str = os.getenv("SESSION_BACKEND", "local_sqlite")
    session_db_file: str = os.getenv(
        "SESSION_DB_FILE", "data/adk_sessions.db"
    )

    agent_platform_project: str = os.getenv(
        "AGENT_PLATFORM_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "")
    )
    agent_platform_location: str = os.getenv(
        "AGENT_PLATFORM_LOCATION", "us-central1"
    )
    agent_engine_id: str = os.getenv("AGENT_ENGINE_ID", "")
    agent_engine_resource_name: str = os.getenv(
        "AGENT_ENGINE_RESOURCE_NAME", ""
    )

    memory_backend: str = os.getenv("MEMORY_BACKEND", "in_memory")
    memory_bank_project: str = os.getenv(
        "MEMORY_BANK_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "")
    )
    memory_bank_location: str = os.getenv(
        "MEMORY_BANK_LOCATION", "us-central1"
    )
    memory_bank_agent_engine_id: str = os.getenv(
        "MEMORY_BANK_AGENT_ENGINE_ID", ""
    )

    identity_salt: str = os.getenv(
        "IDENTITY_SALT", "lab-training-salt"
    )

    @property
    def session_db_path(self) -> Path:
        """Resolve the SQLite file independently of the shell working dir."""
        path = Path(self.session_db_file).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @property
    def session_db_url(self) -> str:
        """Build the SQLAlchemy async URL from the absolute database path."""
        return f"sqlite+aiosqlite:///{self.session_db_path}"


settings = Settings()
