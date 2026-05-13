from __future__ import annotations

import openai

try:
    import anthropic
except ImportError:
    anthropic = None


def _openai_non_retryable_types() -> tuple[type, ...]:
    return (
        openai.BadRequestError,
        openai.AuthenticationError,
        openai.PermissionDeniedError,
        openai.NotFoundError,
        openai.UnprocessableEntityError,
    )


def _anthropic_non_retryable_types() -> tuple[type, ...]:
    if anthropic is None:
        return ()
    candidates = (
        "BadRequestError",
        "AuthenticationError",
        "PermissionDeniedError",
        "NotFoundError",
        "UnprocessableEntityError",
    )
    return tuple(getattr(anthropic, name) for name in candidates if hasattr(anthropic, name))


def is_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, _openai_non_retryable_types()):
        return False
    if isinstance(exc, _anthropic_non_retryable_types()):
        return False

    status = extract_status_code(exc)
    if status is not None and 400 <= status < 500 and status not in (408, 409, 429):
        return False

    return True


def extract_status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None
