"""LLM-driven expansion of "field-definition style" tables.

A `<w:tbl>` may be a list of distinct, retrievable entities (field
definitions, API parameters, glossary entries, etc.) where each row is
worth being its own searchable section. For those tables we want each row
to become a heading node in the outline so embedding hits the right field
directly.

This module asks the LLM whether the current table should be expanded and,
if so, which column holds each row's NAME. On a positive decision it emits
a flat list of body items (one heading + one body text per row) ready to
be yielded by ``iter_docx_body_items``. On any failure (LLM error,
malformed JSON, schema validation, table too small) it returns ``None`` and
the caller falls back to plain table rendering.

The body text for each field carries:

1. A breadcrumb of the surrounding heading hierarchy ("path: Doc > Sec > ...")
   so embedding sees the document context, not just the field name.
2. Every column's "header: value" written out flat (not as ## / ### markdown),
   so embedding has the full field definition without abbreviation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.utils.llm_caller import call_llm


logger = logging.getLogger(__name__)


# Tables smaller than this are not worth asking the LLM about — there's
# nothing meaningful to retrieve and the gate call would dominate cost.
MIN_DATA_ROWS_FOR_EXPANSION = 2

# Cap the sample rows we send to the LLM gate so the prompt stays small.
MAX_SAMPLE_ROWS_FOR_GATE = 5

PATH_SEPARATOR = " > "


def try_expand_field_table(
    table,
    cell_text_getter,
    image_cache: dict[object, str] | None,
    heading_path: list[str],
    model: str | None,
) -> list[dict[str, Any]] | None:
    """Decide via LLM whether ``table`` should be expanded into per-row nodes.

    Returns a flat list of body items on success::

        [
            {"kind": "heading", "source": "table", "text": "<row name>", "level_offset": 1},
            {"kind": "text", "source": "table", "text": "<full row body>"},
            ...
        ]

    The ``level_offset`` on heading items is relative to the surrounding
    Word heading level — the body iterator owns the absolute level
    computation since it knows the current outer heading level.

    Returns ``None`` for any failure path: LLM error, malformed JSON, schema
    violation, table too small, fewer than two columns, etc. The caller
    must fall back to plain rendering.
    """

    rows = _read_table_rows(table, cell_text_getter, image_cache)
    if rows is None:
        return None

    headers, data_rows = _split_header_and_data(rows)
    if headers is None or len(data_rows) < MIN_DATA_ROWS_FOR_EXPANSION or len(headers) < 2:
        return None

    decision = _ask_llm_for_decision(headers, data_rows, model)
    if decision is None:
        return None

    should_expand, name_column_index = decision
    if not should_expand:
        return None

    return _build_expanded_items(headers, data_rows, name_column_index, heading_path)


def _read_table_rows(table, cell_text_getter, image_cache) -> list[list[str]] | None:
    try:
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [cell_text_getter(cell, image_cache=image_cache) or "" for cell in row.cells]
            rows.append([cell.strip() for cell in cells])
        return rows
    except Exception as exc:  # noqa: BLE001 — defensive: any python-docx weirdness should not crash indexing
        logger.warning("Field table expander failed to read table rows: %s", exc)
        return None


def _split_header_and_data(rows: list[list[str]]) -> tuple[list[str] | None, list[list[str]]]:
    if not rows:
        return None, []

    header_row = rows[0]
    if not any(header_row):
        return None, []

    data_rows = [row for row in rows[1:] if any(row)]
    return header_row, data_rows


def _ask_llm_for_decision(
    headers: list[str],
    data_rows: list[list[str]],
    model: str | None,
) -> tuple[bool, int] | None:
    sample = data_rows[:MAX_SAMPLE_ROWS_FOR_GATE]
    prompt = load_prompt(
        "step_01_outline_discovery/prompts/table_expansion_decision.txt",
        headers=json.dumps(headers, ensure_ascii=False),
        sample_rows=json.dumps(sample, ensure_ascii=False),
        sample_count=len(sample),
    )

    try:
        raw = call_llm(model=model, prompt=prompt, json_response=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Field table expander LLM call failed, falling back to plain text: %s", exc)
        return None

    if not raw or raw == "Error":
        logger.warning("Field table expander LLM returned empty/error response, falling back to plain text")
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Field table expander LLM returned invalid JSON, falling back to plain text: error=%s raw=%s",
            exc, raw[:200],
        )
        return None

    return _validate_decision_payload(payload, len(headers))


def _validate_decision_payload(payload: Any, header_count: int) -> tuple[bool, int] | None:
    if not isinstance(payload, dict):
        logger.warning("Field table expander schema invalid: not an object, payload=%s", payload)
        return None

    should_expand = payload.get("should_expand")
    if not isinstance(should_expand, bool):
        logger.warning(
            "Field table expander schema invalid: should_expand missing or wrong type, payload=%s",
            payload,
        )
        return None

    if not should_expand:
        return False, 0

    name_column_index = payload.get("name_column_index")
    if not isinstance(name_column_index, int) or name_column_index < 0 or name_column_index >= header_count:
        # Q3 fallback: name column out of range / wrong type → use the first column.
        logger.warning(
            "Field table expander LLM gave invalid name_column_index=%s; falling back to column 0",
            name_column_index,
        )
        return True, 0

    return True, name_column_index


def _build_expanded_items(
    headers: list[str],
    data_rows: list[list[str]],
    name_column_index: int,
    heading_path: list[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in data_rows:
        name = row[name_column_index].strip() if name_column_index < len(row) else ""
        if not name:
            # Skip rows without a recognizable name — there's nothing to title
            # the resulting node with, and an empty heading would corrupt the
            # outline.
            continue

        body_text = _format_row_body(headers, row, heading_path, name)

        items.append({
            "kind": "heading",
            "source": "table",
            "text": name,
            "level_offset": 1,
        })
        items.append({
            "kind": "text",
            "source": "table",
            "text": body_text,
        })

    return items


def _format_row_body(
    headers: list[str],
    row: list[str],
    heading_path: list[str],
    name: str,
) -> str:
    full_path = list(heading_path) + [name]
    lines = ["路径: " + PATH_SEPARATOR.join(full_path)]
    for index, header in enumerate(headers):
        value = row[index].strip() if index < len(row) else ""
        if not header and not value:
            continue
        label = header or f"col_{index}"
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


__all__ = [
    "MAX_SAMPLE_ROWS_FOR_GATE",
    "MIN_DATA_ROWS_FOR_EXPANSION",
    "PATH_SEPARATOR",
    "try_expand_field_table",
]
