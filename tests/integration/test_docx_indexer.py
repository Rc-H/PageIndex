import asyncio

import pytest

from pageindex.core.indexers import DocumentIndexer, IndexerDependencies
from tests.helpers import FakeLLMClient, build_docx_bytes


def test_docx_indexer_builds_tree_and_summary(tmp_path):
    try:
        payload = build_docx_bytes()
    except RuntimeError as exc:
        if "python-docx" in str(exc):
            pytest.skip(str(exc))
        raise

    path = tmp_path / "sample.docx"
    path.write_bytes(payload)

    indexer = DocumentIndexer(IndexerDependencies(libreoffice_command="libreoffice", doc_conversion_timeout_seconds=1))
    result = asyncio.run(
        indexer.index(
            file_path=path,
            provider_type="openai",
            model="gpt-test",
            index_options={
                "if_add_node_id": "yes",
                "if_add_node_summary": "yes",
                "if_add_doc_description": "yes",
                "summary_token_threshold": 1,
            },
            llm_client=FakeLLMClient(),
        )
    )

    assert result["doc_name"] == "sample"
    structure = result["structure"]
    assert any(n["title"] == "Executive Summary" for n in structure)
