from __future__ import annotations

from typing import Any

from pageindex.core.indexers.pipeline.step_01_outline_discovery.word_paragraphs import (
    extract_paragraph_text,
    extract_table_cell_text,
    get_heading_level,
)
from pageindex.core.indexers.pipeline.step_01_outline_discovery.word_tables import extract_table_text

try:
    from docx import Document as WordDocument
except Exception:
    WordDocument = None


def require_word_document():
    if WordDocument is None:
        raise RuntimeError("python-docx is required for DOCX indexing")
    return WordDocument


def extract_docx_nodes(document, fallback_title: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    current_node: dict[str, Any] | None = None
    body_buffer: list[str] = []

    for line_num, block in enumerate(_iter_docx_blocks(document), start=1):
        if block["kind"] == "heading":
            current_node = _finalize_and_start_heading(nodes, current_node, body_buffer, block, line_num)
            body_buffer = [block["text"]]
        else:
            if current_node is None:
                current_node = {"title": fallback_title, "line_num": 1, "level": 1, "text": ""}
                body_buffer = [fallback_title]
            if block["text"]:
                body_buffer.append(block["text"])

    if current_node is not None:
        current_node["text"] = "\n".join(body_buffer).strip() or current_node["title"]
        nodes.append(current_node)

    if not nodes:
        return [{"title": fallback_title, "line_num": 1, "level": 1, "text": fallback_title}]
    return nodes


def _finalize_and_start_heading(nodes, current_node, body_buffer, block, line_num):
    if current_node is not None:
        current_node["text"] = "\n".join(body_buffer).strip() or current_node["title"]
        nodes.append(current_node)
    return {
        "title": block["text"],
        "line_num": line_num,
        "level": block["level"],
        "text": "",
    }


def _iter_docx_blocks(document):
    image_cache: dict[object, str] = {}
    for child in document.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            paragraph = next((p for p in document.paragraphs if p._p is child), None)
            if paragraph is None:
                continue
            text = extract_paragraph_text(paragraph, image_cache=image_cache).strip()
            if not text:
                continue
            heading_level = get_heading_level(paragraph.style.name if paragraph.style else "")
            if heading_level is not None:
                yield {"kind": "heading", "level": heading_level, "text": text}
            else:
                yield {"kind": "text", "text": text}
        elif tag == "tbl":
            table = next((t for t in document.tables if t._tbl is child), None)
            if table is None:
                continue
            text = _extract_table_text(table, image_cache=image_cache)
            if text:
                yield {"kind": "text", "text": text}


def _extract_table_cell_text(cell, image_cache: dict[object, str] | None = None) -> str:
    return extract_table_cell_text(cell, image_cache=image_cache)


def _extract_table_text(table, image_cache: dict[object, str] | None = None) -> str:
    return extract_table_text(table, _extract_table_cell_text, image_cache=image_cache)


__all__ = ["extract_docx_nodes", "require_word_document"]
