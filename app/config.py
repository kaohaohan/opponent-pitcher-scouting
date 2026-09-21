"""Application settings.

Kept deliberately small: environment variables with sane defaults, no settings
framework. Everything that a deployment might want to change lives here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

DEFAULT_FIXTURE = PACKAGE_DIR / "fixtures" / "hao_yu_lee_2025-08-14.json"


@dataclass(frozen=True)
class Settings:
    database_url: str
    replay_fixture_path: Path
    frontend_dir: Path
    #: Gemini credential, from the environment only — no default. `None` when
    #: unset; `GeminiProvider` fails clearly at call time rather than here, so
    #: importing settings never requires a key Phase 1 doesn't need.
    gemini_api_key: str | None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'watch.db'}"
            ),
            replay_fixture_path=Path(
                os.environ.get("REPLAY_FIXTURE_PATH", DEFAULT_FIXTURE)
            ),
            frontend_dir=Path(
                os.environ.get("FRONTEND_DIR", PROJECT_ROOT / "frontend")
            ),
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        )


settings = Settings.from_env()
