from __future__ import annotations

import re


def extract_table_text(table, cell_text_getter, image_cache: dict[object, str] | None = None) -> str:
    rows = []
    for row in table.rows:
        rows.append([cell_text_getter(cell, image_cache=image_cache) for cell in row.cells])

    normalized_rows = _normalize_table_rows(rows)
    if not normalized_rows:
        return ""

    structured_text = _format_field_definition_table(normalized_rows)
    if structured_text:
        return structured_text
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


def _format_field_definition_table(rows: list[list[str]]) -> str | None:
    if len(rows) < 2:
        return None

    header = [_normalize_header_name(cell) for cell in rows[0]]
    category_index = _find_header_index(header, {"分类"})
    field_index = _find_header_index(header, {"字段名称", "字段"})
    type_index = _find_header_index(header, {"类型"})
    desc_index = _find_header_index(header, {"说明", "描述"})

    if field_index is None or type_index is None or desc_index is None:
        return None

    current_category = None
    lines: list[str] = []
    for row in rows[1:]:
        category = _safe_row_value(row, category_index).strip() if category_index is not None else ""
        field_name = _safe_row_value(row, field_index).strip()
        field_type = _safe_row_value(row, type_index).strip()
        desc = _split_field_description(_safe_row_value(row, desc_index))

        if not field_name:
            continue

        if category:
            if lines and lines[-1] != "":
                lines.append("")
            if category != current_category:
                lines.append(f"## {category}")
                lines.append("")
            current_category = category

        lines.append(f"### {field_name}")
        lines.append(f"- 类型：{field_type}")
        if not desc:
            lines.append("- 说明：")
        elif len(desc) == 1:
            lines.append(f"- 说明：{desc[0]}")
        else:
            lines.append("- 说明：")
            for item in desc:
                lines.append(f"  - {item}")
        lines.append("")

    formatted = "\n".join(lines).strip()
    return formatted or None


def _normalize_header_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _find_header_index(header: list[str], candidates: set[str]) -> int | None:
    for index, value in enumerate(header):
        if value in candidates:
            return index
    return None


def _safe_row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def _split_field_description(text: str) -> list[str]:
    cleaned = _clean_table_text(text)
    if not cleaned:
        return []
    parts = [part.strip() for part in cleaned.split("\n") if part.strip()]
    merged = "\n".join(parts)
    merged = merged.replace("；", "；\n").replace("。", "。\n")
    return [part.strip() for part in merged.split("\n") if part.strip()]


def _format_plain_table_rows(rows: list[list[str]]) -> str:
    rendered_rows = []
    for row in rows:
        rendered_row = " | ".join(cell for cell in row if cell)
        if rendered_row:
            rendered_rows.append(rendered_row)
    return "\n".join(rendered_rows).strip()
