from pageindex.infrastructure.llm.client import LLMClient, OpenAICompatibleLLMClient
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
        if normalized == "azure_openai":
            return OpenAICompatibleLLMClient(
                api_key=llm_settings.azure_openai_api_key,
                base_url=llm_settings.azure_openai_base_url,
            )
        if normalized in {"openai_compatible", "ollama", "vllm"}:
            return OpenAICompatibleLLMClient(
                api_key=llm_settings.openai_compatible_api_key,
                base_url=llm_settings.openai_compatible_base_url,
            )
        raise ValueError(f"Unsupported provider: {llm_settings.provider}")
