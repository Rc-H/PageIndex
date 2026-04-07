"""Paragraph-level raw block extraction for DOCX documents.

Consumes the materialized body item list produced by ``iter_docx_body_items``
and produces a flat ordered list of raw blocks. Each top-level paragraph
(including heading paragraphs) and each top-level textualized table chunk
becomes one raw block, tagged with the section ordinal of the heading it
belongs to.

Headings produce their own block whose ``raw_text`` is the heading title.
This is intentional: the heading text is real content the AI needs to see
when reconstructing the full document.

Knows about section ordinals; knows nothing about char offsets, token
counts, or node ids — those are computed by ``word_block_finalizer``. Does
NOT walk the DOCX document directly; consumes the iterator's output via a
shared list so the LLM-driven field-table expander runs only once per
table.
"""

from __future__ import annotations

from typing import Any, Iterable


def extract_docx_blocks(body_items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return raw blocks ``[{section_ordinal, raw_text, source}]`` in body order.

    ``section_ordinal`` is 1-based and increments whenever a heading item
    is encountered. Body content that appears before any heading is
    assigned section ordinal 1 (matching ``extract_docx_nodes``'s fallback
    path). Empty / whitespace-only items are skipped at the iterator
    level.
    """

    blocks: list[dict[str, Any]] = []
    section_ordinal = 0
    fallback_used = False

    for item in body_items:
        if item["kind"] == "heading":
            section_ordinal += 1
        elif section_ordinal == 0 and not fallback_used:
            section_ordinal = 1
            fallback_used = True

        blocks.append({
            "section_ordinal": section_ordinal if section_ordinal > 0 else 1,
            "raw_text": item["text"],
            "source": item["source"],
        })

    return blocks


__all__ = ["extract_docx_blocks"]
