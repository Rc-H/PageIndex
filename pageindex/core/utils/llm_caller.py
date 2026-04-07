import asyncio
import logging
import time

from pageindex.infrastructure.llm import get_active_llm_client
from pageindex.infrastructure.settings import resolve_model_name


logger = logging.getLogger(__name__)

MAX_RETRIES = 10
_PROMPT_PREVIEW_LENGTH = 300


def _log_request(caller: str, model: str, prompt: str, attempt: int, json_response: bool):
    preview = prompt[:_PROMPT_PREVIEW_LENGTH].replace("\n", "\\n")
    logger.info(
        "[LLM:%s] request attempt=%d model=%s json=%s prompt_len=%d prompt_preview=%s",
        caller, attempt + 1, model, json_response, len(prompt), preview,
    )


def _log_response(caller: str, model: str, response: str, elapsed: float, finish_reason: str | None = None):
    logger.info(
        "[LLM:%s] response model=%s elapsed=%.2fs finish_reason=%s response_len=%d response=%s",
        caller, model, elapsed, finish_reason or "n/a", len(response), response,
    )


def call_llm(model, prompt, chat_history=None, json_response=False):
    resolved_model = resolve_model_name(model)
    for i in range(MAX_RETRIES):
        _log_request("call_llm", resolved_model, prompt, i, json_response)
        try:
            start = time.monotonic()
            result = get_active_llm_client().generate_text(
                model=resolved_model, prompt=prompt, chat_history=chat_history, json_response=json_response,
            )
            _log_response("call_llm", resolved_model, result, time.monotonic() - start)
            return result
        except Exception as e:
            logger.error("[LLM:call_llm] error attempt=%d: %s", i + 1, e)
            if i < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                logger.error("[LLM:call_llm] max retries reached, prompt_len=%d", len(prompt))
                return "Error"


def call_llm_with_finish_reason(model, prompt, chat_history=None, json_response=False):
    resolved_model = resolve_model_name(model)
    for i in range(MAX_RETRIES):
        _log_request("call_llm_with_finish_reason", resolved_model, prompt, i, json_response)
        try:
            start = time.monotonic()
            result, finish_reason = get_active_llm_client().generate_text_with_finish_reason(
                model=resolved_model, prompt=prompt, chat_history=chat_history, json_response=json_response,
            )
            _log_response("call_llm_with_finish_reason", resolved_model, result, time.monotonic() - start, finish_reason)
            return result, finish_reason
        except Exception as e:
            logger.error("[LLM:call_llm_with_finish_reason] error attempt=%d: %s", i + 1, e)
            if i < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                logger.error("[LLM:call_llm_with_finish_reason] max retries reached, prompt_len=%d", len(prompt))
                return "Error"


async def call_llm_async(model, prompt, chat_history=None, json_response=False):
    resolved_model = resolve_model_name(model)
    for i in range(MAX_RETRIES):
        _log_request("call_llm_async", resolved_model, prompt, i, json_response)
        try:
            start = time.monotonic()
            result = await get_active_llm_client().generate_text_async(
                model=resolved_model, prompt=prompt, chat_history=chat_history, json_response=json_response,
            )
            _log_response("call_llm_async", resolved_model, result, time.monotonic() - start)
            return result
        except Exception as e:
            logger.error("[LLM:call_llm_async] error attempt=%d: %s", i + 1, e)
            if i < MAX_RETRIES - 1:
                await asyncio.sleep(1)
            else:
                logger.error("[LLM:call_llm_async] max retries reached, prompt_len=%d", len(prompt))
                return "Error"
