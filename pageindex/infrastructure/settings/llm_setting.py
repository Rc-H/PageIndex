from __future__ import annotations

import os
import json
from dataclasses import dataclass


def _env_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_json_object_or_empty(name: str) -> dict[str, object]:
    raw = _env_or_none(name)
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "openai"
    model: str = ""
    llm_base_url: str | None = None
    # OpenAI
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    # Azure OpenAI
    azure_openai_api_key: str | None = None
    azure_openai_base_url: str | None = None
    # OpenAI-compatible (Ollama / vLLM / etc.)
    openai_compatible_api_key: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_request_kwargs: dict[str, object] | None = None


def load_llm_settings() -> LLMSettings:
    llm_base_url = _env_or_none("LLM_BASE_URL")
    return LLMSettings(
        provider=os.getenv("LLM_PROVIDER", "openai"),
        model=_env_or_none("LLM_MODEL") or "",
        llm_base_url=llm_base_url,
        openai_api_key=_env_or_none("CHATGPT_API_KEY") or _env_or_none("OPENAI_API_KEY"),
        openai_base_url=_env_or_none("OPENAI_BASE_URL") or llm_base_url,
        anthropic_api_key=_env_or_none("ANTHROPIC_API_KEY"),
        anthropic_base_url=_env_or_none("ANTHROPIC_BASE_URL") or llm_base_url,
        azure_openai_api_key=_env_or_none("AZURE_OPENAI_API_KEY"),
        azure_openai_base_url=_env_or_none("AZURE_OPENAI_BASE_URL") or _env_or_none("AZURE_OPENAI_ENDPOINT") or llm_base_url,
        openai_compatible_api_key=_env_or_none("OPENAI_COMPATIBLE_API_KEY") or _env_or_none("OPENAI_API_KEY"),
        openai_compatible_base_url=_env_or_none("OPENAI_COMPATIBLE_BASE_URL") or _env_or_none("OPENAI_BASE_URL") or llm_base_url,
        openai_compatible_request_kwargs=_env_json_object_or_empty("OPENAI_COMPATIBLE_REQUEST_KWARGS"),
    )
