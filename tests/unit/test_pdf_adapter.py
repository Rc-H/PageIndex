import asyncio
from pathlib import Path

from pageindex.core.indexers.adapters import pdf as pdf_adapter
from pageindex.core.indexers.document_indexer import IndexingOptions
from pageindex.core.indexers.pipeline.context import PipelineContext


def test_pdf_adapter_build_includes_extract_blocks_stats_and_node_mapping(monkeypatch):
    class _Logger:
        def info(self, payload):
            return None

    async def _build_pdf_tree(page_list, opt, logger=None):
        return [
            {
                "node_id": "0001",
                "title": "Intro",
                "start_index": 1,
                "end_index": 2,
                "nodes": [
                    {
                        "node_id": "0002",
                        "title": "Details",
                        "start_index": 2,
                        "end_index": 2,
                        "nodes": [],
                    }
                ],
            }
        ]

    monkeypatch.setattr(pdf_adapter, "get_logger", lambda *args, **kwargs: _Logger())
    monkeypatch.setattr(pdf_adapter, "_extract_tables_by_page", lambda source_path, model=None: {1: [], 2: []})
    monkeypatch.setattr(pdf_adapter, "get_page_tokens", lambda source_path, model=None, tables_by_page=None: [("Page 1", 3), ("Page 2", 5)])
    monkeypatch.setattr(pdf_adapter, "_build_pdf_tree", _build_pdf_tree)
    monkeypatch.setattr(
        pdf_adapter,
        "extract_pdf_blocks",
        lambda source_path, model, tables_by_page=None: [
            {
                "block_no": 1,
                "page_no": 1,
                "block_order_in_page": 1,
                "start_index": 1,
                "end_index": 1,
                "raw_content": "First",
                "normalized_text": "First",
                "display_text": "First",
                "char_start_in_doc": 0,
                "char_end_in_doc": 4,
                "char_start_in_page": 0,
                "char_end_in_page": 4,
                "token_count": 2,
                "metadata": {"kind": "text"},
            },
            {
                "block_no": 2,
                "page_no": 2,
                "block_order_in_page": 1,
                "start_index": 2,
                "end_index": 2,
                "raw_content": "Second",
                "normalized_text": "Second",
                "display_text": "Second",
                "char_start_in_doc": 6,
                "char_end_in_doc": 11,
                "char_start_in_page": 0,
                "char_end_in_page": 5,
                "token_count": 3,
                "metadata": {"kind": "text"},
            },
        ],
    )

    context = PipelineContext(
        source_path=Path("sample.pdf"),
        provider_type="openai",
        model="gpt-test",
        options=IndexingOptions.from_raw(
            {
                "model": "gpt-test",
                "if_add_node_id": "no",
                "if_add_node_summary": "no",
                "if_add_doc_description": "no",
                "if_add_node_text": "no",
            }
        ),
        llm_client=None,
        doc_name="sample",
    )

    result = asyncio.run(pdf_adapter.PdfAdapter().build(context))

    assert result["doc_name"] == "sample"
    assert result["page_count"] == 2
    assert result["char_count"] == 12
    assert result["token_count"] == 5
    assert [block["pageindex_node_id"] for block in result["extract"]["blocks"]] == ["0001", "0002"]


def test_attach_block_node_ids_prefers_deepest_covering_node():
    blocks = [
        {"page_no": 1},
        {"page_no": 2},
        {"page_no": 3},
    ]
    structure = [
        {
            "node_id": "0001",
            "start_index": 1,
            "end_index": 3,
            "nodes": [
                {
                    "node_id": "0002",
                    "start_index": 2,
                    "end_index": 3,
                    "nodes": [],
                }
            ],
        }
    ]

    pdf_adapter._attach_block_node_ids(blocks, structure)

    assert [block.get("pageindex_node_id") for block in blocks] == ["0001", "0002", "0002"]
