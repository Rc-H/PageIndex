"""Tree construction for block-based PDF outlines.

Converts the flat list from ``process_block_outline`` into a hierarchical
tree using ``build_tree_from_nodes``, analogous to how the Word adapter
converts heading nodes into a tree. Each node carries ``start_index`` and
``end_index`` as block numbers (not page numbers), plus ``start_block`` and
``end_block`` as explicit aliases, and ``start_page``/``end_page`` derived
from the block list.
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

    ``outline_items``: flat list of ``{structure, title, start_block_no}``
    ``blocks``: the full block list for deriving end boundaries and page numbers.

    Returns a nested tree where each node has:
    - ``title``, ``text``, ``line_num`` (for compat with ``build_tree_from_nodes``)
    - ``start_index``, ``end_index`` — block number range
    - ``start_block``, ``end_block`` — same as start/end_index (explicit)
    - ``start_page``, ``end_page`` — derived page numbers
    """
    if not outline_items or not blocks:
        return []

    block_lookup = {b["block_no"]: b for b in blocks}
    max_block_no = blocks[-1]["block_no"]

    # Convert flat items to node format expected by build_tree_from_nodes
    flat_nodes = []
    for i, item in enumerate(outline_items):
        sb = item["start_block_no"]
        # end_block = next item's start - 1, or max_block for the last item
        eb = (outline_items[i + 1]["start_block_no"] - 1) if i + 1 < len(outline_items) else max_block_no

        # Collect text from blocks in range
        text_parts = []
        for bno in range(sb, eb + 1):
            b = block_lookup.get(bno)
            if b:
                text_parts.append(b["normalized_text"])
        text = "\n".join(text_parts)

        # Derive page range from blocks
        start_page = block_lookup[sb]["page_no"] if sb in block_lookup else 1
        end_page = block_lookup[eb]["page_no"] if eb in block_lookup else start_page

        flat_nodes.append({
            "title": item.get("title", ""),
            "level": _structure_to_level(item.get("structure", "1")),
            "line_num": sb,  # use block_no as line_num for compat
            "text": text,
            "start_index": sb,
            "end_index": eb,
        })

    tree = build_tree_from_nodes(flat_nodes)
    _attach_block_and_page_fields(tree, block_lookup)
    return tree


def _structure_to_level(structure: str) -> int:
    """Convert a structure string like '1.2.3' to a depth level."""
    return len(str(structure).split("."))


def _attach_block_and_page_fields(nodes: list[dict[str, Any]], block_lookup: dict[int, Any]):
    """Add start_block/end_block/start_page/end_page to every node."""
    for node in nodes:
        si = node.get("start_index")
        ei = node.get("end_index")
        if si is not None and ei is not None:
            node["start_block"] = si
            node["end_block"] = ei
            node["start_page"] = block_lookup[si]["page_no"] if si in block_lookup else None
            node["end_page"] = block_lookup[ei]["page_no"] if ei in block_lookup else None

        children = node.get("nodes")
        if children:
            _attach_block_and_page_fields(children, block_lookup)
