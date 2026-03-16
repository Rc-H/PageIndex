from pageindex.core.indexers.document import infer_file_type
from pageindex.core.indexers.document import docx_parser


def test_infer_file_type_supports_common_extensions_case_insensitively():
    assert infer_file_type("report.PDF") == "pdf"
    assert infer_file_type("outline.MD") == "markdown"
    assert infer_file_type("draft.Markdown") == "markdown"
    assert infer_file_type("notes.DOCX") == "docx"
    assert infer_file_type("legacy.Doc") == "doc"


def test_extract_docx_nodes_uses_fallback_title_when_document_has_no_headings(monkeypatch):
    monkeypatch.setattr(
        docx_parser,
        "_iter_docx_blocks",
        lambda document: iter(
            [
                {"kind": "text", "text": "First paragraph"},
                {"kind": "text", "text": "Second paragraph"},
            ]
        ),
    )

    nodes = docx_parser.extract_docx_nodes(document=object(), fallback_title="sample")

    assert nodes == [
        {
            "title": "sample",
            "line_num": 1,
            "level": 1,
            "text": "sample\nFirst paragraph\nSecond paragraph",
        }
    ]
