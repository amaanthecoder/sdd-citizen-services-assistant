"""Config and env loading."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal dotenv loader — avoids the python-dotenv hard dep for grading."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    agent_model: str
    planner_model: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            agent_model=os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001"),
            planner_model=os.environ.get("PLANNER_MODEL", "claude-haiku-4-5-20251001"),
        )


CONFIG = Config.from_env()
