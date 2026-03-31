import pytest

from pageindex.core.utils.pdf import header_detection as hd


def _make_table(bbox, page_height, cells=None, markdown="**表格：页眉**\n\n| 公司 | 文档编号 |\n| --- | --- |\n| 志特 | DOC-001 |"):
    return {
        "bbox": bbox,
        "page_height": page_height,
        "cells": cells or [["公司", "文档编号"], ["志特", "DOC-001"]],
        "rows": 2,
        "cols": 2,
        "markdown": markdown,
    }


# ── _parse_header_response ───────────────────────────────────────────────────

def test_parse_header_response_returns_true_for_is_header_true():
    assert hd._parse_header_response('{"is_header": true}') is True

def test_parse_header_response_returns_false_for_is_header_false():
    assert hd._parse_header_response('{"is_header": false}') is False

def test_parse_header_response_extracts_json_from_surrounding_text():
    assert hd._parse_header_response('好的，结果如下：{"is_header": true}') is True

def test_parse_header_response_returns_false_for_none():
    assert hd._parse_header_response(None) is False

def test_parse_header_response_returns_false_for_malformed_json():
    assert hd._parse_header_response("是") is False


# ── _is_top_of_page ──────────────────────────────────────────────────────────

def test_is_top_of_page_returns_true_when_table_near_top():
    table = _make_table(bbox=[0, 5, 500, 50], page_height=841)
    assert hd._is_top_of_page(table) is True


def test_is_top_of_page_returns_false_when_table_in_middle():
    table = _make_table(bbox=[0, 400, 500, 450], page_height=841)
    assert hd._is_top_of_page(table) is False


def test_is_top_of_page_returns_false_when_table_too_tall():
    # Near top but height exceeds ratio (200/841 > 0.15)
    table = _make_table(bbox=[0, 5, 500, 205], page_height=841)
    assert hd._is_top_of_page(table) is False


def test_is_top_of_page_returns_false_when_no_page_height():
    table = _make_table(bbox=[0, 5, 500, 50], page_height=None)
    assert hd._is_top_of_page(table) is False


def test_is_top_of_page_returns_false_when_no_bbox():
    table = {"bbox": None, "page_height": 841, "cells": [["A"]], "rows": 1, "cols": 1, "markdown": ""}
    assert hd._is_top_of_page(table) is False


# ── _table_structure_key ─────────────────────────────────────────────────────

def test_table_structure_key_uses_first_row_and_col_count():
    table = _make_table(bbox=[0, 5, 500, 50], page_height=841,
                        cells=[["公司", "文档编号"], ["志特", "DOC-001"]])
    assert hd._table_structure_key(table) == (2, ("公司", "文档编号"))


def test_table_structure_key_ignores_data_rows():
    t1 = _make_table(bbox=[0, 5, 500, 50], page_height=841,
                     cells=[["公司", "文档编号"], ["志特", "DOC-001"]])
    t2 = _make_table(bbox=[0, 5, 500, 50], page_height=841,
                     cells=[["公司", "文档编号"], ["另一家", "DOC-002"]])
    assert hd._table_structure_key(t1) == hd._table_structure_key(t2)


def test_table_structure_key_empty_cells():
    table = {"bbox": [0, 5, 500, 50], "page_height": 841, "cells": [], "markdown": ""}
    assert hd._table_structure_key(table) == (0, ())


def test_table_structure_key_skips_all_empty_first_row_and_uses_next():
    # First row is all images (empty), second row has text
    table = _make_table(bbox=[0, 5, 500, 50], page_height=841,
                        cells=[["", ""], ["公司", "文档编号"], ["志特", "DOC-001"]])
    assert hd._table_structure_key(table) == (2, ("公司", "文档编号"))


def test_table_structure_key_all_image_cells_falls_back_to_col_count():
    table = _make_table(bbox=[0, 5, 500, 50], page_height=841,
                        cells=[["", ""], ["", ""]])
    assert hd._table_structure_key(table) == (2, ())


# ── _find_header_structure_keys ──────────────────────────────────────────────

def test_find_header_structure_keys_returns_key_appearing_on_multiple_pages():
    header = _make_table(bbox=[0, 5, 500, 50], page_height=841)
    pages_tables = {
        1: [header],
        2: [header],
        3: [header],
    }
    keys = hd._find_header_structure_keys(pages_tables)
    assert hd._table_structure_key(header) in keys


def test_find_header_structure_keys_ignores_table_appearing_once():
    header = _make_table(bbox=[0, 5, 500, 50], page_height=841)
    pages_tables = {1: [header], 2: []}
    keys = hd._find_header_structure_keys(pages_tables)
    assert len(keys) == 0


def test_find_header_structure_keys_ignores_table_in_middle_of_page():
    mid_table = _make_table(bbox=[0, 400, 500, 450], page_height=841)
    pages_tables = {1: [mid_table], 2: [mid_table], 3: [mid_table]}
    keys = hd._find_header_structure_keys(pages_tables)
    assert len(keys) == 0


# ── filter_page_header_tables (end-to-end with monkeypatched LLM) ────────────

def test_filter_marks_header_tables_when_llm_confirms(monkeypatch):
    monkeypatch.setattr(hd, "_confirm_header_with_llm", lambda table, model: True)

    header = _make_table(bbox=[0, 5, 500, 50], page_height=841)
    content = _make_table(bbox=[0, 200, 500, 400], page_height=841,
                          cells=[["条款", "内容"], ["1", "适用范围"]])
    pages_tables = {
        1: [header, content],
        2: [header, content],
    }
    result = hd.filter_page_header_tables(pages_tables)

    # Header tables are marked, not removed — so bboxes stay for suppression
    header_key = hd._table_structure_key(header)
    for tables in result.values():
        for t in tables:
            if hd._table_structure_key(t) == header_key:
                assert t.get("_is_page_header") is True
            else:
                assert not t.get("_is_page_header")

    # Content tables are untouched
    assert all(
        any(hd._table_structure_key(t) == hd._table_structure_key(content) for t in tables)
        for tables in result.values()
    )


def test_filter_keeps_tables_when_llm_denies(monkeypatch):
    monkeypatch.setattr(hd, "_confirm_header_with_llm", lambda table, model: False)

    header = _make_table(bbox=[0, 5, 500, 50], page_height=841)
    pages_tables = {1: [header], 2: [header]}
    result = hd.filter_page_header_tables(pages_tables)

    assert result == pages_tables


def test_filter_passthrough_for_single_page():
    header = _make_table(bbox=[0, 5, 500, 50], page_height=841)
    pages_tables = {1: [header]}
    result = hd.filter_page_header_tables(pages_tables)
    assert result == pages_tables


def test_filter_passthrough_when_no_candidates(monkeypatch):
    monkeypatch.setattr(hd, "_confirm_header_with_llm", lambda table, model: True)

    mid_table = _make_table(bbox=[0, 400, 500, 450], page_height=841)
    pages_tables = {1: [mid_table], 2: [mid_table]}
    result = hd.filter_page_header_tables(pages_tables)
    assert result == pages_tables
