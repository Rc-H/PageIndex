"""Unit tests for the DOCX raw block extractor."""

from __future__ import annotations

from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_block_extractor


def _heading(text, level=1):
    return {"kind": "heading", "source": "paragraph", "text": text, "level": level}


def _paragraph(text):
    return {"kind": "text", "source": "paragraph", "text": text}


def _table(text):
    return {"kind": "text", "source": "table", "text": text}


def test_empty_body_returns_empty_list():
    blocks = word_block_extractor.extract_docx_blocks([])

    assert blocks == []


def test_paragraphs_with_no_heading_share_section_one():
    blocks = word_block_extractor.extract_docx_blocks([
        _paragraph("alpha"),
        _paragraph("beta"),
    ])

    assert blocks == [
        {"section_ordinal": 1, "raw_text": "alpha", "source": "paragraph"},
        {"section_ordinal": 1, "raw_text": "beta", "source": "paragraph"},
    ]


def test_heading_starts_a_new_section():
    blocks = word_block_extractor.extract_docx_blocks([
        _heading("First"),
        _paragraph("alpha"),
        _heading("Second"),
        _paragraph("beta"),
    ])

    sections = [b["section_ordinal"] for b in blocks]
    texts = [b["raw_text"] for b in blocks]

    assert sections == [1, 1, 2, 2]
    assert texts == ["First", "alpha", "Second", "beta"]


def test_table_block_inherits_current_section():
    blocks = word_block_extractor.extract_docx_blocks([
        _heading("Top"),
        _paragraph("intro"),
        _table("c1 | c2"),
        _heading("Mid"),
        _table("d1 | d2"),
    ])

    assert blocks == [
        {"section_ordinal": 1, "raw_text": "Top", "source": "paragraph"},
        {"section_ordinal": 1, "raw_text": "intro", "source": "paragraph"},
        {"section_ordinal": 1, "raw_text": "c1 | c2", "source": "table"},
        {"section_ordinal": 2, "raw_text": "Mid", "source": "paragraph"},
        {"section_ordinal": 2, "raw_text": "d1 | d2", "source": "table"},
    ]


def test_body_content_before_first_heading_goes_into_section_one():
    blocks = word_block_extractor.extract_docx_blocks([
        _paragraph("preamble"),
        _heading("Real Title"),
        _paragraph("body"),
    ])

    assert blocks[0] == {"section_ordinal": 1, "raw_text": "preamble", "source": "paragraph"}
    assert blocks[1]["section_ordinal"] == 2  # heading creates section 2
    assert blocks[2]["section_ordinal"] == 2


def test_table_derived_headings_increment_section_ordinal():
    """When the body iterator's field-table expander promotes a row into a
    heading item, ``extract_docx_blocks`` must treat it the same as any
    other heading: increment the section ordinal."""

    blocks = word_block_extractor.extract_docx_blocks([
        _heading("Outer", level=1),
        {"kind": "heading", "source": "table", "text": "field_a", "level": 2},
        {"kind": "text", "source": "table", "text": "body of a"},
        {"kind": "heading", "source": "table", "text": "field_b", "level": 2},
        {"kind": "text", "source": "table", "text": "body of b"},
    ])

    assert [b["section_ordinal"] for b in blocks] == [1, 2, 2, 3, 3]
    assert [b["source"] for b in blocks] == ["paragraph", "table", "table", "table", "table"]
