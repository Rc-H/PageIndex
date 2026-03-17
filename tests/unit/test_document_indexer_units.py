from pageindex.core.indexers import infer_file_type
from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_outline as docx_parser


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


def test_extract_paragraph_text_keeps_embedded_image_placeholders():
    class _Rel:
        is_external = False

    class _Part:
        rels = {"rId1": _Rel()}

    def _fake_qn(value):
        return value

    class _RunElement:
        tag = "w:r"

        def findall(self, query):
            if query == "w:fldChar":
                return []
            if query == "w:instrText":
                return []
            if query == ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing":
                return [self]
            if query == ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip":
                return [self]
            if query == ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pict":
                return []
            return []

        def get(self, key):
            if key == "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed":
                return "rId1"
            return None

    class _Run:
        def __init__(self, element, paragraph):
            self.element = element
            self.text = "caption"

    class _Paragraph:
        part = _Part()
        _element = [_RunElement()]
        text = "caption"

    original_run = docx_parser.Run
    original_qn = docx_parser.qn
    docx_parser.Run = _Run
    docx_parser.qn = _fake_qn
    try:
        assert docx_parser._extract_paragraph_text(_Paragraph()) == "![image]caption"
    finally:
        docx_parser.Run = original_run
        docx_parser.qn = original_qn
