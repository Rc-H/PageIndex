"""Heading-anchored outline extraction for DOCX documents.

Consumes the materialized body item list produced by ``iter_docx_body_items``
and produces flat heading nodes for ``build_tree_from_nodes``. Each node
carries ``start_index`` and ``end_index`` equal to the section ordinal
(1-based, in body-item order) so the tree builder can propagate and bubble
up section coverage.

This module knows about heading levels and section ordinals; it knows
nothing about block dict shapes or char offsets, and it does NOT walk the
DOCX document directly — that is the body iterator's job. Walking once and
materializing the result is required because the LLM-driven field-table
expander runs inside the iterator and must fire only once per table.
"""

from __future__ import annotations

from typing import Any, Iterable

try:
    from docx import Document as WordDocument
except Exception:
    WordDocument = None


def require_word_document():
    if WordDocument is None:
        raise RuntimeError("python-docx is required for DOCX indexing")
    return WordDocument


def extract_docx_nodes(
    body_items: Iterable[dict[str, Any]],
    fallback_title: str,
) -> list[dict[str, Any]]:
    """Build flat heading nodes from a materialized body item list.

    Each returned node has ``title``, ``level``, ``line_num``, ``text``,
    ``start_index`` and ``end_index``. ``start_index == end_index`` equals
    the section ordinal (1-based, in body-item order). ``text`` contains
    the heading title followed by all body content (paragraphs and
    textualized table chunks) under that heading.

    If there are no heading items in ``body_items``, returns a single
    fallback node at section ordinal 1.
    """

    nodes: list[dict[str, Any]] = []
    current_node: dict[str, Any] | None = None
    body_buffer: list[str] = []
    section_ordinal = 0

    for line_num, item in enumerate(body_items, start=1):
        if item["kind"] == "heading":
            if current_node is not None:
                _finalize_node(current_node, body_buffer, nodes)
            section_ordinal += 1
            current_node = _start_heading_node(item, line_num, section_ordinal)
            body_buffer = [item["text"]]
        else:
            if current_node is None:
                section_ordinal += 1
                current_node = _start_fallback_node(fallback_title, section_ordinal)
                body_buffer = [fallback_title]
            body_buffer.append(item["text"])

    if current_node is not None:
        _finalize_node(current_node, body_buffer, nodes)

    if not nodes:
        return [_start_fallback_node(fallback_title, section_ordinal=1)]

    return nodes


def _start_heading_node(item: dict[str, Any], line_num: int, section_ordinal: int) -> dict[str, Any]:
    return {
        "title": item["text"],
        "line_num": line_num,
        "level": item["level"],
        "text": "",
        "start_index": section_ordinal,
        "end_index": section_ordinal,
    }


def _start_fallback_node(fallback_title: str, section_ordinal: int) -> dict[str, Any]:
    return {
        "title": fallback_title,
        "line_num": 1,
        "level": 1,
        "text": fallback_title,
        "start_index": section_ordinal,
        "end_index": section_ordinal,
    }


def _finalize_node(node: dict[str, Any], body_buffer: list[str], result: list[dict[str, Any]]) -> None:
    node["text"] = "\n".join(body_buffer).strip() or node["title"]
    result.append(node)


__all__ = ["extract_docx_nodes", "require_word_document"]
