from __future__ import annotations

from dataclasses import dataclass

from .llm_setting import LLMSettings
from .service_setting import ServiceSettings


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings
    service: ServiceSettings
