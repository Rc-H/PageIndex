import pytest

from pageindex.core.utils import image_upload
from pageindex.core.indexers.pipeline.step_06_finalize.result import build_index_result
from pageindex.infrastructure.settings import load_settings
from pageindex.core.utils import token_counter, pdf_reader


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
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
    settings = app_settings.service

    assert llm_settings.provider == "openai_compatible"
    assert llm_settings.model == "gpt-4.1-mini"
    assert settings.libreoffice_command == "/usr/local/bin/soffice"
    assert settings.doc_conversion_timeout_seconds == 33
    assert settings.remote_file_timeout_seconds == 44
    assert settings.callback_timeout_seconds == 55
    assert settings.callback_retry_count == 6
    assert settings.seq_url == "http://seq.local"
    assert settings.seq_api_key == "secret"
    assert settings.log_level == "DEBUG"
    assert settings.log_timeout_seconds == 7
    assert settings.attachment_upload_domain == ""
    assert settings.attachment_upload_api_key is None


def test_load_settings_reads_attachment_upload_environment(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", "demo-key")

    app_settings = load_settings()

    assert app_settings.service.attachment_upload_domain == "http://localhost:8080"
    assert app_settings.service.attachment_upload_api_key == "demo-key"


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


def test_extract_ordered_page_content_includes_image_placeholders():
    class _Page:
        def get_text(self, mode):
            assert mode == "dict"
            return {
                "blocks": [
                    {"type": 0, "bbox": [0, 30, 100, 50], "lines": [{"spans": [{"text": "Second"}]}]},
                    {"type": 1, "bbox": [0, 20, 100, 25]},
                    {"type": 0, "bbox": [0, 10, 100, 15], "lines": [{"spans": [{"text": "First"}]}]},
                ]
            }

    assert pdf_reader._extract_ordered_page_content(_Page()) == "First\n![image]\nSecond"


def test_extract_page_blocks_preserves_order_and_offsets():
    class _Page:
        def get_text(self, mode):
            assert mode == "dict"
            return {
                "blocks": [
                    {"type": 0, "bbox": [0, 30, 100, 50], "lines": [{"spans": [{"text": "Second"}]}]},
                    {"type": 1, "bbox": [0, 20, 100, 25]},
                    {"type": 0, "bbox": [0, 10, 100, 15], "lines": [{"spans": [{"text": "First"}]}]},
                ]
            }

    blocks, next_block_no, next_offset = pdf_reader._extract_page_blocks(
        _Page(),
        page_no=2,
        block_no_start=4,
        doc_char_offset=10,
        encode=lambda text: text.split(),
    )

    assert [block["block_no"] for block in blocks] == [4, 5, 6]
    assert [block["raw_content"] for block in blocks] == ["First", "![image]", "Second"]
    assert [block["page_no"] for block in blocks] == [2, 2, 2]
    assert [block["char_start_in_doc"] for block in blocks] == [10, 16, 25]
    assert [block["metadata"]["type"] for block in blocks] == ["text", "image", "text"]
    assert next_block_no == 7
    assert next_offset == 31


def test_get_page_tokens_prefers_pymupdf_when_available(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_reader, "pymupdf", object())
    monkeypatch.setattr(pdf_reader, "get_token_encoder", lambda model: (lambda text: text.split()))
    monkeypatch.setattr(pdf_reader, "_get_page_tokens_pymupdf", lambda pdf_path, encode: calls.append("pymupdf") or [("x", 1)])
    monkeypatch.setattr(pdf_reader, "_get_page_tokens_pypdf2", lambda pdf_path, encode: calls.append("pypdf2") or [("y", 1)])

    result = pdf_reader.get_page_tokens("sample.pdf")

    assert result == [("x", 1)]
    assert calls == ["pymupdf"]


def test_build_index_result_includes_optional_extract_and_stats():
    result = build_index_result(
        doc_name="sample",
        structure=[{"title": "Intro"}],
        doc_description="summary",
        page_count=3,
        char_count=120,
        token_count=40,
        extract={"blocks": [{"block_no": 1}]},
    )

    assert result == {
        "doc_name": "sample",
        "structure": [{"title": "Intro"}],
        "doc_description": "summary",
        "page_count": 3,
        "char_count": 120,
        "token_count": 40,
        "extract": {"blocks": [{"block_no": 1}]},
    }


def test_upload_image_bytes_returns_uuid_markdown_and_optional_header(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", "secret-key")

    image_upload.load_settings.cache_clear() if hasattr(image_upload.load_settings, "cache_clear") else None

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"uuid": "45296a84-ba5c-418a-add1-d5b7dff86bd4"}}

    class _Client:
        def __init__(self, timeout, headers=None):
            captured["timeout"] = timeout
            captured["headers"] = headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, files):
            captured["url"] = url
            captured["files"] = files
            return _Response()

    monkeypatch.setattr(image_upload.httpx, "Client", _Client)

    markdown = image_upload.upload_image_bytes(b"abc", "sample.png", "image/png")

    assert markdown == "![image](45296a84-ba5c-418a-add1-d5b7dff86bd4)"
    assert captured["url"] == "http://localhost:8080/api/Attachment/upload"
    assert captured["headers"] == {"x-api-key": "secret-key"}


def test_upload_image_bytes_omits_api_key_header_when_empty(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")
    monkeypatch.delenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", raising=False)

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"uuid": "uuid-only"}}

    class _Client:
        def __init__(self, timeout, headers=None):
            captured["headers"] = headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, files):
            return _Response()

    monkeypatch.setattr(image_upload.httpx, "Client", _Client)

    markdown = image_upload.upload_image_bytes(b"abc", "sample.png", "image/png")

    assert markdown == "![image](uuid-only)"
    assert captured["headers"] is None
