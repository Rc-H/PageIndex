import httpx
import openai
import pytest

from pageindex.core.utils.llm_retry import extract_status_code, is_retryable_llm_error


def _httpx_response(status: int) -> httpx.Response:
    return httpx.Response(status_code=status, request=httpx.Request("POST", "http://example.com"))


def _openai_error(cls, status: int, message: str = "bad"):
    return cls(message=message, response=_httpx_response(status), body=None)


@pytest.mark.parametrize(
    "cls, status",
    [
        (openai.BadRequestError, 400),
        (openai.AuthenticationError, 401),
        (openai.PermissionDeniedError, 403),
        (openai.NotFoundError, 404),
        (openai.UnprocessableEntityError, 422),
    ],
)
def test_openai_4xx_is_not_retryable(cls, status):
    assert is_retryable_llm_error(_openai_error(cls, status)) is False


def test_openai_rate_limit_is_retryable():
    assert is_retryable_llm_error(_openai_error(openai.RateLimitError, 429)) is True


def test_openai_500_is_retryable():
    assert is_retryable_llm_error(_openai_error(openai.InternalServerError, 500)) is True


def test_generic_exception_is_retryable():
    assert is_retryable_llm_error(RuntimeError("transient")) is True


def test_status_code_attr_on_exception_drives_classification():
    fake_cls = type("FakeStatusError", (Exception,), {})

    err_400 = fake_cls("bad")
    err_400.status_code = 400
    assert is_retryable_llm_error(err_400) is False

    err_500 = fake_cls("boom")
    err_500.status_code = 500
    assert is_retryable_llm_error(err_500) is True


def test_extract_status_code_reads_response_attribute():
    err = type("FakeStatusError", (Exception,), {})("bad")
    err.response = _httpx_response(418)
    assert extract_status_code(err) == 418


def test_408_409_429_are_retryable_status_codes():
    for status in (408, 409, 429):
        err = type("FakeStatusError", (Exception,), {})("transient")
        err.status_code = status
        assert is_retryable_llm_error(err) is True
