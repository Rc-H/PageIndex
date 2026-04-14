import asyncio
from pathlib import Path
from types import SimpleNamespace

from pageindex.core.indexers.adapters import markdown, pdf, word
from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.core.indexers.pipeline.step_06_finalize import word_block_finalizer


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
        "block_granularity_page_threshold": 0,
        "max_token_num_per_block_range": 512,
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
    monkeypatch.setattr(pdf, "_extract_tables_by_page", lambda source_path, model=None: {})
    monkeypatch.setattr(pdf, "get_page_tokens", lambda source_path, model=None, tables_by_page=None: [("page-1", 3), ("page-2", 5)])

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
        lambda source_path, model=None, tables_by_page=None: [
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


def test_word_adapter_build_emits_extract_blocks_with_node_links(monkeypatch, tmp_path):
    class _WordDocument:
        def __init__(self, path):
            self.path = path

    word_path = tmp_path / "sample.docx"
    word_path.write_bytes(b"demo")

    context = PipelineContext(
        source_path=word_path,
        provider_type="openai",
        model="gpt-test",
        # if_add_node_id="yes" so the final structure keeps node_id visible
        # (the adapter assigns ids unconditionally, but visibility is gated).
        options=_build_options(if_add_node_id="yes"),
        llm_client=None,
        doc_name="sample",
    )

    flat_nodes = [
        {"title": "Intro", "level": 1, "line_num": 1, "text": "Intro\nAlpha", "start_index": 1, "end_index": 1},
        {"title": "Body", "level": 1, "line_num": 3, "text": "Body\nBeta", "start_index": 2, "end_index": 2},
    ]
    raw_blocks = [
        {"section_ordinal": 1, "raw_text": "Intro", "source": "paragraph"},
        {"section_ordinal": 1, "raw_text": "Alpha", "source": "paragraph"},
        {"section_ordinal": 2, "raw_text": "Body", "source": "paragraph"},
        {"section_ordinal": 2, "raw_text": "Beta", "source": "paragraph"},
    ]

    monkeypatch.setattr(word, "require_word_document", lambda: _WordDocument)
    # Bypass the body iterator entirely; the test injects the post-iterator
    # state directly via extract_docx_nodes / extract_docx_blocks stubs.
    monkeypatch.setattr(word, "iter_docx_body_items", lambda *args, **kwargs: iter([]))
    monkeypatch.setattr(word, "extract_docx_nodes", lambda body_items, doc_name: flat_nodes)
    monkeypatch.setattr(word, "extract_docx_blocks", lambda body_items: raw_blocks)
    # Use the real build_tree_from_nodes / write_node_id / format_structure /
    # finalize_word_blocks so the test exercises the integrated contract.
    monkeypatch.setattr(word_block_finalizer, "count_tokens", lambda text, model=None: len(text))

    result = asyncio.run(word.WordAdapter().build(context))

    assert result["doc_name"] == Path(word_path).stem
    assert result["location_unit"] == "section"

    blocks = result["extract"]["blocks"]
    # 4 raw blocks → 4 emitted blocks (none empty)
    assert len(blocks) == 4

    # PDF-shape required fields
    required = {
        "block_no", "page_no", "block_order_in_page", "start_index", "end_index",
        "raw_content", "normalized_text", "display_text",
        "char_start_in_doc", "char_end_in_doc", "char_start_in_page", "char_end_in_page",
        "token_count", "metadata",
    }
    for block in blocks:
        assert required.issubset(block.keys())
        assert block["metadata"]["type"] == "text"
        assert block["metadata"]["pageindex_node_id"] is not None

    # Section ordinals carry through correctly
    assert [b["start_index"] for b in blocks] == [1, 1, 2, 2]
    assert [b["end_index"] for b in blocks] == [1, 1, 2, 2]
    assert [b["page_no"] for b in blocks] == [1, 1, 2, 2]
    assert [b["block_no"] for b in blocks] == [1, 2, 3, 4]
    assert [b["block_order_in_page"] for b in blocks] == [1, 2, 1, 2]

    # All node ids reference real nodes in the structure
    structure_node_ids = _collect_node_ids(result["structure"])
    for block in blocks:
        assert block["metadata"]["pageindex_node_id"] in structure_node_ids

    # char_count totals match the sum of normalized_text lengths
    assert result["char_count"] == sum(len(b["normalized_text"]) for b in blocks)
    assert result["token_count"] == sum(b["token_count"] for b in blocks)


def _collect_node_ids(structure):
    ids: set[str] = set()
    if isinstance(structure, dict):
        if "node_id" in structure:
            ids.add(structure["node_id"])
        ids.update(_collect_node_ids(structure.get("nodes") or []))
    elif isinstance(structure, list):
        for item in structure:
            ids.update(_collect_node_ids(item))
    return ids
