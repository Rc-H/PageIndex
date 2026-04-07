"""Plain-text rendering for python-docx ``Table`` objects.

Field-definition tables are no longer special-cased here — that lives in
``word_field_table_expander``, which uses an LLM gate to decide which
tables should be expanded into per-row outline nodes. Tables that are NOT
expanded by the gate fall through to plain-row rendering in this module.
"""

from __future__ import annotations

import re


def extract_table_text(table, cell_text_getter, image_cache: dict[object, str] | None = None) -> str:
    rows = []
    for row in table.rows:
        rows.append([cell_text_getter(cell, image_cache=image_cache) for cell in row.cells])

    normalized_rows = _normalize_table_rows(rows)
    if not normalized_rows:
        return ""

    return _format_plain_table_rows(normalized_rows)


def _normalize_table_rows(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return []

    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return []

    normalized = []
    for row in rows:
        padded = row + [""] * (max_cols - len(row))
        cleaned = [_clean_table_text(cell) for cell in padded]
        if any(cleaned):
            normalized.append(cleaned)
    return normalized


def _clean_table_text(text: str | None) -> str:
    if text is None:
        return ""
    cleaned = str(text).replace("\xa0", " ").replace("\t", " ")
    cleaned = re.sub(r"\r\n|\r", "\n", cleaned)
    cleaned = "\n".join(part.strip() for part in cleaned.split("\n") if part.strip())
    cleaned = re.sub(r"[ ]+", " ", cleaned)
    return cleaned.strip()


def _format_plain_table_rows(rows: list[list[str]]) -> str:
    # Keep empty cells as empty separator slots so column alignment is
    # preserved (e.g. ``["A", "", "C"]`` renders as ``"A |  | C"``).
    # ``_normalize_table_rows`` already drops fully-empty rows so we won't
    # introduce blank lines here.
    rendered_rows = []
    for row in rows:
        if not any(row):
            continue
        rendered_rows.append(" | ".join(row))
    return "\n".join(rendered_rows).strip()
