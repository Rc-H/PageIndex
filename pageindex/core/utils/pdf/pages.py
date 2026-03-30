from __future__ import annotations

from pageindex.core.utils.pdf.constants import (
    IMAGE_BLOCK_TYPE,
    PAGE_NUMBER_ARTIFACT_PATTERNS,
    TABLE_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
)
from pageindex.core.utils.pdf.images import _extract_image_markdown_from_pymupdf_block
from pageindex.core.utils.pdf.tables import _render_table_markdown


PYMUPDF_ITEM_KIND = "pymupdf"
TEXT_PYMUPDF_TYPE = 0
IMAGE_PYMUPDF_TYPE = 1
EMPTY_BBOX = [float("inf"), float("inf"), float("inf"), float("inf")]


def _extract_ordered_page_content(page, render_images: bool = False, page_tables: list[dict] | None = None) -> str:
    rendered_parts = []
    image_index = 0
    for item in _get_ordered_page_items(page, page_tables=page_tables):
        if _is_image_item(item):
            image_index += 1
        part = _render_ordered_item(
            item,
            image_index=image_index if _is_image_item(item) else None,
            render_images=render_images,
        )
        if part:
            rendered_parts.append(part)
    return "\n".join(rendered_parts).strip()


def _extract_page_blocks(
    page,
    page_no: int,
    block_no_start: int,
    doc_char_offset: int,
    encode,
    pdf_path=None,
    model: str | None = None,
    page_tables: list[dict] | None = None,
):
    rendered_items = _render_page_items(
        page,
        page_no=page_no,
        pdf_path=pdf_path,
        model=model,
        page_tables=page_tables,
    )
    page_blocks = []
    page_char_offset = 0
    next_block_no = block_no_start

    page_width = page.rect.width
    page_height = page.rect.height
    non_empty_items = [(raw_content, item) for raw_content, item in rendered_items if raw_content]
    for emitted_index, (raw_content, item) in enumerate(non_empty_items):
        normalized_text = _normalize_block_text(raw_content)
        char_count = len(normalized_text)
        metadata = _build_item_metadata(item)
        metadata["page_width"] = page_width
        metadata["page_height"] = page_height
        page_blocks.append(
            {
                "block_no": next_block_no,
                "page_no": page_no,
                "block_order_in_page": emitted_index + 1,
                "start_index": page_no,
                "end_index": page_no,
                "raw_content": raw_content,
                "normalized_text": normalized_text,
                "display_text": raw_content,
                "char_start_in_doc": doc_char_offset,
                "char_end_in_doc": doc_char_offset + char_count - 1 if char_count else doc_char_offset,
                "char_start_in_page": page_char_offset,
                "char_end_in_page": page_char_offset + char_count - 1 if char_count else page_char_offset,
                "token_count": len(encode(normalized_text)),
                "metadata": metadata,
            }
        )
        next_block_no += 1
        doc_char_offset += char_count
        page_char_offset += char_count
        if emitted_index < len(non_empty_items) - 1:
            doc_char_offset += 1
            page_char_offset += 1

    return page_blocks, next_block_no, doc_char_offset


def _render_page_items(page, page_no: int, pdf_path=None, model: str | None = None, page_tables: list[dict] | None = None):
    rendered = []
    image_index = 0
    for item in _get_ordered_page_items(page, page_tables=page_tables):
        if _is_image_item(item):
            image_index += 1
        rendered.append(
            (
                _render_ordered_item(
                    item,
                    pdf_path=pdf_path,
                    page_no=page_no,
                    image_index=image_index if _is_image_item(item) else None,
                    render_images=True,
                    model=model,
                ),
                item,
            )
        )
    return rendered


def _build_item_metadata(item: dict) -> dict:
    if item.get("kind") == TABLE_BLOCK_TYPE:
        table = item["table"]
        return {
            "type": TABLE_BLOCK_TYPE,
            "bbox": table.get("bbox"),
            "table": {
                "rows": table.get("rows"),
                "cols": table.get("cols"),
                "cells": table.get("cells", []),
                "engine": table.get("engine"),
                "title": table.get("title"),
                "summary": table.get("summary"),
            },
        }

    block = item["block"]
    metadata = {
        "type": IMAGE_BLOCK_TYPE if block.get("type") == IMAGE_PYMUPDF_TYPE else TEXT_BLOCK_TYPE,
        "bbox": block.get("bbox"),
    }
    if block.get("type") == IMAGE_PYMUPDF_TYPE and block.get("_pageindex_uploaded_image"):
        metadata["image"] = block["_pageindex_uploaded_image"]
    return metadata


def _get_ordered_page_items(page, page_tables: list[dict] | None = None):
    table_items = [
        {"kind": TABLE_BLOCK_TYPE, "bbox": table.get("bbox"), "table": table}
        for table in (page_tables or [])
    ]
    table_bboxes = [item["bbox"] for item in table_items if item.get("bbox")]
    block_items = []
    for block in _get_ordered_blocks(page):
        if block.get("type") == TEXT_PYMUPDF_TYPE and _block_overlaps_any_table(block, table_bboxes):
            continue
        block_items.append({"kind": PYMUPDF_ITEM_KIND, "bbox": block.get("bbox"), "block": block})
    return sorted(block_items + table_items, key=_ordered_item_key)


def _get_ordered_blocks(page):
    blocks = page.get_text("dict").get("blocks", [])
    return sorted(blocks, key=lambda block: _ordered_item_key({"bbox": block.get("bbox")}))


def _ordered_item_key(item: dict):
    bbox = item.get("bbox") or EMPTY_BBOX
    return (round(bbox[1], 2), round(bbox[0], 2))


def _block_overlaps_any_table(block: dict, table_bboxes: list[list[float] | tuple[float, float, float, float]]) -> bool:
    bbox = block.get("bbox")
    return any(_bbox_overlap_ratio(bbox, table_bbox) > 0.3 for table_bbox in table_bboxes if bbox and table_bbox)


def _bbox_overlap_ratio(bbox_a, bbox_b) -> float:
    if not bbox_a or not bbox_b:
        return 0.0
    ax0, ay0, ax1, ay1 = bbox_a
    bx0, by0, bx1, by1 = bbox_b
    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)
    if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
        return 0.0
    intersection = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
    area_a = max(ax1 - ax0, 0) * max(ay1 - ay0, 0)
    return 0.0 if area_a <= 0 else intersection / area_a


def _render_ordered_item(item: dict, pdf_path=None, page_no: int | None = None, image_index: int | None = None, render_images: bool = False, model: str | None = None) -> str:
    if item.get("kind") == TABLE_BLOCK_TYPE:
        return _render_table_markdown(item["table"])
    block = item["block"]
    if block.get("type") == TEXT_PYMUPDF_TYPE:
        return _extract_text_from_pymupdf_block(block)
    if block.get("type") == IMAGE_PYMUPDF_TYPE:
        return _extract_image_markdown_from_pymupdf_block(
            block,
            pdf_path=pdf_path,
            page_no=page_no,
            image_index=image_index,
            render_images=render_images,
            model=model,
        )
    return ""


def _is_image_item(item: dict) -> bool:
    return item.get("kind") == PYMUPDF_ITEM_KIND and item["block"].get("type") == IMAGE_PYMUPDF_TYPE


def _extract_text_from_pymupdf_block(block: dict) -> str:
    lines = []
    for line in block.get("lines", []):
        line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
        if line_text and not _is_page_number_artifact(line_text):
            lines.append(line_text)
    return "\n".join(lines)


def _normalize_block_text(text: str) -> str:
    return _remove_page_number_artifacts(text).strip()


def _is_page_number_artifact(text: str) -> bool:
    candidate = text.strip()
    return any(pattern.match(candidate) for pattern in PAGE_NUMBER_ARTIFACT_PATTERNS)


def _remove_page_number_artifacts(text: str | None) -> str:
    if not text:
        return ""
    lines = [line for line in text.splitlines() if not _is_page_number_artifact(line)]
    return "\n".join(lines)
