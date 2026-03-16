import asyncio

import pytest

from pageindex.core.indexers.document import DocumentIndexer, IndexerDependencies
from tests.helpers import FakeLLMClient


def test_doc_indexer_surfaces_conversion_failure(tmp_path):
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"not-a-real-doc")

    indexer = DocumentIndexer(
        IndexerDependencies(libreoffice_command="command-that-does-not-exist", doc_conversion_timeout_seconds=1)
    )

    with pytest.raises(Exception):
        asyncio.run(
            indexer.index(
                file_path=path,
                provider_type="openai",
                model="gpt-test",
                index_options={},
                llm_client=FakeLLMClient(),
            )
        )
