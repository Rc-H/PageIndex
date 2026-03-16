from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import openai


class LLMClient(ABC):
    @abstractmethod
    def generate_text(self, model: str, prompt: str, chat_history: list[dict[str, Any]] | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_text_with_finish_reason(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        raise NotImplementedError

    @abstractmethod
    async def generate_text_async(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> str:
        raise NotImplementedError


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(self, api_key: str | None, base_url: str | None = None):
        if not api_key:
            raise ValueError("Missing API key for OpenAI-compatible provider")
        self._api_key = api_key
        self._base_url = base_url

    def _build_messages(self, prompt: str, chat_history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        messages = list(chat_history or [])
        messages.append({"role": "user", "content": prompt})
        return messages

    def _sync_client(self) -> openai.OpenAI:
        return openai.OpenAI(api_key=self._api_key, base_url=self._base_url)

    def _async_client(self) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    def generate_text(self, model: str, prompt: str, chat_history: list[dict[str, Any]] | None = None) -> str:
        response = self._sync_client().chat.completions.create(
            model=model,
            messages=self._build_messages(prompt, chat_history),
            temperature=0,
        )
        return response.choices[0].message.content or ""

    def generate_text_with_finish_reason(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        response = self._sync_client().chat.completions.create(
            model=model,
            messages=self._build_messages(prompt, chat_history),
            temperature=0,
        )
        finish_reason = response.choices[0].finish_reason or "stop"
        mapped_reason = "max_output_reached" if finish_reason == "length" else "finished"
        return response.choices[0].message.content or "", mapped_reason

    async def generate_text_async(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> str:
        async with self._async_client() as client:
            response = await client.chat.completions.create(
                model=model,
                messages=self._build_messages(prompt, chat_history),
                temperature=0,
            )
        return response.choices[0].message.content or ""
