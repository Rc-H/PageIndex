import asyncio
from pathlib import Path
from types import SimpleNamespace

from pageindex.core.indexers.adapters import markdown, pdf, word
from pageindex.core.indexers.pipeline.context import PipelineContext


def _build_options(**overrides):
    defaults = {
        "if_add_node_id": "yes",
        "if_add_node_summary": "no",
        "if_add_doc_description": "no",
        "if_add_node_text": "no",
        "if_thinning": "no",
        "thinning_threshold": 0,
        "summary_token_threshold": 0,
        "model": "gpt-test",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_pdf_adapter_build_includes_extract_blocks_and_stats(monkeypatch, tmp_path):
    context = PipelineContext(
        source_path=tmp_path / "sample.pdf",
        provider_type="openai",
        model="gpt-test",
        options=_build_options(),
        llm_client=None,
        doc_name="sample",
    )

    monkeypatch.setattr(pdf, "get_logger", lambda *args, **kwargs: SimpleNamespace(info=lambda *a, **k: None))
    monkeypatch.setattr(pdf, "get_page_tokens", lambda source_path: [("page-1", 3), ("page-2", 5)])

    async def _fake_build_pdf_tree(page_list, opt, logger=None):
        return [
            {
                "node_id": "0001",
                "title": "Intro",
                "start_index": 1,
                "end_index": 2,
                "nodes": [
                    {
                        "node_id": "0002",
                        "title": "Child",
                        "start_index": 2,
                        "end_index": 2,
                        "nodes": [],
                    }
                ],
            }
        ]

    monkeypatch.setattr(pdf, "_build_pdf_tree", _fake_build_pdf_tree)
    monkeypatch.setattr(pdf, "write_node_id", lambda structure: None)
    monkeypatch.setattr(
        pdf,
        "extract_pdf_blocks",
        lambda source_path, model: [
            {
                "block_no": 1,
                "page_no": 1,
                "block_order_in_page": 1,
                "start_index": 1,
                "end_index": 1,
                "raw_content": "Alpha",
                "normalized_text": "Alpha",
                "display_text": "Alpha",
                "char_start_in_doc": 0,
                "char_end_in_doc": 4,
                "char_start_in_page": 0,
                "char_end_in_page": 4,
                "token_count": 1,
            },
            {
                "block_no": 2,
                "page_no": 2,
                "block_order_in_page": 1,
                "start_index": 2,
                "end_index": 2,
                "raw_content": "Beta",
                "normalized_text": "Beta",
                "display_text": "Beta",
                "char_start_in_doc": 6,
                "char_end_in_doc": 9,
                "char_start_in_page": 0,
                "char_end_in_page": 3,
                "token_count": 2,
            },
        ],
    )

    result = asyncio.run(pdf.PdfAdapter().build(context))

    assert result["page_count"] == 2
    assert result["char_count"] == 10
    assert result["token_count"] == 3
    assert result["extract"]["blocks"][0]["pageindex_node_id"] == "0001"
    assert result["extract"]["blocks"][1]["pageindex_node_id"] == "0002"


def test_markdown_adapter_build_includes_stats(monkeypatch, tmp_path):
    markdown_path = tmp_path / "sample.md"
    markdown_content = "# Title\nHello world"
    markdown_path.write_text(markdown_content, encoding="utf-8")

    context = PipelineContext(
        source_path=markdown_path,
        provider_type="openai",
        model="gpt-test",
        options=_build_options(if_add_node_id="no"),
        llm_client=None,
        doc_name="sample",
    )

    monkeypatch.setattr(markdown, "extract_nodes_from_markdown", lambda content: ([{"title": "Title"}], content.splitlines()))
    monkeypatch.setattr(markdown, "extract_node_text_content", lambda node_list, lines: [{"title": "Title", "text": "Hello world", "line_num": 1}])
    monkeypatch.setattr(markdown, "build_tree_from_nodes", lambda nodes: [{"title": "Title", "line_num": 1, "nodes": []}])
    monkeypatch.setattr(markdown, "format_structure", lambda structure, order: structure)
    monkeypatch.setattr(markdown, "count_tokens", lambda content, model: 7)

    result = asyncio.run(markdown.MarkdownAdapter().build(context))

    assert result["doc_name"] == "sample"
    assert result["char_count"] == len(markdown_content)
    assert result["token_count"] == 7


def test_word_adapter_build_includes_stats(monkeypatch, tmp_path):
    class _WordDocument:
        def __init__(self, path):
            self.path = path

    word_path = tmp_path / "sample.docx"
    word_path.write_bytes(b"demo")

    context = PipelineContext(
        source_path=word_path,
        provider_type="openai",
        model="gpt-test",
        options=_build_options(if_add_node_id="no"),
        llm_client=None,
        doc_name="sample",
    )

    monkeypatch.setattr(word, "require_word_document", lambda: _WordDocument)
    monkeypatch.setattr(
        word,
        "extract_docx_nodes",
        lambda document, doc_name: [
            {"title": "Intro", "text": "Alpha"},
            {"title": "Body", "text": "Beta"},
        ],
    )
    monkeypatch.setattr(word, "build_tree_from_nodes", lambda nodes: [{"title": "Intro", "line_num": 1, "nodes": []}])
    monkeypatch.setattr(word, "format_structure", lambda structure, order: structure)
    monkeypatch.setattr(word, "count_tokens", lambda content, model: 5)

    result = asyncio.run(word.WordAdapter().build(context))

    assert result["doc_name"] == Path(word_path).stem
    assert result["char_count"] == len("Alpha\n\nBeta")
    assert result["token_count"] == 5
