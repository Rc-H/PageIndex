import asyncio

import pytest

from pageindex.core.indexers import DocumentIndexer, IndexerDependencies
from tests.helpers import FakeLLMClient, build_docx_bytes, build_docx_bytes_with_field_table


def test_docx_indexer_builds_tree_and_summary(tmp_path):
    try:
        payload = build_docx_bytes()
    except RuntimeError as exc:
        if "python-docx" in str(exc):
            pytest.skip(str(exc))
        raise

    path = tmp_path / "sample.docx"
    path.write_bytes(payload)

    indexer = DocumentIndexer(IndexerDependencies(libreoffice_command="libreoffice", doc_conversion_timeout_seconds=1, model="gpt-test"))
    result = asyncio.run(
        indexer.index(
            file_path=path,
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


def test_docx_indexer_formats_field_definition_tables_as_sections(tmp_path):
    try:
        payload = build_docx_bytes_with_field_table()
    except RuntimeError as exc:
        if "python-docx" in str(exc):
            pytest.skip(str(exc))
        raise

    path = tmp_path / "field-table.docx"
    path.write_bytes(payload)

    indexer = DocumentIndexer(IndexerDependencies(libreoffice_command="libreoffice", doc_conversion_timeout_seconds=1, model="gpt-test"))
    result = asyncio.run(
        indexer.index(
            file_path=path,
            index_options={
                "if_add_node_id": "no",
                "if_add_node_summary": "no",
                "if_add_doc_description": "no",
                "if_add_node_text": "yes",
            },
            llm_client=FakeLLMClient(),
        )
    )

    top_level_texts = [node.get("text", "") for node in result["structure"]]
    full_text = "\n".join(top_level_texts)
    assert "## 基本信息" in full_text
    assert "### 核算组织" in full_text
    assert "- 类型：组织" in full_text
    assert "  - 系统生成" in full_text
