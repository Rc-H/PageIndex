from __future__ import annotations

from .app_setting import Settings
from .llm_setting import load_llm_settings
from .service_setting import load_service_settings


def load_settings() -> Settings:
    return Settings(
        llm=load_llm_settings(),
        service=load_service_settings(),
    )
