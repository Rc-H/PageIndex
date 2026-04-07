"""Unit tests for the level-based tree builder.

Used by both Markdown and Word adapters. Verifies the generic optional
``start_index`` / ``end_index`` propagation and bubble-up so Markdown stays
unaffected (no fields propagated) and Word gets correct section coverage.
"""

from __future__ import annotations

from pageindex.core.indexers.pipeline.step_03_tree_construction.markdown_tree import (
    build_tree_from_nodes,
)


def _node(title, level, line_num=1, text="", **extras):
    base = {"title": title, "level": level, "line_num": line_num, "text": text}
    base.update(extras)
    return base


def test_returns_empty_for_empty_input():
    assert build_tree_from_nodes([]) == []


def test_markdown_style_nodes_are_unaffected_by_propagation():
    flat = [
        _node("Title", level=1),
        _node("Sub", level=2),
    ]

    tree = build_tree_from_nodes(flat)

    assert "start_index" not in tree[0]
    assert "end_index" not in tree[0]
    assert "start_index" not in tree[0]["nodes"][0]
    assert "end_index" not in tree[0]["nodes"][0]


def test_leaves_preserve_start_end_when_present():
    flat = [
        _node("A", level=1, start_index=1, end_index=1),
        _node("B", level=1, start_index=2, end_index=2),
    ]

    tree = build_tree_from_nodes(flat)

    assert tree[0]["start_index"] == 1
    assert tree[0]["end_index"] == 1
    assert tree[1]["start_index"] == 2
    assert tree[1]["end_index"] == 2


def test_parent_bubbles_up_min_max_of_children():
    flat = [
        _node("Root", level=1, start_index=1, end_index=1),
        _node("Child A", level=2, start_index=2, end_index=2),
        _node("Child B", level=2, start_index=4, end_index=4),
    ]

    tree = build_tree_from_nodes(flat)

    root = tree[0]
    assert root["start_index"] == 1
    assert root["end_index"] == 4


def test_three_level_tree_bubbles_through_all_levels():
    flat = [
        _node("L1", level=1, start_index=1, end_index=1),
        _node("L2", level=2, start_index=2, end_index=2),
        _node("L3a", level=3, start_index=3, end_index=3),
        _node("L3b", level=3, start_index=5, end_index=5),
        _node("L2b", level=2, start_index=7, end_index=7),
    ]

    tree = build_tree_from_nodes(flat)

    root = tree[0]
    assert root["start_index"] == 1
    assert root["end_index"] == 7
    l2_first = root["nodes"][0]
    assert l2_first["start_index"] == 2
    assert l2_first["end_index"] == 5
    l2_second = root["nodes"][1]
    assert l2_second["start_index"] == 7
    assert l2_second["end_index"] == 7


def test_bubble_ignores_children_without_indices():
    flat = [
        _node("Root", level=1),  # no indices on root or this child
        _node("Child A", level=2, start_index=3, end_index=3),
        _node("Child B", level=2),  # no indices
    ]

    tree = build_tree_from_nodes(flat)

    root = tree[0]
    # Root inherits the only child that has indices
    assert root["start_index"] == 3
    assert root["end_index"] == 3
    assert "start_index" not in root["nodes"][1]
    assert "end_index" not in root["nodes"][1]


def test_existing_parent_indices_are_widened_not_overwritten():
    flat = [
        _node("Root", level=1, start_index=10, end_index=10),
        _node("Child", level=2, start_index=2, end_index=20),
    ]

    tree = build_tree_from_nodes(flat)

    root = tree[0]
    assert root["start_index"] == 2
    assert root["end_index"] == 20
