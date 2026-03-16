from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from pageindex.infrastructure.llm.client import LLMClient
from pageindex.infrastructure.llm.factory import LLMProviderFactory


_llm_client_var: ContextVar[LLMClient | None] = ContextVar("pageindex_llm_client", default=None)


def get_active_llm_client() -> LLMClient:
    client = _llm_client_var.get()
    if client is not None:
        return client
    from pageindex.infrastructure.settings import load_settings
    return LLMProviderFactory.create(load_settings().llm)


@contextmanager
def use_llm_client(client: LLMClient):
    token = _llm_client_var.set(client)
    try:
        yield
    finally:
        _llm_client_var.reset(token)
