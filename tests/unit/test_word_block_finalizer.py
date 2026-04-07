"""Unit tests for the Word block finalizer."""

from __future__ import annotations

import pytest

from pageindex.core.indexers.pipeline.step_06_finalize import word_block_finalizer


@pytest.fixture(autouse=True)
def _stub_count_tokens(monkeypatch):
    monkeypatch.setattr(word_block_finalizer, "count_tokens", lambda text, model=None: len(text))


def _raw(section_ordinal, text, source="paragraph"):
    return {"section_ordinal": section_ordinal, "raw_text": text, "source": source}


def _leaf(node_id, start, end, title="leaf"):
    return {"title": title, "node_id": node_id, "start_index": start, "end_index": end, "nodes": []}


def test_basic_shape_assigns_block_no_and_orders():
    raw_blocks = [
        _raw(1, "abc"),
        _raw(1, "de"),
        _raw(2, "fghi"),
    ]
    tree = [_leaf("0001", 1, 1), _leaf("0002", 2, 2)]

    blocks, char_count, token_count = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert [b["block_no"] for b in blocks] == [1, 2, 3]
    assert [b["block_order_in_page"] for b in blocks] == [1, 2, 1]
    assert [b["page_no"] for b in blocks] == [1, 1, 2]
    assert [b["start_index"] for b in blocks] == [1, 1, 2]
    assert [b["end_index"] for b in blocks] == [1, 1, 2]
    assert char_count == 3 + 2 + 4
    assert token_count == 3 + 2 + 4


def test_doc_char_offsets_are_cumulative_with_separator():
    raw_blocks = [_raw(1, "abc"), _raw(1, "de"), _raw(2, "fghi")]
    tree = [_leaf("0001", 1, 1), _leaf("0002", 2, 2)]

    blocks, _, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    # block 0: "abc" → starts at 0, ends at 2
    # +1 separator → next starts at 4
    # block 1: "de" → starts at 4, ends at 5
    # +1 separator → next starts at 7
    # block 2: "fghi" → starts at 7, ends at 10
    assert [b["char_start_in_doc"] for b in blocks] == [0, 4, 7]
    assert [b["char_end_in_doc"] for b in blocks] == [2, 5, 10]


def test_page_char_offsets_reset_on_section_change():
    raw_blocks = [_raw(1, "abc"), _raw(1, "de"), _raw(2, "fghi")]
    tree = [_leaf("0001", 1, 1), _leaf("0002", 2, 2)]

    blocks, _, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    # section 1: block 0 starts at 0, block 1 separated by 1 → starts at 4
    # section 2: block 2 resets to 0
    assert [b["char_start_in_page"] for b in blocks] == [0, 4, 0]
    assert [b["char_end_in_page"] for b in blocks] == [2, 5, 3]


def test_node_id_resolves_to_leaf_for_each_section():
    raw_blocks = [_raw(1, "x"), _raw(2, "y"), _raw(3, "z")]
    tree = [
        _leaf("0001", 1, 1),
        _leaf("0002", 2, 2),
        _leaf("0003", 3, 3),
    ]

    blocks, _, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert [b["metadata"]["pageindex_node_id"] for b in blocks] == ["0001", "0002", "0003"]


def test_node_id_prefers_deepest_node_in_hierarchy():
    raw_blocks = [_raw(2, "x")]
    tree = [
        {
            "title": "root",
            "node_id": "0000",
            "start_index": 1,
            "end_index": 4,
            "nodes": [
                {
                    "title": "branch",
                    "node_id": "0001",
                    "start_index": 1,
                    "end_index": 2,
                    "nodes": [_leaf("0002", 2, 2, title="deep")],
                },
                _leaf("0003", 3, 4),
            ],
        }
    ]

    blocks, _, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert blocks[0]["metadata"]["pageindex_node_id"] == "0002"


def test_node_id_falls_back_to_covering_ancestor_when_no_leaf_matches():
    raw_blocks = [_raw(5, "x")]
    tree = [
        {
            "title": "root",
            "node_id": "0000",
            "start_index": 1,
            "end_index": 10,
            "nodes": [_leaf("0001", 1, 1)],
        }
    ]

    blocks, _, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert blocks[0]["metadata"]["pageindex_node_id"] == "0000"


def test_metadata_type_is_text_for_all_sources():
    raw_blocks = [_raw(1, "para", source="paragraph"), _raw(1, "tabletext", source="table")]
    tree = [_leaf("0001", 1, 1)]

    blocks, _, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert all(b["metadata"]["type"] == "text" for b in blocks)


def test_empty_raw_text_after_strip_is_dropped():
    raw_blocks = [_raw(1, "real"), _raw(1, "   "), _raw(1, "also")]
    tree = [_leaf("0001", 1, 1)]

    blocks, char_count, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert [b["raw_content"] for b in blocks] == ["real", "also"]
    assert [b["block_no"] for b in blocks] == [1, 2]
    assert char_count == len("real") + len("also")


def test_single_block_in_single_section():
    raw_blocks = [_raw(1, "hello")]
    tree = [_leaf("0001", 1, 1)]

    blocks, char_count, token_count = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert len(blocks) == 1
    block = blocks[0]
    assert block["block_no"] == 1
    assert block["block_order_in_page"] == 1
    assert block["start_index"] == 1
    assert block["end_index"] == 1
    assert block["page_no"] == 1
    assert block["char_start_in_doc"] == 0
    assert block["char_end_in_doc"] == 4
    assert block["char_start_in_page"] == 0
    assert block["char_end_in_page"] == 4
    assert char_count == 5
    assert token_count == 5


def test_normalized_text_strips_outer_whitespace():
    raw_blocks = [_raw(1, "  hello  ")]
    tree = [_leaf("0001", 1, 1)]

    blocks, char_count, _ = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert blocks[0]["normalized_text"] == "hello"
    assert blocks[0]["raw_content"] == "  hello  "
    assert char_count == len("hello")


def test_returns_empty_when_all_blocks_dropped():
    raw_blocks = [_raw(1, "   "), _raw(2, "")]
    tree = [_leaf("0001", 1, 1)]

    blocks, char_count, token_count = word_block_finalizer.finalize_word_blocks(raw_blocks, tree, model=None)

    assert blocks == []
    assert char_count == 0
    assert token_count == 0
