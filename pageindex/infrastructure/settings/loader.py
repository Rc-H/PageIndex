from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .app_setting import Settings
from .llm_setting import load_llm_settings
from .service_setting import load_service_settings


_ENV_LOADED = False


def _load_project_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    # Load the repo-root .env once, while letting explicit shell exports win.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    _ENV_LOADED = True


def load_settings() -> Settings:
    _load_project_dotenv()
    return Settings(
        llm=load_llm_settings(),
        service=load_service_settings(),
    )
