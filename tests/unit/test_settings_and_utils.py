import pytest

from pageindex.infrastructure.settings import load_settings
from pageindex.core.utils import token_counter, pdf_reader


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_LIBREOFFICE_COMMAND", "/usr/local/bin/soffice")
    monkeypatch.setenv("PAGEINDEX_DOC_CONVERSION_TIMEOUT_SECONDS", "33")
    monkeypatch.setenv("PAGEINDEX_REMOTE_FILE_TIMEOUT_SECONDS", "44")
    monkeypatch.setenv("PAGEINDEX_CALLBACK_TIMEOUT_SECONDS", "55")
    monkeypatch.setenv("PAGEINDEX_CALLBACK_RETRY_COUNT", "6")

    settings = load_settings().service

    assert settings.libreoffice_command == "/usr/local/bin/soffice"
    assert settings.doc_conversion_timeout_seconds == 33
    assert settings.remote_file_timeout_seconds == 44
    assert settings.callback_timeout_seconds == 55
    assert settings.callback_retry_count == 6


def test_count_tokens_falls_back_when_model_encoding_is_unavailable(monkeypatch):
    class _Encoding:
        def encode(self, text):
            return text.split()

    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", lambda model: (_ for _ in ()).throw(KeyError(model)))
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", lambda name: _Encoding())

    assert token_counter.count_tokens("alpha beta gamma", model="unknown-model") == 3


def test_count_tokens_uses_character_estimate_when_all_tokenizers_fail(monkeypatch):
    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", lambda model: (_ for _ in ()).throw(KeyError(model)))
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", lambda name: (_ for _ in ()).throw(ValueError(name)))

    assert token_counter.count_tokens("abcdefghij", model="unknown-model") == 2


def test_count_tokens_uses_qwen_transformers_tokenizer(monkeypatch):
    class _Tokenizer:
        def encode(self, text):
            return list(text)

    class _AutoTokenizer:
        @staticmethod
        def from_pretrained(model_name, trust_remote_code):
            assert model_name == "Qwen/Qwen3-30B-A3B-Instruct-2507"
            assert trust_remote_code is True
            return _Tokenizer()

    token_counter._build_transformers_encoder.cache_clear()
    monkeypatch.setattr(token_counter, "AutoTokenizer", _AutoTokenizer)

    assert token_counter.count_tokens("你好，世界", model="Qwen3-30B-A3B-Instruct-2507") == 5


def test_count_tokens_falls_back_from_qwen_to_tiktoken(monkeypatch):
    class _Encoding:
        def encode(self, text):
            return text.split()

    token_counter._build_transformers_encoder.cache_clear()
    monkeypatch.setattr(token_counter, "AutoTokenizer", None)
    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", lambda model: (_ for _ in ()).throw(KeyError(model)))
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", lambda name: _Encoding())

    assert token_counter.count_tokens("alpha beta gamma", model="Qwen/Qwen3-30B-A3B-Instruct-2507") == 3


def test_get_page_tokens_requires_pypdf2(monkeypatch):
    monkeypatch.setattr(pdf_reader, "PyPDF2", None)

    with pytest.raises(RuntimeError, match="PyPDF2 is required"):
        pdf_reader.get_page_tokens("sample.pdf", pdf_parser="PyPDF2")


def test_get_page_tokens_requires_pymupdf(monkeypatch):
    monkeypatch.setattr(pdf_reader, "pymupdf", None)
    monkeypatch.setattr(pdf_reader, "get_token_encoder", lambda model: (lambda text: []))

    with pytest.raises(RuntimeError, match="pymupdf is required"):
        pdf_reader.get_page_tokens("sample.pdf", pdf_parser="PyMuPDF")
