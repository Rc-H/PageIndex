"""Unit tests for the DOCX body iterator.

Uses lightweight stub objects rather than real python-docx Document objects.
The iterator only needs ``element.body.iterchildren()``, ``paragraphs``,
``tables``, and the per-paragraph attributes that ``extract_paragraph_text``
reads (which we monkeypatch out).
"""

from __future__ import annotations

import pytest

from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_body_iterator


WORDPROCESSINGML_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class _Child:
    def __init__(self, tag: str):
        self.tag = WORDPROCESSINGML_NS + tag


class _Body:
    def __init__(self, children):
        self._children = children

    def iterchildren(self):
        return iter(self._children)


class _Element:
    def __init__(self, body):
        self.body = body


class _Style:
    def __init__(self, name: str | None):
        self.name = name


class _Paragraph:
    def __init__(self, child, text: str, style_name: str | None = None):
        self._p = child
        self._text_value = text
        self.style = _Style(style_name)


class _Table:
    def __init__(self, child, text: str):
        self._tbl = child
        self._text_value = text


class _Document:
    def __init__(self, items):
        self._items = items
        children = [item._p if hasattr(item, "_p") else item._tbl for item in items]
        self.element = _Element(_Body(children))
        self.paragraphs = [item for item in items if isinstance(item, _Paragraph)]
        self.tables = [item for item in items if isinstance(item, _Table)]


@pytest.fixture(autouse=True)
def _stub_paragraph_and_table(monkeypatch):
    monkeypatch.setattr(
        word_body_iterator,
        "extract_paragraph_text",
        lambda paragraph, image_cache: paragraph._text_value,
    )
    monkeypatch.setattr(
        word_body_iterator,
        "extract_table_text",
        lambda table, cell_renderer, image_cache: table._text_value,
    )
    # Disable the LLM-driven field-table expander by default — tests that
    # specifically need it monkeypatch try_expand_field_table directly.
    monkeypatch.setattr(
        word_body_iterator,
        "try_expand_field_table",
        lambda **kwargs: None,
    )


def _build_document(items):
    return _Document(items)


def test_empty_body_yields_nothing():
    document = _build_document([])
    assert list(word_body_iterator.iter_docx_body_items(document, {})) == []


def test_single_paragraph_yields_text_paragraph_item():
    para = _Paragraph(_Child("p"), "hello")
    document = _build_document([para])

    items = list(word_body_iterator.iter_docx_body_items(document, {}))

    assert items == [{"kind": "text", "source": "paragraph", "text": "hello"}]


def test_single_heading_paragraph_yields_heading_with_level():
    para = _Paragraph(_Child("p"), "Section A", style_name="Heading 2")
    document = _build_document([para])

    items = list(word_body_iterator.iter_docx_body_items(document, {}))

    assert items == [
        {"kind": "heading", "source": "paragraph", "text": "Section A", "level": 2}
    ]


def test_single_table_yields_text_table_item():
    table = _Table(_Child("tbl"), "row1 | row2")
    document = _build_document([table])

    items = list(word_body_iterator.iter_docx_body_items(document, {}))

    assert items == [{"kind": "text", "source": "table", "text": "row1 | row2"}]


def test_mixed_items_preserve_body_order():
    items_in = [
        _Paragraph(_Child("p"), "Title", style_name="Heading 1"),
        _Paragraph(_Child("p"), "intro paragraph"),
        _Table(_Child("tbl"), "tabletext"),
        _Paragraph(_Child("p"), "outro paragraph"),
    ]
    document = _build_document(items_in)

    yielded = list(word_body_iterator.iter_docx_body_items(document, {}))

    assert [item["text"] for item in yielded] == [
        "Title",
        "intro paragraph",
        "tabletext",
        "outro paragraph",
    ]
    assert [item["kind"] for item in yielded] == ["heading", "text", "text", "text"]
    assert [item["source"] for item in yielded] == ["paragraph", "paragraph", "table", "paragraph"]


def test_whitespace_only_paragraphs_are_skipped(monkeypatch):
    monkeypatch.setattr(
        word_body_iterator,
        "extract_paragraph_text",
        lambda paragraph, image_cache: paragraph._text_value,
    )

    items_in = [
        _Paragraph(_Child("p"), "   "),
        _Paragraph(_Child("p"), "\n\t"),
        _Paragraph(_Child("p"), "real text"),
    ]
    document = _build_document(items_in)

    yielded = list(word_body_iterator.iter_docx_body_items(document, {}))

    assert [item["text"] for item in yielded] == ["real text"]


def test_image_cache_is_threaded_into_paragraph_extractor(monkeypatch):
    captured = {}

    def fake_extract(paragraph, image_cache):
        captured["cache"] = image_cache
        return paragraph._text_value

    monkeypatch.setattr(word_body_iterator, "extract_paragraph_text", fake_extract)

    cache: dict[object, str] = {"sentinel": "value"}
    document = _build_document([_Paragraph(_Child("p"), "hello")])

    list(word_body_iterator.iter_docx_body_items(document, cache))

    assert captured["cache"] is cache


def test_image_cache_is_threaded_into_table_renderer(monkeypatch):
    captured = {}

    def fake_extract_table(table, cell_renderer, image_cache):
        captured["cache"] = image_cache
        return table._text_value

    monkeypatch.setattr(word_body_iterator, "extract_table_text", fake_extract_table)

    cache: dict[object, str] = {}
    document = _build_document([_Table(_Child("tbl"), "x")])

    list(word_body_iterator.iter_docx_body_items(document, cache))

    assert captured["cache"] is cache


def test_table_expander_is_skipped_when_model_not_provided(monkeypatch):
    expander_calls = {"count": 0}

    def fake_expander(**kwargs):
        expander_calls["count"] += 1
        return None

    monkeypatch.setattr(word_body_iterator, "try_expand_field_table", fake_expander)

    document = _build_document([_Table(_Child("tbl"), "table-text")])

    items = list(word_body_iterator.iter_docx_body_items(document, {}))  # no model

    assert expander_calls["count"] == 0
    assert items == [{"kind": "text", "source": "table", "text": "table-text"}]


def test_table_expander_is_called_when_model_provided(monkeypatch):
    captured = {}

    def fake_expander(**kwargs):
        captured.update(kwargs)
        return None  # decline expansion

    monkeypatch.setattr(word_body_iterator, "try_expand_field_table", fake_expander)

    document = _build_document([_Table(_Child("tbl"), "table-text")])

    list(word_body_iterator.iter_docx_body_items(document, {}, doc_name="MyDoc", model="gpt-test"))

    assert captured["model"] == "gpt-test"
    # No prior heading → heading_path should contain only the doc name
    assert captured["heading_path"] == ["MyDoc"]


def test_table_expansion_yields_heading_and_text_items(monkeypatch):
    document = _build_document([
        _Paragraph(_Child("p"), "Outer Section", style_name="Heading 1"),
        _Table(_Child("tbl"), "ignored when expanded"),
    ])

    def fake_expander(**kwargs):
        # Expand into 2 fields
        return [
            {"kind": "heading", "source": "table", "text": "field_a", "level_offset": 1},
            {"kind": "text", "source": "table", "text": "body of a"},
            {"kind": "heading", "source": "table", "text": "field_b", "level_offset": 1},
            {"kind": "text", "source": "table", "text": "body of b"},
        ]

    monkeypatch.setattr(word_body_iterator, "try_expand_field_table", fake_expander)

    items = list(word_body_iterator.iter_docx_body_items(document, {}, doc_name="Doc", model="m"))

    # 1 outer heading + 4 expanded items
    assert len(items) == 5
    # Outer heading at its real level
    assert items[0] == {"kind": "heading", "source": "paragraph", "text": "Outer Section", "level": 1}
    # Field heading absolute level = base (1) + offset (1) = 2
    assert items[1] == {"kind": "heading", "source": "table", "text": "field_a", "level": 2}
    assert items[2] == {"kind": "text", "source": "table", "text": "body of a"}
    assert items[3] == {"kind": "heading", "source": "table", "text": "field_b", "level": 2}
    assert items[4] == {"kind": "text", "source": "table", "text": "body of b"}


def test_table_expansion_breadcrumb_includes_full_heading_chain(monkeypatch):
    document = _build_document([
        _Paragraph(_Child("p"), "L1 Title", style_name="Heading 1"),
        _Paragraph(_Child("p"), "L2 Title", style_name="Heading 2"),
        _Table(_Child("tbl"), "ignored"),
    ])

    captured = {}

    def fake_expander(**kwargs):
        captured["heading_path"] = list(kwargs["heading_path"])
        return None

    monkeypatch.setattr(word_body_iterator, "try_expand_field_table", fake_expander)

    list(word_body_iterator.iter_docx_body_items(document, {}, doc_name="Doc", model="m"))

    # Heading stack at table time = [(1, "L1 Title"), (2, "L2 Title")]
    # The doc_name is NOT prepended when the heading stack is non-empty
    # (the document's own H1 is the doc title; prepending file stem would
    # be redundant).
    assert captured["heading_path"] == ["L1 Title", "L2 Title"]


def test_table_expansion_advances_heading_stack(monkeypatch):
    document = _build_document([
        _Paragraph(_Child("p"), "L1", style_name="Heading 1"),
        _Table(_Child("tbl"), "ignored"),
        _Paragraph(_Child("p"), "after-table paragraph"),
    ])

    def fake_expander(**kwargs):
        return [
            {"kind": "heading", "source": "table", "text": "field_x", "level_offset": 1},
            {"kind": "text", "source": "table", "text": "body of x"},
        ]

    monkeypatch.setattr(word_body_iterator, "try_expand_field_table", fake_expander)

    items = list(word_body_iterator.iter_docx_body_items(document, {}, doc_name="Doc", model="m"))

    # The post-table paragraph should still be a regular text item; the
    # heading stack advancing is internal but observable via no crash and
    # correct ordering.
    assert items[-1] == {"kind": "text", "source": "paragraph", "text": "after-table paragraph"}


def test_pre_heading_table_expansion_uses_only_doc_name(monkeypatch):
    document = _build_document([_Table(_Child("tbl"), "ignored")])

    captured = {}

    def fake_expander(**kwargs):
        captured["heading_path"] = list(kwargs["heading_path"])
        return None

    monkeypatch.setattr(word_body_iterator, "try_expand_field_table", fake_expander)

    list(word_body_iterator.iter_docx_body_items(document, {}, doc_name="Doc", model="m"))

    assert captured["heading_path"] == ["Doc"]
