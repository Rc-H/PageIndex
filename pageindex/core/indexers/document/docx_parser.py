from __future__ import annotations

import re
from typing import Any

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
    line_num = 0

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
    for child in document.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            paragraph = next((p for p in document.paragraphs if p._p is child), None)
            if paragraph is None:
                continue
            text = paragraph.text.strip()
            if not text:
                continue
            heading_level = _get_heading_level(paragraph.style.name if paragraph.style else "")
            if heading_level is not None:
                yield {"kind": "heading", "level": heading_level, "text": text}
            else:
                yield {"kind": "text", "text": text}
        elif tag == "tbl":
            table = next((t for t in document.tables if t._tbl is child), None)
            if table is None:
                continue
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cell for cell in cells if cell))
            text = "\n".join(row for row in rows if row).strip()
            if text:
                yield {"kind": "text", "text": text}


def _get_heading_level(style_name: str) -> int | None:
    match = re.search(r"heading\s+(\d+)", style_name or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None
