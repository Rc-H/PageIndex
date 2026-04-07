from pageindex.core.indexers import infer_file_type
from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_outline as docx_parser


def test_infer_file_type_supports_common_extensions_case_insensitively():
    assert infer_file_type("report.PDF") == "pdf"
    assert infer_file_type("outline.MD") == "markdown"
    assert infer_file_type("draft.Markdown") == "markdown"
    assert infer_file_type("notes.DOCX") == "docx"
    assert infer_file_type("legacy.Doc") == "doc"


def test_extract_docx_nodes_uses_fallback_title_when_body_has_no_headings():
    body_items = [
        {"kind": "text", "source": "paragraph", "text": "First paragraph"},
        {"kind": "text", "source": "paragraph", "text": "Second paragraph"},
    ]

    nodes = docx_parser.extract_docx_nodes(body_items, fallback_title="sample")

    assert nodes == [
        {
            "title": "sample",
            "line_num": 1,
            "level": 1,
            "text": "sample\nFirst paragraph\nSecond paragraph",
            "start_index": 1,
            "end_index": 1,
        }
    ]
