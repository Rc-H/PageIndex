"""Link extracted blocks to structure tree nodes.

Provides two strategies:
- Page-based linking: matches blocks to nodes by ``page_no`` ↔ ``start_index``/``end_index``
- Block-based linking: matches by ``block_no`` ↔ ``start_block``/``end_block``
"""

from __future__ import annotations

from typing import Any

PAGEINDEX_NODE_ID_KEY = "pageindex_node_id"


def attach_block_node_ids(blocks: list[dict[str, Any]], structure: list[dict[str, Any]]):
    """Assign node IDs to blocks using page-based matching."""
    for block in blocks:
        node_id = _find_deepest_covering_node_id(structure, block["page_no"])
        if node_id:
            block[PAGEINDEX_NODE_ID_KEY] = node_id


def attach_block_node_ids_by_block_range(blocks: list[dict[str, Any]], structure: list[dict[str, Any]]):
    """Assign node IDs to blocks using block-range matching."""
    for block in blocks:
        node_id = _find_deepest_covering_node_by_block(structure, block["block_no"])
        if node_id:
            block[PAGEINDEX_NODE_ID_KEY] = node_id


def _find_deepest_covering_node_id(nodes, page_no):
    best_match = None
    for node in nodes:
        start_index = node.get("start_index")
        end_index = node.get("end_index")
        if start_index is None or end_index is None or page_no < start_index or page_no > end_index:
            continue
        child_match = _find_deepest_covering_node_id(node.get("nodes", []), page_no)
        if child_match:
            return child_match
        best_match = node.get("node_id")
    return best_match


def _find_deepest_covering_node_by_block(nodes, block_no):
    best_match = None
    for node in nodes:
        sb = node.get("start_block")
        eb = node.get("end_block")
        if sb is None or eb is None or block_no < sb or block_no > eb:
            continue
        child_match = _find_deepest_covering_node_by_block(node.get("nodes", []), block_no)
        if child_match:
            return child_match
        best_match = node.get("node_id")
    return best_match
