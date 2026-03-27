from pageindex.infrastructure.llm.client import AnthropicLLMClient, LLMClient, OpenAICompatibleLLMClient
from pageindex.infrastructure.settings import LLMSettings


class LLMProviderFactory:
    @staticmethod
    def create(llm_settings: LLMSettings) -> LLMClient:
        normalized = (llm_settings.provider or "openai").strip().lower()
        if normalized == "openai":
            return OpenAICompatibleLLMClient(
                api_key=llm_settings.openai_api_key,
                base_url=llm_settings.openai_base_url,
            )
        if normalized == "anthropic":
            return AnthropicLLMClient(
                api_key=llm_settings.anthropic_api_key,
                base_url=llm_settings.anthropic_base_url,
            )
        if normalized == "azure_openai":
            return OpenAICompatibleLLMClient(
                api_key=llm_settings.azure_openai_api_key,
                base_url=llm_settings.azure_openai_base_url,
            )
        if normalized in {"openai_compatible", "ollama", "vllm"}:
            return OpenAICompatibleLLMClient(
                api_key=llm_settings.openai_compatible_api_key,
                base_url=llm_settings.openai_compatible_base_url,
                request_kwargs=llm_settings.openai_compatible_request_kwargs,
            )
        raise ValueError(f"Unsupported provider: {llm_settings.provider}")
