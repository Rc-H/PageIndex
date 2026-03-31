"""Detection and filtering of table-based page headers in PDF documents."""
from __future__ import annotations

import json
import re

from pageindex.core.utils.pdf.constants import (
    MIN_PAGES_FOR_HEADER,
    PAGE_HEADER_DETECTION_PROMPT,
    PAGE_HEADER_MAX_HEIGHT_RATIO,
    PAGE_HEADER_TOP_RATIO,
)
from pageindex.infrastructure.llm import get_active_llm_client
from pageindex.infrastructure.settings import resolve_model_name


def filter_page_header_tables(
    pages_tables: dict[int, list[dict]],
    model: str | None = None,
) -> dict[int, list[dict]]:
    """Remove tables identified as recurring page headers from all pages."""
    if len(pages_tables) < MIN_PAGES_FOR_HEADER:
        return pages_tables

    candidate_keys = _find_header_structure_keys(pages_tables)
    if not candidate_keys:
        return pages_tables

    confirmed_keys = _confirm_header_keys(pages_tables, candidate_keys, model)
    if not confirmed_keys:
        return pages_tables

    return _mark_tables_as_headers(pages_tables, confirmed_keys)


def _find_header_structure_keys(pages_tables: dict[int, list[dict]]) -> set[tuple]:
    """Return structure keys of tables that appear at the top of >= MIN_PAGES_FOR_HEADER pages."""
    key_page_count: dict[tuple, int] = {}

    for tables in pages_tables.values():
        seen_keys: set[tuple] = set()
        for table in tables:
            if not _is_top_of_page(table):
                continue
            key = _table_structure_key(table)
            if key not in seen_keys:
                key_page_count[key] = key_page_count.get(key, 0) + 1
                seen_keys.add(key)

    return {key for key, count in key_page_count.items() if count >= MIN_PAGES_FOR_HEADER}


def _confirm_header_keys(
    pages_tables: dict[int, list[dict]],
    candidate_keys: set[tuple],
    model: str | None,
) -> set[tuple]:
    """Ask LLM once per unique candidate structure to confirm it is a page header."""
    confirmed: set[tuple] = set()
    representative: dict[tuple, dict] = {}

    for tables in pages_tables.values():
        for table in tables:
            key = _table_structure_key(table)
            if key in candidate_keys and key not in representative:
                representative[key] = table

    for key, table in representative.items():
        if _confirm_header_with_llm(table, model):
            confirmed.add(key)

    return confirmed


def _mark_tables_as_headers(
    pages_tables: dict[int, list[dict]],
    confirmed_keys: set[tuple],
) -> dict[int, list[dict]]:
    """Mark tables whose structure key is in confirmed_keys with _is_page_header=True.

    Tables are kept in the dict so their bboxes can still be used to suppress
    overlapping image and text blocks during page rendering.
    """
    result: dict[int, list[dict]] = {}
    for page_no, tables in pages_tables.items():
        result[page_no] = []
        for t in tables:
            if _table_structure_key(t) in confirmed_keys:
                result[page_no].append({**t, "_is_page_header": True})
            else:
                result[page_no].append(t)
    return result


def _is_top_of_page(table: dict) -> bool:
    """Return True if the table is positioned near the top and is short relative to page height."""
    bbox = table.get("bbox")
    page_height = table.get("page_height")
    if not bbox or not page_height or page_height <= 0:
        return False

    table_top = bbox[1]
    table_height = bbox[3] - bbox[1]

    return (
        table_top < page_height * PAGE_HEADER_TOP_RATIO
        and table_height < page_height * PAGE_HEADER_MAX_HEIGHT_RATIO
    )


def _table_structure_key(table: dict) -> tuple:
    """Build a structure key from column count and first non-empty row content.

    Image cells are extracted as empty strings by pdfplumber. If the first row
    is entirely empty (e.g. a logo spanning the full width), we fall through to
    the next row that has at least one non-empty cell so the key stays stable
    across pages.
    """
    cells = table.get("cells") or []
    if not cells:
        return (0, ())
    for row in cells:
        normalized = tuple(" ".join(str(cell or "").split()).lower() for cell in row)
        if any(normalized):
            return (len(normalized), normalized)
    # All rows are empty (all image cells) — key on col count only
    return (len(cells[0]), ())


def _cells_to_markdown(cells: list[list[str]]) -> str:
    """Build a plain markdown table from cell data, without title or summary."""
    if not cells:
        return ""
    width = max((len(row) for row in cells), default=0)
    if width == 0:
        return ""
    padded = [row + [""] * (width - len(row)) for row in cells]

    def fmt(row):
        return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in row) + " |"

    lines = [fmt(padded[0]), "| " + " | ".join(["---"] * width) + " |"]
    lines.extend(fmt(r) for r in padded[1:])
    return "\n".join(lines)


def _confirm_header_with_llm(table: dict, model: str | None) -> bool:
    """Call LLM to confirm whether the table is a page header. Returns True if yes."""
    cells = table.get("cells") or []
    if not cells:
        return False

    # Build raw table markdown from cells only — exclude the generated title
    # and summary which can mislead the LLM into treating it as a content table.
    table_markdown = _cells_to_markdown(cells)
    prompt = PAGE_HEADER_DETECTION_PROMPT.format(table_markdown=table_markdown)
    response = _generate_text_with_llm(prompt, model=model)
    return _parse_header_response(response)


def _parse_header_response(response: str | None) -> bool:
    """Parse the LLM JSON response for header confirmation. Defaults to False on any error."""
    if not response:
        return False
    try:
        match = re.search(r"\{.*?\}", response, re.DOTALL)
        if not match:
            return False
        return bool(json.loads(match.group())["is_header"])
    except Exception:
        return False


def _generate_text_with_llm(prompt: str, model: str | None = None) -> str | None:
    try:
        client = get_active_llm_client()
    except Exception:
        return None

    try:
        return client.generate_text(model=resolve_model_name(model), prompt=prompt)
    except Exception:
        return None
