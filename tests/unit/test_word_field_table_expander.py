"""Unit tests for the LLM-driven field table expander."""

from __future__ import annotations

import json
from typing import Any

import pytest

from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_field_table_expander


# ---------- table fakes -------------------------------------------------------


class _FakeRow:
    def __init__(self, cells):
        self.cells = cells


class _FakeTable:
    def __init__(self, rows):
        self.rows = [_FakeRow(row) for row in rows]


def _make_table(rows: list[list[str]]) -> _FakeTable:
    return _FakeTable([[_StringCell(value) for value in row] for row in rows])


class _StringCell:
    def __init__(self, value: str):
        self._value = value


def _string_cell_text_getter(cell, image_cache=None):
    return cell._value


# ---------- LLM stubs ---------------------------------------------------------


def _stub_llm_returning(monkeypatch, payload, captured: dict | None = None):
    def fake_call(model, prompt, json_response=False):
        if captured is not None:
            captured["model"] = model
            captured["prompt"] = prompt
            captured["json_response"] = json_response
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(word_field_table_expander, "call_llm", fake_call)


# ---------- tests -------------------------------------------------------------


def test_returns_none_for_table_without_data_rows(monkeypatch):
    table = _make_table([["字段名称", "类型", "说明"]])  # header only

    _stub_llm_returning(monkeypatch, "should not be called")

    result = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert result is None


def test_returns_none_for_table_with_one_data_row(monkeypatch):
    # MIN_DATA_ROWS_FOR_EXPANSION = 2 → a single data row is not worth asking
    table = _make_table([
        ["字段名称", "类型"],
        ["编码", "文本"],
    ])

    _stub_llm_returning(monkeypatch, "should not be called")

    result = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert result is None


def test_returns_none_for_single_column_table(monkeypatch):
    table = _make_table([["字段"], ["A"], ["B"]])

    _stub_llm_returning(monkeypatch, "should not be called")

    result = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert result is None


def test_expands_when_llm_says_yes_with_explicit_name_column(monkeypatch):
    table = _make_table([
        ["分类", "字段名称", "类型", "说明"],
        ["基本信息", "核算组织", "组织", "当前核算组织"],
        ["基本信息", "编码", "文本", "自动带出"],
    ])

    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": True, "name_column_index": 1}),
    )

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["租赁物资档案", "基础数据"],
        model="gpt-test",
    )

    assert items is not None
    assert len(items) == 4  # 2 (heading + body) per row × 2 rows

    # First row: heading then body
    assert items[0] == {
        "kind": "heading",
        "source": "table",
        "text": "核算组织",
        "level_offset": 1,
    }
    body_0 = items[1]["text"]
    assert "路径: 租赁物资档案 > 基础数据 > 核算组织" in body_0
    assert "字段名称: 核算组织" in body_0
    assert "类型: 组织" in body_0
    assert "说明: 当前核算组织" in body_0
    assert "分类: 基本信息" in body_0

    # Second row
    assert items[2]["text"] == "编码"
    assert "路径: 租赁物资档案 > 基础数据 > 编码" in items[3]["text"]
    assert "字段名称: 编码" in items[3]["text"]


def test_falls_back_to_first_column_when_name_column_index_invalid(monkeypatch):
    table = _make_table([
        ["A", "B", "C"],
        ["x1", "y1", "z1"],
        ["x2", "y2", "z2"],
    ])

    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": True, "name_column_index": 999}),
    )

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is not None
    # name column fell back to 0 → row names should be x1 / x2
    assert items[0]["text"] == "x1"
    assert items[2]["text"] == "x2"


def test_falls_back_to_first_column_when_name_column_index_missing(monkeypatch):
    table = _make_table([
        ["A", "B"],
        ["x1", "y1"],
        ["x2", "y2"],
    ])

    _stub_llm_returning(monkeypatch, json.dumps({"should_expand": True}))  # no name_column_index

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is not None
    assert items[0]["text"] == "x1"
    assert items[2]["text"] == "x2"


def test_returns_none_when_llm_says_no(monkeypatch):
    table = _make_table([
        ["month", "revenue"],
        ["2026-01", "100"],
        ["2026-02", "120"],
    ])

    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": False, "name_column_index": None}),
    )

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is None


def test_returns_none_when_llm_payload_missing_should_expand(monkeypatch):
    table = _make_table([
        ["A", "B"],
        ["x1", "y1"],
        ["x2", "y2"],
    ])

    _stub_llm_returning(
        monkeypatch,
        json.dumps({"random_key": True, "name_column_index": 0}),
    )

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is None


def test_returns_none_when_llm_returns_invalid_json(monkeypatch):
    table = _make_table([
        ["A", "B"],
        ["x1", "y1"],
        ["x2", "y2"],
    ])

    _stub_llm_returning(monkeypatch, "this is not json {")

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is None


def test_returns_none_when_llm_returns_error_sentinel(monkeypatch):
    table = _make_table([
        ["A", "B"],
        ["x1", "y1"],
        ["x2", "y2"],
    ])

    _stub_llm_returning(monkeypatch, "Error")

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is None


def test_returns_none_when_llm_call_raises(monkeypatch):
    table = _make_table([
        ["A", "B"],
        ["x1", "y1"],
        ["x2", "y2"],
    ])

    _stub_llm_returning(monkeypatch, RuntimeError("boom"))

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert items is None


def test_skips_rows_with_empty_name_column(monkeypatch):
    table = _make_table([
        ["A", "B"],
        ["x1", "y1"],
        ["", "y2"],  # name column empty → skip
        ["x3", "y3"],
    ])

    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": True, "name_column_index": 0}),
    )

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    # Only x1 and x3 produce items
    assert items is not None
    assert len(items) == 4
    assert items[0]["text"] == "x1"
    assert items[2]["text"] == "x3"


def test_llm_prompt_is_loaded_with_headers_and_sample_rows(monkeypatch):
    table = _make_table([
        ["字段", "类型"],
        ["foo", "int"],
        ["bar", "str"],
    ])

    captured: dict[str, Any] = {}
    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": True, "name_column_index": 0}),
        captured=captured,
    )

    word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    assert captured["model"] == "gpt-test"
    assert captured["json_response"] is True
    # Headers and sample rows are interpolated into the prompt
    assert "字段" in captured["prompt"]
    assert "类型" in captured["prompt"]
    assert "foo" in captured["prompt"]
    assert "bar" in captured["prompt"]


def test_sample_rows_are_capped_for_large_tables(monkeypatch):
    rows = [["字段", "类型"]] + [[f"name{i}", f"type{i}"] for i in range(20)]
    table = _make_table(rows)

    captured: dict[str, Any] = {}
    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": False}),
        captured=captured,
    )

    word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["Doc"],
        model="gpt-test",
    )

    # The prompt only includes the first MAX_SAMPLE_ROWS_FOR_GATE rows
    cap = word_field_table_expander.MAX_SAMPLE_ROWS_FOR_GATE
    assert "name0" in captured["prompt"]
    assert f"name{cap - 1}" in captured["prompt"]
    assert f"name{cap}" not in captured["prompt"]


def test_breadcrumb_uses_only_heading_path_when_provided(monkeypatch):
    table = _make_table([
        ["字段", "类型"],
        ["foo", "int"],
        ["bar", "str"],
    ])

    _stub_llm_returning(
        monkeypatch,
        json.dumps({"should_expand": True, "name_column_index": 0}),
    )

    items = word_field_table_expander.try_expand_field_table(
        table=table,
        cell_text_getter=_string_cell_text_getter,
        image_cache=None,
        heading_path=["租赁物资档案", "基础数据", "字段定义"],
        model="gpt-test",
    )

    body = items[1]["text"]
    assert body.startswith("路径: 租赁物资档案 > 基础数据 > 字段定义 > foo")
