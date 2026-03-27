from types import SimpleNamespace

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    anthropic = SimpleNamespace(Anthropic=None, AsyncAnthropic=None)
import openai

from pageindex.infrastructure.llm.client import AnthropicLLMClient, LLMClient, OpenAICompatibleLLMClient
from pageindex.infrastructure.llm.context import get_active_llm_client, use_llm_client
from pageindex.infrastructure.llm.factory import LLMProviderFactory

__all__ = [
    "AnthropicLLMClient",
    "LLMClient",
    "LLMProviderFactory",
    "OpenAICompatibleLLMClient",
    "anthropic",
    "get_active_llm_client",
    "openai",
    "use_llm_client",
]
