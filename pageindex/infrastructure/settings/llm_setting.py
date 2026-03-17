from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "openai"
    model: str = "gpt-4o-2024-11-20"
    # OpenAI
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    # Azure OpenAI
    azure_openai_api_key: str | None = None
    azure_openai_base_url: str | None = None
    # OpenAI-compatible (Ollama / vLLM / etc.)
    openai_compatible_api_key: str | None = None
    openai_compatible_base_url: str | None = None


def load_llm_settings() -> LLMSettings:
    return LLMSettings(
        provider=os.getenv("LLM_PROVIDER", "openai"),
        model=os.getenv("LLM_MODEL", "gpt-4o-2024-11-20"),
        openai_api_key=os.getenv("CHATGPT_API_KEY") or os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_openai_base_url=os.getenv("AZURE_OPENAI_BASE_URL") or os.getenv("AZURE_OPENAI_ENDPOINT"),
        openai_compatible_api_key=os.getenv("OPENAI_COMPATIBLE_API_KEY") or os.getenv("OPENAI_API_KEY"),
        openai_compatible_base_url=os.getenv("OPENAI_COMPATIBLE_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
    )
