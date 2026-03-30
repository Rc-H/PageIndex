from __future__ import annotations

from typing import Any


def build_index_result(
    doc_name: str,
    structure: list[dict[str, Any]],
    doc_description: str | None = None,
    page_count: int | None = None,
    char_count: int | None = None,
    token_count: int | None = None,
    extract: dict[str, Any] | None = None,
    content_images: list[dict[str, Any]] | None = None,
    location_unit: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"doc_name": doc_name, "structure": structure}
    if doc_description is not None:
        result["doc_description"] = doc_description
    if page_count is not None:
        result["page_count"] = page_count
    if char_count is not None:
        result["char_count"] = char_count
    if token_count is not None:
        result["token_count"] = token_count
    if extract is not None:
        result["extract"] = extract
    if content_images is not None:
        result["content_images"] = content_images
    if location_unit is not None:
        result["location_unit"] = location_unit
    return result
