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
        {
            "paragraphs": [
                type("_Paragraph", (), {"text": "A"})(),
                type("_Paragraph", (), {"text": "A"})(),
                type("_Paragraph", (), {"text": "B"})(),
            ],
            "tables": [],
        },
    )()

    assert word_paragraphs.extract_table_cell_text(cell) == "A B"


def test_extract_table_cell_text_recovers_nested_table_content(monkeypatch):
    monkeypatch.setattr(
        word_paragraphs,
        "extract_paragraph_text",
        lambda paragraph, image_cache=None: paragraph.text,
    )

    nested_table = object()

    def render_nested(table, image_cache=None):
        assert table is nested_table
        return "nested-row"

    cell = type(
        "_Cell",
        (),
        {
            "paragraphs": [type("_Paragraph", (), {"text": "outer"})()],
            "tables": [nested_table],
        },
    )()

    result = word_paragraphs.extract_table_cell_text(
        cell,
        nested_table_renderer=render_nested,
    )

    assert result == "outer nested-row"


def test_extract_table_cell_text_recurses_through_two_levels(monkeypatch):
    monkeypatch.setattr(
        word_paragraphs,
        "extract_paragraph_text",
        lambda paragraph, image_cache=None: paragraph.text,
    )

    deep_table = type(
        "_DeepTable",
        (),
        {},
    )()

    def render_deep(table, image_cache=None):
        if table is deep_table:
            return "deep-content"
        # Outer table contains a sub-cell which itself has the deep table
        return word_paragraphs.extract_table_cell_text(
            type(
                "_InnerCell",
                (),
                {
                    "paragraphs": [type("_P", (), {"text": "mid"})()],
                    "tables": [deep_table],
                },
            )(),
            nested_table_renderer=render_deep,
        )

    middle_table = type("_MidTable", (), {})()

    cell = type(
        "_Cell",
        (),
        {
            "paragraphs": [type("_P", (), {"text": "top"})()],
            "tables": [middle_table],
        },
    )()

    result = word_paragraphs.extract_table_cell_text(
        cell,
        nested_table_renderer=render_deep,
    )

    # Top paragraph + middle's recursive renderer output (which contains "mid deep-content")
    assert "top" in result
    assert "mid" in result
    assert "deep-content" in result


def test_extract_table_cell_text_dedupes_nested_table_when_identical(monkeypatch):
    monkeypatch.setattr(
        word_paragraphs,
        "extract_paragraph_text",
        lambda paragraph, image_cache=None: paragraph.text,
    )

    cell = type(
        "_Cell",
        (),
        {
            "paragraphs": [type("_P", (), {"text": "X"})()],
            "tables": [object()],
        },
    )()

    result = word_paragraphs.extract_table_cell_text(
        cell,
        nested_table_renderer=lambda table, image_cache=None: "X",
    )

    assert result == "X"


def test_extract_table_cell_text_without_renderer_ignores_nested_tables(monkeypatch):
    monkeypatch.setattr(
        word_paragraphs,
        "extract_paragraph_text",
        lambda paragraph, image_cache=None: paragraph.text,
    )

    cell = type(
        "_Cell",
        (),
        {
            "paragraphs": [type("_P", (), {"text": "outer"})()],
            "tables": [object()],
        },
    )()

    # No nested_table_renderer → tables silently ignored (matches old behavior
    # for callers that don't need nested-table recovery).
    assert word_paragraphs.extract_table_cell_text(cell) == "outer"
