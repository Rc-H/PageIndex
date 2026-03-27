from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_paragraphs


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

    original_run = word_paragraphs.Run
    original_qn = word_paragraphs.qn
    word_paragraphs.Run = _Run
    word_paragraphs.qn = _fake_qn
    try:
        assert word_paragraphs.extract_paragraph_text(_Paragraph()) == "![image]caption"
    finally:
        word_paragraphs.Run = original_run
        word_paragraphs.qn = original_qn


def test_extract_table_cell_text_deduplicates_paragraph_text(monkeypatch):
    monkeypatch.setattr(word_paragraphs, "extract_paragraph_text", lambda paragraph, image_cache=None: paragraph.text)

    cell = type(
        "_Cell",
        (),
        {"paragraphs": [type("_Paragraph", (), {"text": "A"})(), type("_Paragraph", (), {"text": "A"})(), type("_Paragraph", (), {"text": "B"})()]},
    )()

    assert word_paragraphs.extract_table_cell_text(cell) == "A B"
