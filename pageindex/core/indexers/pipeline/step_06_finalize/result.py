from __future__ import annotations

from typing import Any


def build_index_result(doc_name: str, structure: list[dict[str, Any]], doc_description: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"doc_name": doc_name, "structure": structure}
    if doc_description is not None:
        result["doc_description"] = doc_description
    return result
