import pytest

from pageindex.infrastructure.settings import load_settings, resolve_model_name


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm-proxy.local")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "")
    monkeypatch.setenv("OPENAI_COMPATIBLE_REQUEST_KWARGS", "{\"chat_template_kwargs\":{\"enable_thinking\":false}}")
    monkeypatch.setenv("PAGEINDEX_LIBREOFFICE_COMMAND", "/usr/local/bin/soffice")
    monkeypatch.setenv("PAGEINDEX_DOC_CONVERSION_TIMEOUT_SECONDS", "33")
    monkeypatch.setenv("PAGEINDEX_REMOTE_FILE_TIMEOUT_SECONDS", "44")
    monkeypatch.setenv("PAGEINDEX_CALLBACK_TIMEOUT_SECONDS", "55")
    monkeypatch.setenv("PAGEINDEX_CALLBACK_RETRY_COUNT", "6")
    monkeypatch.setenv("PAGEINDEX_SEQ_URL", "http://seq.local")
    monkeypatch.setenv("PAGEINDEX_SEQ_API_KEY", "secret")
    monkeypatch.setenv("PAGEINDEX_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("PAGEINDEX_LOG_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", "")

    app_settings = load_settings()
    llm_settings = app_settings.llm
    service_settings = app_settings.service

    assert llm_settings.provider == "openai_compatible"
    assert llm_settings.model == "gpt-4.1-mini"
    assert llm_settings.llm_base_url == "http://llm-proxy.local"
    assert llm_settings.openai_compatible_base_url == "http://llm-proxy.local"
    assert llm_settings.openai_compatible_request_kwargs == {"chat_template_kwargs": {"enable_thinking": False}}
    assert service_settings.libreoffice_command == "/usr/local/bin/soffice"
    assert service_settings.doc_conversion_timeout_seconds == 33
    assert service_settings.remote_file_timeout_seconds == 44
    assert service_settings.callback_timeout_seconds == 55
    assert service_settings.callback_retry_count == 6
    assert service_settings.seq_url == "http://seq.local"
    assert service_settings.seq_api_key == "secret"
    assert service_settings.log_level == "DEBUG"
    assert service_settings.log_timeout_seconds == 7
    assert service_settings.attachment_upload_domain == ""
    assert service_settings.attachment_upload_api_key is None


def test_load_settings_reads_anthropic_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://anthropic-proxy.local")

    app_settings = load_settings()

    assert app_settings.llm.provider == "anthropic"
    assert app_settings.llm.anthropic_api_key == "anthropic-secret"
    assert app_settings.llm.anthropic_base_url == "http://anthropic-proxy.local"


def test_load_settings_rejects_invalid_openai_compatible_request_kwargs(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_REQUEST_KWARGS", "[]")

    with pytest.raises(ValueError, match="OPENAI_COMPATIBLE_REQUEST_KWARGS must be a JSON object"):
        load_settings()


def test_load_settings_reads_attachment_upload_environment(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", "demo-key")

    app_settings = load_settings()

    assert app_settings.service.attachment_upload_domain == "http://localhost:8080"
    assert app_settings.service.attachment_upload_api_key == "demo-key"


def test_resolve_model_name_prefers_explicit_value(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "env-model")

    assert resolve_model_name("explicit-model") == "explicit-model"


def test_resolve_model_name_uses_llm_model_from_settings(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "env-model")

    assert resolve_model_name() == "env-model"
