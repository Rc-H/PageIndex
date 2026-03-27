from __future__ import annotations

from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Any

import openai

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    anthropic = SimpleNamespace(Anthropic=None, AsyncAnthropic=None)


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
    _OPENAI_CHAT_CREATE_TOP_LEVEL_KEYS = {
        "audio",
        "frequency_penalty",
        "function_call",
        "functions",
        "logit_bias",
        "logprobs",
        "max_completion_tokens",
        "max_tokens",
        "metadata",
        "modalities",
        "n",
        "parallel_tool_calls",
        "prediction",
        "presence_penalty",
        "reasoning_effort",
        "response_format",
        "seed",
        "service_tier",
        "stop",
        "store",
        "stream",
        "stream_options",
        "temperature",
        "tool_choice",
        "tools",
        "top_logprobs",
        "top_p",
        "user",
        "web_search_options",
    }

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        request_kwargs: dict[str, Any] | None = None,
    ):
        if not api_key:
            raise ValueError("Missing API key for OpenAI-compatible provider")
        self._api_key = api_key
        self._base_url = base_url
        self._request_kwargs = dict(request_kwargs or {})

    def _build_messages(self, prompt: str, chat_history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        messages = list(chat_history or [])
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_messages_with_content(
        self,
        content: str | list[dict[str, Any]],
        chat_history: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        messages = list(chat_history or [])
        messages.append({"role": "user", "content": content})
        return messages

    def _sync_client(self) -> openai.OpenAI:
        return openai.OpenAI(api_key=self._api_key, base_url=self._base_url)

    def _async_client(self) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    def _build_request_kwargs(self, json_response: bool = False) -> dict[str, Any]:
        top_level_kwargs: dict[str, Any] = {"temperature": 0}
        extra_body: dict[str, Any] = {}

        for key, value in self._request_kwargs.items():
            if key in self._OPENAI_CHAT_CREATE_TOP_LEVEL_KEYS:
                top_level_kwargs[key] = value
            else:
                extra_body[key] = value

        if json_response:
            top_level_kwargs["response_format"] = {"type": "json_object"}
        if extra_body:
            top_level_kwargs["extra_body"] = extra_body
        return top_level_kwargs

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

    def generate_text_from_content(
        self,
        model: str,
        content: str | list[dict[str, Any]],
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> str:
        response = self._sync_client().chat.completions.create(
            model=model,
            messages=self._build_messages_with_content(content, chat_history),
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


class AnthropicLLMClient(LLMClient):
    def __init__(self, api_key: str | None, base_url: str | None = None):
        if not api_key:
            raise ValueError("Missing API key for Anthropic provider")
        self._api_key = api_key
        self._base_url = base_url

    def _build_messages(self, prompt: str, chat_history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        messages = list(chat_history or [])
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_prompt(self, prompt: str, json_response: bool = False) -> str:
        if not json_response:
            return prompt
        return (
            f"{prompt}\n\n"
            "Return valid JSON only. Do not wrap it in Markdown fences. "
            "Do not include any explanatory text before or after the JSON."
        )

    def _sync_client(self) -> anthropic.Anthropic:
        if anthropic.Anthropic is None:
            raise RuntimeError("anthropic package is required for the Anthropic provider")
        return anthropic.Anthropic(api_key=self._api_key, base_url=self._base_url)

    def _async_client(self) -> anthropic.AsyncAnthropic:
        if anthropic.AsyncAnthropic is None:
            raise RuntimeError("anthropic package is required for the Anthropic provider")
        return anthropic.AsyncAnthropic(api_key=self._api_key, base_url=self._base_url)

    def _extract_text(self, response: Any) -> str:
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")

    def _map_finish_reason(self, stop_reason: str | None) -> str:
        if stop_reason == "max_tokens":
            return "max_output_reached"
        return "finished"

    def generate_text(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> str:
        response = self._sync_client().messages.create(
            model=model,
            max_tokens=8192,
            messages=self._build_messages(self._build_prompt(prompt, json_response=json_response), chat_history),
            temperature=0,
        )
        return self._extract_text(response)

    def generate_text_with_finish_reason(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> tuple[str, str]:
        response = self._sync_client().messages.create(
            model=model,
            max_tokens=8192,
            messages=self._build_messages(self._build_prompt(prompt, json_response=json_response), chat_history),
            temperature=0,
        )
        return self._extract_text(response), self._map_finish_reason(getattr(response, "stop_reason", None))

    async def generate_text_async(
        self,
        model: str,
        prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        json_response: bool = False,
    ) -> str:
        async with self._async_client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=8192,
                messages=self._build_messages(self._build_prompt(prompt, json_response=json_response), chat_history),
                temperature=0,
            )
        return self._extract_text(response)
