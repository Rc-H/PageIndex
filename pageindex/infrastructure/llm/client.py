from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import openai


class LLMClient(ABC):
    @abstractmethod
    def generate_text(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_text_with_finish_reason(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> tuple[str, str]:
        raise NotImplementedError

    @abstractmethod
    async def generate_text_async(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
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

    def _build_request_kwargs(self, json_response: bool = False) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"temperature": 0}
        if json_response:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def generate_text(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> str:
        response = self._sync_client().chat.completions.create(
            model=model,
            messages=self._build_messages(prompt, chat_history),
            **self._build_request_kwargs(json_response=json_response),
        )
        return response.choices[0].message.content or ""

    def generate_text_with_finish_reason(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> tuple[str, str]:
        response = self._sync_client().chat.completions.create(
            model=model,
            messages=self._build_messages(prompt, chat_history),
            **self._build_request_kwargs(json_response=json_response),
        )
        finish_reason = response.choices[0].finish_reason or "stop"
        mapped_reason = "max_output_reached" if finish_reason == "length" else "finished"
        return response.choices[0].message.content or "", mapped_reason

    async def generate_text_async(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> str:
        async with self._async_client() as client:
            response = await client.chat.completions.create(
                model=model,
                messages=self._build_messages(prompt, chat_history),
                **self._build_request_kwargs(json_response=json_response),
            )
        return response.choices[0].message.content or ""
