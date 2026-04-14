"""Integration test for block-level granularity on small/medium PDFs.

Requires real LLM access — configure environment variables before running.
Fixture: tests/fixtures/pdfs/GETO-HR-003考勤管理制度.pdf
"""

import asyncio
from pathlib import Path

import pytest

from pageindex.core.indexers.adapters.pdf import PdfAdapter
from pageindex.core.indexers.document_indexer import IndexingOptions
from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.infrastructure.llm import use_llm_client
from pageindex.infrastructure.llm.factory import LLMProviderFactory
from pageindex.infrastructure.settings import load_settings

FIXTURE_PDF = Path(__file__).parent.parent / "fixtures" / "pdfs" / "GETO-HR-003考勤管理制度.pdf"


def _make_context(options_override: dict | None = None):
    settings = load_settings()
    raw = {
        "model": settings.llm.model,
        "if_add_node_id": "yes",
        "if_add_node_summary": "yes",
        "if_add_doc_description": "no",
        "if_add_node_text": "no",
        "block_granularity_page_threshold": 35,
        "max_token_num_per_block_range": 512,
    }
    if options_override:
        raw.update(options_override)
    options = IndexingOptions.from_raw(raw)
    llm_client = LLMProviderFactory.create(settings.llm)
    return PipelineContext(
        source_path=str(FIXTURE_PDF),
        provider_type=settings.llm.provider,
        model=options.model,
        options=options,
        llm_client=llm_client,
        doc_name=FIXTURE_PDF.stem,
    ), llm_client


def _collect_all_nodes(structure):
    nodes = []
    for item in (structure if isinstance(structure, list) else [structure]):
        nodes.append(item)
        if "nodes" in item:
            nodes.extend(_collect_all_nodes(item["nodes"]))
    return nodes


@pytest.mark.skipif(not FIXTURE_PDF.exists(), reason="Fixture PDF not found")
def test_block_granularity_full_pipeline():
    context, llm_client = _make_context()
    adapter = PdfAdapter()

    async def _run():
        with use_llm_client(llm_client):
            return await adapter.build(context)

    result = asyncio.run(_run())

    structure = result["structure"]
    assert isinstance(structure, list)
    assert len(structure) > 0

    all_nodes = _collect_all_nodes(structure)

    # 1. All nodes should have start_block and end_block
    for node in all_nodes:
        assert "start_block" in node, f"Node '{node.get('title')}' missing start_block"
        assert "end_block" in node, f"Node '{node.get('title')}' missing end_block"

    # 2. start_block <= end_block
    for node in all_nodes:
        assert node["start_block"] <= node["end_block"], (
            f"Node '{node.get('title')}': start_block={node['start_block']} > end_block={node['end_block']}"
        )

    # 3. start_index <= end_index
    for node in all_nodes:
        si = node.get("start_index")
        ei = node.get("end_index")
        if si is not None and ei is not None:
            assert si <= ei, (
                f"Node '{node.get('title')}': start_index={si} > end_index={ei}"
            )

    # 4. Sibling nodes should have non-overlapping block ranges
    def _check_sibling_overlap(nodes_list):
        for i in range(len(nodes_list) - 1):
            a = nodes_list[i]
            b = nodes_list[i + 1]
            assert a["end_block"] < b["start_block"], (
                f"Sibling overlap: '{a.get('title')}' end_block={a['end_block']} "
                f">= '{b.get('title')}' start_block={b['start_block']}"
            )
        for n in nodes_list:
            if "nodes" in n:
                _check_sibling_overlap(n["nodes"])

    _check_sibling_overlap(structure)

    # 5. All nodes should have node_id
    for node in all_nodes:
        assert "node_id" in node, f"Node '{node.get('title')}' missing node_id"

    # 6. All nodes should have start_page and end_page
    for node in all_nodes:
        assert node.get("start_page") is not None, f"Node '{node.get('title')}' missing start_page"
        assert node.get("end_page") is not None, f"Node '{node.get('title')}' missing end_page"

    # Print structure for manual inspection
    def _print_tree(nodes, indent=0):
        for n in nodes:
            prefix = "  " * indent
            print(
                f"{prefix}- [{n.get('node_id')}] {n.get('title')} "
                f"(pages {n.get('start_page')}-{n.get('end_page')}, "
                f"blocks {n.get('start_block')}-{n.get('end_block')})"
            )
            if "nodes" in n:
                _print_tree(n["nodes"], indent + 1)

    print("\n=== Structure Tree ===")
    _print_tree(structure)
    print(f"\nTotal nodes: {len(all_nodes)}")
    print(f"Page count: {result.get('page_count')}")
