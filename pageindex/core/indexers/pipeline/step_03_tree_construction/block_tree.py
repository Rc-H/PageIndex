"""Tree construction for block-based PDF outlines.

Converts the flat list from ``process_block_outline`` into a hierarchical
tree using ``build_tree_from_nodes``, analogous to how the Word adapter
converts heading nodes into a tree. Each node carries:

- ``start_index`` / ``end_index`` — page number range (1-indexed, inclusive).
- ``start_block`` / ``end_block`` — block number range (1-indexed, inclusive).
"""

from __future__ import annotations

from typing import Any

from pageindex.core.indexers.pipeline.step_03_tree_construction.markdown_tree import (
    build_tree_from_nodes,
)


def build_block_tree(
    outline_items: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a hierarchical tree from block-level outline items.

    ``outline_items``: flat list of ``{structure, title, start_block_no}``.
    ``blocks``: the full block list for deriving end boundaries and page numbers.

    Returns a nested tree where each node has ``title``, ``start_index``/
    ``end_index`` (page range) and ``start_block``/``end_block`` (block range).
    """
    if not outline_items or not blocks:
        return []

    block_lookup = {b["block_no"]: b for b in blocks}
    max_block_no = blocks[-1]["block_no"]

    # Convert flat items into the shape expected by build_tree_from_nodes.
    # We temporarily put block numbers into start_index/end_index so the
    # tree builder can bubble up the correct min/max; we overwrite them with
    # page numbers in a second pass and keep the block range under
    # start_block/end_block.
    flat_nodes = []
    for i, item in enumerate(outline_items):
        sb = item["start_block_no"]
        eb = (outline_items[i + 1]["start_block_no"] - 1) if i + 1 < len(outline_items) else max_block_no

        text_parts = []
        for bno in range(sb, eb + 1):
            b = block_lookup.get(bno)
            if b:
                text_parts.append(b["normalized_text"])
        text = "\n".join(text_parts)

        flat_nodes.append({
            "title": item.get("title", ""),
            "level": _structure_to_level(item.get("structure", "1")),
            "line_num": sb,
            "text": text,
            "start_index": sb,
            "end_index": eb,
        })

    tree = build_tree_from_nodes(flat_nodes)
    _rewrite_indices_to_pages(tree, block_lookup)
    return tree


def _structure_to_level(structure: str) -> int:
    return len(str(structure).split("."))


def _rewrite_indices_to_pages(nodes: list[dict[str, Any]], block_lookup: dict[int, Any]):
    """Move the bubbled-up block range into start_block/end_block and
    overwrite start_index/end_index with the corresponding page numbers.
    """
    for node in nodes:
        sb = node.get("start_index")
        eb = node.get("end_index")
        if sb is not None and eb is not None:
            node["start_block"] = sb
            node["end_block"] = eb
            node["start_index"] = block_lookup[sb]["page_no"] if sb in block_lookup else None
            node["end_index"] = block_lookup[eb]["page_no"] if eb in block_lookup else None

        children = node.get("nodes")
        if children:
            _rewrite_indices_to_pages(children, block_lookup)
