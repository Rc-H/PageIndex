import logging
import os
import re

from pageindex.infrastructure.llm import get_active_llm_client
from pageindex.infrastructure.settings import resolve_model_name

from pageindex.core.utils.pdf.constants import (
    CAMELOT_ENGINE_NAME,
    DEFAULT_TABLE_TITLE,
    MAX_TABLE_TITLE_LENGTH,
    PDFPLUMBER_ENGINE_NAME,
    TABLE_SUMMARY_PROMPT_TEMPLATE,
    TABLE_TITLE_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import camelot
except ImportError:
    camelot = None


def _extract_tables_by_page(pdf_path, model: str | None = None) -> dict[int, list[dict]]:
    pdfplumber_tables = _extract_tables_with_pdfplumber(pdf_path, model=model)
    camelot_tables = _extract_missing_tables_with_camelot(
        pdf_path,
        extracted_pages=set(pdfplumber_tables),
        model=model,
    )

    page_numbers = set(pdfplumber_tables) | set(camelot_tables)
    merged: dict[int, list[dict]] = {}
    for page_no in sorted(page_numbers):
        if pdfplumber_tables.get(page_no):
            merged[page_no] = pdfplumber_tables[page_no]
        elif camelot_tables.get(page_no):
            merged[page_no] = camelot_tables[page_no]
            logger.info("camelot table fallback used", extra={"page_no": page_no, "table_count": len(merged[page_no])})
    return merged


def _extract_missing_tables_with_camelot(
    pdf_path,
    extracted_pages: set[int],
    model: str | None = None,
) -> dict[int, list[dict]]:
    page_numbers = _get_pdf_page_numbers(pdf_path)
    if page_numbers is None:
        if extracted_pages:
            return {}
        return _extract_tables_with_camelot(pdf_path, model=model)

    missing_pages = [page_no for page_no in page_numbers if page_no not in extracted_pages]
    if not missing_pages:
        return {}
    return _extract_camelot_tables(pdf_path, page_numbers=missing_pages, model=model)


def _extract_tables_with_pdfplumber(pdf_path, model: str | None = None) -> dict[int, list[dict]]:
    del model
    if pdfplumber is None:
        return {}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            result: dict[int, list[dict]] = {}
            for page_no, page in enumerate(pdf.pages, start=1):
                tables = _extract_pdfplumber_page_tables(page, page_no=page_no)
                if tables:
                    result[page_no] = tables
            return result
    except Exception as exc:
        logger.warning("pdfplumber table extraction failed: %s", exc)
        return {}


def _extract_pdfplumber_page_tables(page, page_no: int) -> list[dict]:
    tables = []
    finder = getattr(page, "find_tables", None)
    settings = _default_pdfplumber_table_settings()
    if callable(finder):
        for table_index, table in enumerate(finder(table_settings=settings), start=1):
            raw_cells = table.extract() if hasattr(table, "extract") else None
            payload = _build_table_payload(
                cells=_normalize_table(raw_cells or []),
                bbox=_normalize_bbox(getattr(table, "bbox", None)),
                engine=PDFPLUMBER_ENGINE_NAME,
                page_no=page_no,
                table_index=table_index,
            )
            if payload:
                tables.append(payload)
        return tables

    raw_tables = page.extract_tables(settings)
    for table_index, raw_cells in enumerate(raw_tables or [], start=1):
        payload = _build_table_payload(
            cells=_normalize_table(raw_cells),
            bbox=None,
            engine=PDFPLUMBER_ENGINE_NAME,
            page_no=page_no,
            table_index=table_index,
        )
        if payload:
            tables.append(payload)
    return tables


def _extract_tables_with_camelot(pdf_path, model: str | None = None) -> dict[int, list[dict]]:
    return _extract_camelot_tables(pdf_path, page_numbers=None, model=model)


def _extract_camelot_tables(pdf_path, page_numbers: list[int] | None = None, model: str | None = None) -> dict[int, list[dict]]:
    del model
    if camelot is None or not isinstance(pdf_path, (str, os.PathLike)):
        return {}

    page_selector = _build_camelot_page_selector(page_numbers)
    result: dict[int, list[dict]] = {}
    for flavor in ("lattice", "stream"):
        try:
            tables = camelot.read_pdf(os.fspath(pdf_path), pages=page_selector, flavor=flavor)
        except Exception:
            continue

        for table in tables:
            page_no = int(getattr(table, "page", "0") or 0)
            if page_no <= 0 or result.get(page_no):
                continue
            dataframe = getattr(table, "df", None)
            raw_cells = dataframe.values.tolist() if dataframe is not None else []
            payload = _build_table_payload(
                cells=_normalize_table(raw_cells),
                bbox=_normalize_bbox(getattr(table, "_bbox", None)),
                engine=CAMELOT_ENGINE_NAME,
                page_no=page_no,
                table_index=len(result.get(page_no, [])) + 1,
            )
            if payload:
                result.setdefault(page_no, []).append(payload)
    return result


def _build_camelot_page_selector(page_numbers: list[int] | None) -> str:
    if not page_numbers:
        return "all"
    return ",".join(str(page_no) for page_no in page_numbers)


def _get_pdf_page_numbers(pdf_path) -> list[int] | None:
    if pdfplumber is None or not isinstance(pdf_path, (str, os.PathLike)):
        return None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return list(range(1, len(pdf.pages) + 1))
    except Exception:
        return None


def _default_pdfplumber_table_settings() -> dict[str, object]:
    return {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "edge_min_length": 3,
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
    }


def _normalize_bbox(bbox):
    if not bbox or len(bbox) != 4:
        return None
    return [float(value) for value in bbox]


def _build_table_payload(cells: list[list[str]], bbox, engine: str, page_no: int, table_index: int) -> dict | None:
    if not cells:
        return None
    table_markdown = _table_to_markdown(cells)
    title = _generate_table_title(table_markdown, fallback_index=table_index)
    summary = _generate_table_summary(table_markdown)
    return {
        "bbox": bbox,
        "cells": cells,
        "rows": len(cells),
        "cols": max((len(row) for row in cells), default=0),
        "engine": engine,
        "title": title,
        "summary": summary,
        "page_no": page_no,
        "table_index": table_index,
        "markdown": _render_table_block(table_markdown, title=title, summary=summary),
    }


def _normalize_table(raw_table: list[list]) -> list[list[str]]:
    if not raw_table:
        return []

    rows = [list(row or []) for row in raw_table]
    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return []

    normalized = []
    for index, row in enumerate(rows):
        padded = row + [None] * (max_cols - len(row))
        cleaned = [_clean_table_cell(cell) for cell in padded]
        if any(cleaned) or index == 0:
            normalized.append(cleaned)

    if not normalized:
        return []

    if not any(normalized[0]):
        normalized[0] = [f"列{i + 1}" for i in range(len(normalized[0]))]
    return normalized


def _clean_table_cell(cell) -> str:
    if cell is None:
        return ""
    text = str(cell).replace("\xa0", " ").replace("\t", " ")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = "\n".join(part.strip() for part in text.split("\n") if part.strip())
    text = re.sub(r"[ ]+", " ", text)
    return text.strip()


def _table_to_markdown(cells: list[list[str]]) -> str:
    if not cells:
        return ""

    width = max((len(row) for row in cells), default=0)
    if width == 0:
        return ""

    padded_rows = [row + [""] * (width - len(row)) for row in cells]
    header = padded_rows[0]
    body = padded_rows[1:]

    def format_row(row):
        escaped = [cell.replace("|", "\\|").replace("\n", " ") for cell in row]
        return "| " + " | ".join(escaped) + " |"

    separator = "| " + " | ".join(["---"] * width) + " |"
    lines = [format_row(header), separator]
    lines.extend(format_row(row) for row in body)
    return "\n".join(lines)


def _render_table_block(table_markdown: str, title: str, summary: str | None = None) -> str:
    if not table_markdown:
        return ""
    parts = [f"**表格：{title}**", "", table_markdown]
    if summary:
        parts.extend(["", f"表格摘要：{summary}"])
    return "\n".join(parts)


def _render_table_markdown(table: dict) -> str:
    return table.get("markdown", "")


def _generate_table_title(table_markdown: str, model: str | None = None, fallback_index: int | None = None) -> str:
    prompt = TABLE_TITLE_PROMPT_TEMPLATE.format(table_markdown=table_markdown)
    generated = _generate_text_with_llm(prompt, model=model)
    normalized = _normalize_table_title(generated)
    if normalized != DEFAULT_TABLE_TITLE:
        return normalized
    return _default_table_title(fallback_index)


def _generate_table_summary(table_markdown: str, model: str | None = None) -> str | None:
    prompt = TABLE_SUMMARY_PROMPT_TEMPLATE.format(table_markdown=table_markdown)
    generated = _generate_text_with_llm(prompt, model=model)
    return _normalize_table_summary(generated)


def _generate_text_with_llm(prompt: str, model: str | None = None) -> str | None:
    try:
        client = get_active_llm_client()
    except Exception:
        return None

    try:
        return client.generate_text(model=resolve_model_name(model), prompt=prompt)
    except Exception:
        return None


def _normalize_table_title(value: str | None) -> str:
    if not value:
        return DEFAULT_TABLE_TITLE
    first_line = value.strip().splitlines()[0].strip()
    first_line = re.sub(r"^[\"'“”‘’《〈【\[\(]+", "", first_line)
    first_line = re.sub(r"[\"'“”‘’》〉】\]\)]+$", "", first_line)
    first_line = re.sub(r"[。！!？?,，:：;；、]", "", first_line)
    first_line = " ".join(first_line.split())
    if not first_line:
        return DEFAULT_TABLE_TITLE
    if len(first_line) > MAX_TABLE_TITLE_LENGTH:
        first_line = first_line[:MAX_TABLE_TITLE_LENGTH].rstrip()
    return first_line or DEFAULT_TABLE_TITLE


def _normalize_table_summary(value: str | None) -> str | None:
    if not value:
        return None
    summary = " ".join(part.strip() for part in value.strip().splitlines() if part.strip())
    summary = re.sub(r"\s+", " ", summary)
    return summary or None


def _default_table_title(table_index: int | None = None) -> str:
    if table_index and table_index > 1:
        return f"{DEFAULT_TABLE_TITLE} {table_index}"
    return DEFAULT_TABLE_TITLE
