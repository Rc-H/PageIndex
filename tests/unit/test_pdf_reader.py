import pytest

from pageindex.core.utils import image_upload, pdf_reader
from pageindex.core.utils.pdf import images as pdf_images
from pageindex.core.utils.pdf import tables as pdf_tables


def test_get_page_tokens_requires_pypdf2(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setattr(pdf_reader, "PyPDF2", None)

    with pytest.raises(RuntimeError, match="PyPDF2 is required"):
        pdf_reader.get_page_tokens("sample.pdf", pdf_parser="PyPDF2")


def test_get_page_tokens_requires_pymupdf(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
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


def test_extract_image_markdown_from_pymupdf_block_uploads_and_keeps_original_filename(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    monkeypatch.setattr(pdf_images, "_generate_image_alt_text", lambda *args, **kwargs: "流程图总览说明太长")
    monkeypatch.setattr(pdf_images, "_generate_image_description", lambda *args, **kwargs: "流程图总览说明太长")
    captured = {}
    monkeypatch.setattr(
        pdf_images,
        "upload_attachment_bytes",
        lambda content, filename, content_type=None: captured.update(
            {"content": content, "filename": filename, "content_type": content_type}
        ) or "attachment-uuid",
    )

    markdown = pdf_reader._extract_image_markdown_from_pymupdf_block(
        {"image": b"png-data", "ext": "png"},
        pdf_path=pdf_path,
        page_no=16,
        image_index=1,
        render_images=True,
        model="qwen-test",
    )

    assert markdown == "![流程图总览说明太长](sample.pdf-page-16.png)\n[图片内容：流程图总览说明太长]"
    assert captured == {
        "content": b"png-data",
        "filename": "sample.pdf-page-16.png",
        "content_type": "image/png",
    }


def test_extract_image_markdown_from_pymupdf_block_uses_index_suffix_for_second_image(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    monkeypatch.setattr(pdf_images, "_generate_image_alt_text", lambda *args, **kwargs: "表格总览")
    monkeypatch.setattr(pdf_images, "_generate_image_description", lambda *args, **kwargs: "表格总览")
    monkeypatch.setattr(pdf_images, "upload_attachment_bytes", lambda content, filename, content_type=None: "attachment-uuid")

    markdown = pdf_reader._extract_image_markdown_from_pymupdf_block(
        {"image": b"png-data", "ext": "png"},
        pdf_path=pdf_path,
        page_no=16,
        image_index=2,
        render_images=True,
    )

    assert markdown == "![表格总览](sample.pdf-page-16-2.png)\n[图片内容：表格总览]"


def test_normalize_image_alt_text_truncates_and_strips_punctuation():
    assert pdf_reader._normalize_image_alt_text("《这是一张非常非常长的图片说明！》") == "这是一张非常非常长的图片说明"


def test_normalize_table_cleans_cells_and_infers_header():
    table = pdf_reader._normalize_table(
        [
            [None, None],
            [" A\nB ", " value | raw "],
            [None, " second "],
        ]
    )

    assert table == [
        ["列1", "列2"],
        ["A\nB", "value | raw"],
        ["", "second"],
    ]


def test_table_to_markdown_renders_header_and_escapes_pipes():
    markdown = pdf_reader._table_to_markdown(
        [
            ["名称", "说明"],
            ["字段", "值 | 备注"],
        ]
    )

    assert markdown == "| 名称 | 说明 |\n| --- | --- |\n| 字段 | 值 \\| 备注 |"


def test_render_table_block_includes_summary():
    content = pdf_reader._render_table_block("| A |\n| --- |\n| 1 |", title="季度对比", summary="展示季度变化。")

    assert content == "**表格：季度对比**\n\n| A |\n| --- |\n| 1 |\n\n表格摘要：展示季度变化。"


def test_generate_table_title_falls_back_when_llm_missing(monkeypatch):
    monkeypatch.setattr(pdf_tables, "_generate_text_with_llm", lambda prompt, model=None: None)

    assert pdf_reader._generate_table_title("| A |\n| --- |\n| 1 |", fallback_index=2) == "表格 2"


def test_generate_table_summary_normalizes_multiline_output(monkeypatch):
    monkeypatch.setattr(pdf_tables, "_generate_text_with_llm", lambda prompt, model=None: "第一句。\n\n第二句。")

    assert pdf_reader._generate_table_summary("| A |\n| --- |\n| 1 |") == "第一句。 第二句。"


def test_table_generation_uses_llm_model_from_settings_when_model_not_provided(monkeypatch):
    captured = {}

    class _Client:
        def generate_text(self, model, prompt):
            captured["model"] = model
            captured["prompt"] = prompt
            return "表格标题"

    monkeypatch.setenv("LLM_MODEL", "Qwen3.5-35B-A3B")
    monkeypatch.setattr(pdf_tables, "get_active_llm_client", lambda: _Client())

    assert pdf_tables._generate_text_with_llm("hello") == "表格标题"
    assert captured["model"] == "Qwen3.5-35B-A3B"


def test_image_summary_uses_llm_model_from_settings_when_model_not_provided(monkeypatch):
    captured = {}

    class _Client:
        def generate_text_from_content(self, model, content):
            captured["model"] = model
            captured["content"] = content
            return "图片标题"

    monkeypatch.setenv("LLM_MODEL", "Qwen3.5-35B-A3B")
    monkeypatch.setattr(image_upload, "get_active_llm_client", lambda: _Client())
    monkeypatch.setattr(image_upload, "OpenAICompatibleLLMClient", _Client)

    assert image_upload.summarize_image_with_llm(b"png-data", content_type="image/png") == "图片标题"
    assert captured["model"] == "Qwen3.5-35B-A3B"


def test_extract_tables_by_page_prefers_pdfplumber_over_camelot(monkeypatch):
    monkeypatch.setattr(pdf_tables, "_extract_tables_with_pdfplumber", lambda pdf_path, model=None: {1: [{"engine": "pdfplumber"}]})
    monkeypatch.setattr(pdf_tables, "_extract_missing_tables_with_camelot", lambda pdf_path, extracted_pages, model=None: {1: [{"engine": "camelot"}]})

    assert pdf_reader._extract_tables_by_page("sample.pdf") == {1: [{"engine": "pdfplumber"}]}


def test_extract_tables_by_page_falls_back_to_camelot(monkeypatch):
    monkeypatch.setattr(pdf_tables, "_extract_tables_with_pdfplumber", lambda pdf_path, model=None: {})
    monkeypatch.setattr(pdf_tables, "_extract_missing_tables_with_camelot", lambda pdf_path, extracted_pages, model=None: {1: [{"engine": "camelot"}]})

    assert pdf_reader._extract_tables_by_page("sample.pdf") == {1: [{"engine": "camelot"}]}


def test_extract_tables_by_page_limits_camelot_to_missing_pages(monkeypatch):
    captured = {}
    monkeypatch.setattr(pdf_tables, "_extract_tables_with_pdfplumber", lambda pdf_path, model=None: {1: [{"engine": "pdfplumber"}]})
    monkeypatch.setattr(pdf_tables, "_get_pdf_page_numbers", lambda pdf_path: [1, 2, 3])
    monkeypatch.setattr(
        pdf_tables,
        "_extract_camelot_tables",
        lambda pdf_path, page_numbers=None, model=None: captured.update({"page_numbers": page_numbers}) or {2: [{"engine": "camelot"}]},
    )

    result = pdf_reader._extract_tables_by_page("sample.pdf")

    assert result == {
        1: [{"engine": "pdfplumber"}],
        2: [{"engine": "camelot"}],
    }
    assert captured["page_numbers"] == [2, 3]


def test_extract_page_blocks_includes_tables_and_skips_overlapping_text(monkeypatch):
    class _Rect:
        width = 595.276
        height = 841.89

    class _Page:
        rect = _Rect()

        def get_text(self, mode):
            assert mode == "dict"
            return {
                "blocks": [
                    {"type": 0, "bbox": [0, 12, 100, 48], "lines": [{"spans": [{"text": "Inside table"}]}]},
                    {"type": 1, "bbox": [0, 60, 100, 80], "image": b"png", "ext": "png"},
                    {"type": 0, "bbox": [0, 90, 100, 110], "lines": [{"spans": [{"text": "After"}]}]},
                ]
            }

    monkeypatch.setattr(pdf_images, "_generate_image_alt_text", lambda *args, **kwargs: "图示")
    monkeypatch.setattr(pdf_images, "_generate_image_description", lambda *args, **kwargs: "详细描述")
    monkeypatch.setattr(pdf_images, "upload_attachment_bytes", lambda *args, **kwargs: "attachment-uuid")

    table = {
        "bbox": [0, 10, 100, 50],
        "rows": 2,
        "cols": 2,
        "cells": [["A", "B"], ["1", "2"]],
        "engine": "pdfplumber",
        "title": "季度对比",
        "summary": "展示季度变化。",
        "markdown": "**表格：季度对比**\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n表格摘要：展示季度变化。",
    }

    blocks, next_block_no, next_offset = pdf_reader._extract_page_blocks(
        _Page(),
        page_no=2,
        block_no_start=4,
        doc_char_offset=10,
        encode=lambda text: text.split(),
        pdf_path="sample.pdf",
        page_tables=[table],
    )

    assert [block["metadata"]["type"] for block in blocks] == ["table", "image", "text"]
    assert "Inside table" not in [block["raw_content"] for block in blocks]
    assert blocks[0]["metadata"]["table"]["engine"] == "pdfplumber"
    assert blocks[1]["metadata"]["image"] == {
        "file_name": "sample.pdf-page-2.png",
        "attachment_id": "attachment-uuid",
        "img_title": "图示",
        "img_description": "详细描述",
        "page_no": 2,
        "image_index": 1,
    }
    assert next_block_no == 7
    assert next_offset > 10


def test_extract_page_blocks_preserves_order_and_offsets():
    class _Rect:
        width = 595.276
        height = 841.89

    class _Page:
        rect = _Rect()

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
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    calls = []
    monkeypatch.setattr(pdf_reader, "pymupdf", object())
    monkeypatch.setattr(pdf_reader, "get_token_encoder", lambda model: (lambda text: text.split()))
    monkeypatch.setattr(
        pdf_reader,
        "_get_page_tokens_pymupdf",
        lambda pdf_path, encode, model=None, tables_by_page=None: calls.append("pymupdf") or [("x", 1)],
    )
    monkeypatch.setattr(pdf_reader, "_get_page_tokens_pypdf2", lambda pdf_path, encode: calls.append("pypdf2") or [("y", 1)])

    result = pdf_reader.get_page_tokens("sample.pdf")

    assert result == [("x", 1)]
    assert calls == ["pymupdf"]
