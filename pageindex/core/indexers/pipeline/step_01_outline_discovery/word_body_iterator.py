"""Top-level body walker for DOCX documents.

Walks ``document.element.body.iterchildren()`` and yields one normalized item
per top-level ``<w:p>`` and ``<w:tbl>``. Tables nested inside table cells are
NOT yielded here — they are recovered by ``extract_table_cell_text``'s
recursive renderer when the outer table is processed.

Field-definition style tables can be **expanded** into per-row heading +
body items by an LLM gate (``word_field_table_expander``). When expansion
fires, the iterator yields a heading item per row instead of a single
``source="table"`` text item, so each row becomes its own outline section.

This module knows nothing about block dict shapes; it is consumed by both
``word_outline`` (heading hierarchy) and ``word_block_extractor``
(paragraph-level raw blocks).
"""

from __future__ import annotations

from typing import Iterator

from pageindex.core.indexers.pipeline.step_01_outline_discovery.word_field_table_expander import (
    try_expand_field_table,
)
from pageindex.core.indexers.pipeline.step_01_outline_discovery.word_paragraphs import (
    extract_paragraph_text,
    extract_table_cell_text,
    get_heading_level,
)
from pageindex.core.indexers.pipeline.step_01_outline_discovery.word_tables import (
    extract_table_text,
)


PARAGRAPH_SOURCE = "paragraph"
TABLE_SOURCE = "table"

HEADING_KIND = "heading"
TEXT_KIND = "text"


def iter_docx_body_items(
    document,
    image_cache: dict[object, str],
    *,
    doc_name: str | None = None,
    model: str | None = None,
) -> Iterator[dict]:
    """Yield ``{kind, source, text, level?}`` for each top-level body item.

    - ``kind`` is ``"heading"`` for paragraphs whose style maps to a heading
      level, AND for table rows that the field-table expander promotes into
      their own section. Otherwise ``"text"``.
    - ``source`` is ``"paragraph"`` or ``"table"`` so consumers can tell apart
      a textualized table from a regular paragraph even though both share
      ``kind="text"``.
    - ``level`` is only present when ``kind == "heading"``. For Word
      headings it comes from the paragraph style; for table-derived
      headings it is computed from the surrounding heading hierarchy.

    Empty / whitespace-only items are skipped.

    ``doc_name`` and ``model`` are used by the field-table expander to
    build per-row breadcrumbs and to call the LLM gate. When ``model`` is
    None the expander is skipped (tables go through plain rendering).
    """

    heading_stack: list[tuple[int, str]] = []  # (level, title), parent first

    for child in document.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield from _yield_paragraph_items(document, child, image_cache, heading_stack)
        elif tag == "tbl":
            yield from _yield_table_items(
                document, child, image_cache, heading_stack, doc_name=doc_name, model=model,
            )


def _yield_paragraph_items(document, child, image_cache, heading_stack):
    paragraph = next((p for p in document.paragraphs if p._p is child), None)
    if paragraph is None:
        return
    text = extract_paragraph_text(paragraph, image_cache=image_cache).strip()
    if not text:
        return
    heading_level = get_heading_level(paragraph.style.name if paragraph.style else "")
    if heading_level is not None:
        _push_heading(heading_stack, heading_level, text)
        yield {
            "kind": HEADING_KIND,
            "source": PARAGRAPH_SOURCE,
            "text": text,
            "level": heading_level,
        }
    else:
        yield {
            "kind": TEXT_KIND,
            "source": PARAGRAPH_SOURCE,
            "text": text,
        }


def _yield_table_items(document, child, image_cache, heading_stack, *, doc_name, model):
    table = next((t for t in document.tables if t._tbl is child), None)
    if table is None:
        return

    if model:
        heading_path = _current_heading_path(heading_stack, doc_name)
        expanded = try_expand_field_table(
            table=table,
            cell_text_getter=lambda cell, image_cache: extract_table_cell_text(
                cell,
                image_cache=image_cache,
                nested_table_renderer=render_table_text,
            ),
            image_cache=image_cache,
            heading_path=heading_path,
            model=model,
        )
        if expanded is not None:
            yield from _materialize_expanded_items(expanded, heading_stack)
            return

    text = render_table_text(table, image_cache=image_cache)
    if text:
        yield {
            "kind": TEXT_KIND,
            "source": TABLE_SOURCE,
            "text": text,
        }


def _materialize_expanded_items(expanded_items, heading_stack):
    """Convert the expander's relative-level items into iterator output.

    The expander emits headings with ``level_offset`` (relative to the
    surrounding section). Here we resolve absolute levels using the current
    ``heading_stack`` and update the stack so that subsequent body items
    nest correctly under the table-derived sections.
    """

    base_level = heading_stack[-1][0] if heading_stack else 0
    for item in expanded_items:
        if item["kind"] == HEADING_KIND:
            absolute_level = base_level + item.get("level_offset", 1)
            text = item["text"]
            _push_heading(heading_stack, absolute_level, text)
            yield {
                "kind": HEADING_KIND,
                "source": item.get("source", TABLE_SOURCE),
                "text": text,
                "level": absolute_level,
            }
        else:
            yield {
                "kind": item["kind"],
                "source": item.get("source", TABLE_SOURCE),
                "text": item["text"],
            }


def _push_heading(heading_stack: list[tuple[int, str]], level: int, title: str) -> None:
    while heading_stack and heading_stack[-1][0] >= level:
        heading_stack.pop()
    heading_stack.append((level, title))


def _current_heading_path(heading_stack: list[tuple[int, str]], doc_name: str | None) -> list[str]:
    # The breadcrumb is built from the Word heading hierarchy. We only fall
    # back to ``doc_name`` when there is no surrounding heading at all —
    # otherwise the document's own H1 is the doc title and prepending the
    # file stem would duplicate it (and file stems are usually not
    # semantically meaningful anyway).
    path = [title for _, title in heading_stack]
    if not path and doc_name:
        return [doc_name]
    return path


def render_table_text(table, image_cache: dict[object, str] | None = None) -> str:
    """Render a python-docx ``Table`` to plain text, recursively handling
    nested tables inside cells.

    Lives here (rather than in ``word_tables``) so that the recursive cell
    renderer can be defined as a closure that re-enters this same function
    without creating an import cycle with ``extract_table_cell_text``.
    """

    cache = image_cache if image_cache is not None else {}

    def cell_renderer(cell, image_cache):
        return extract_table_cell_text(
            cell,
            image_cache=image_cache,
            nested_table_renderer=render_table_text,
        )

    return extract_table_text(table, cell_renderer, image_cache=cache)


__all__ = [
    "HEADING_KIND",
    "PARAGRAPH_SOURCE",
    "TABLE_SOURCE",
    "TEXT_KIND",
    "iter_docx_body_items",
    "render_table_text",
]
