import json
import sys

import pytest

from run_pageindex import main
from tests.helpers import FakeLLMClient


def test_cli_keeps_single_file_markdown_flow(monkeypatch, tmp_path):
    markdown = tmp_path / "sample.md"
    markdown.write_text("# Intro\nHello", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setattr("run_pageindex.configure_logging", lambda **kwargs: None)
    monkeypatch.setattr("pageindex.infrastructure.llm.LLMProviderFactory.create", lambda _settings: FakeLLMClient())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pageindex.py",
            "--md_path",
            str(markdown),
        ],
    )

    main()

    output = tmp_path / "results" / "sample_structure.json"
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["doc_name"] == "sample"
    assert payload["structure"][0]["title"] == "Intro"


def test_cli_rejects_multiple_input_paths(monkeypatch, tmp_path):
    pdf = tmp_path / "sample.pdf"
    md = tmp_path / "sample.md"
    pdf.write_bytes(b"%PDF-1.4")
    md.write_text("# Intro\nHello", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pageindex.py",
            "--pdf_path",
            str(pdf),
            "--md_path",
            str(md),
        ],
    )

    with pytest.raises(ValueError, match="Exactly one"):
        main()


def test_cli_supports_docx_input(monkeypatch, tmp_path):
    docx = tmp_path / "sample.docx"
    docx.write_bytes(b"fake-docx")
    captured = {}

    async def _fake_index(self, file_path, index_options, llm_client):
        del self, llm_client
        captured["file_path"] = str(file_path)
        captured["index_options"] = index_options
        return {"doc_name": "sample", "structure": [{"title": "Doc"}]}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setattr("run_pageindex.configure_logging", lambda **kwargs: None)
    monkeypatch.setattr("pageindex.core.indexers.document_indexer.DocumentIndexer.index", _fake_index)
    monkeypatch.setattr("pageindex.infrastructure.llm.LLMProviderFactory.create", lambda _settings: FakeLLMClient())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pageindex.py",
            "--doc_path",
            str(docx),
            "--summary-token-threshold",
            "17",
        ],
    )

    main()

    output = tmp_path / "results" / "sample_structure.json"
    assert output.exists()
    assert captured["file_path"] == str(docx)
    assert captured["index_options"]["summary_token_threshold"] == 17
