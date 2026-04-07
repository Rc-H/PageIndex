"""Generic level-based tree builder for flat heading nodes.

Used by both Markdown and Word adapters. Format-agnostic: it propagates the
optional ``start_index`` and ``end_index`` fields when present on the source
nodes and bubbles up parent ranges from their children. Markdown flat nodes
do not carry these fields, so for Markdown the propagation is a no-op.
"""

from __future__ import annotations


def build_tree_from_nodes(node_list):
    if not node_list:
        return []

    stack = []
    root_nodes = []

    for node in node_list:
        current_level = node["level"]
        tree_node = {
            "title": node["title"],
            "text": node["text"],
            "line_num": node["line_num"],
            "nodes": [],
        }

        if "start_index" in node:
            tree_node["start_index"] = node["start_index"]
        if "end_index" in node:
            tree_node["end_index"] = node["end_index"]

        while stack and stack[-1][1] >= current_level:
            stack.pop()

        if not stack:
            root_nodes.append(tree_node)
        else:
            parent_node, _ = stack[-1]
            parent_node["nodes"].append(tree_node)

        stack.append((tree_node, current_level))

    _bubble_up_indices(root_nodes)
    return root_nodes


def _bubble_up_indices(nodes):
    """Post-order walk: each parent's range = min/max of its children's ranges.

    Children that have no ``start_index`` / ``end_index`` are ignored. If no
    child contributes a range, the parent's existing values (if any) are
    preserved. If neither the parent nor any child carries a range, the
    parent stays unchanged.
    """

    for node in nodes:
        children = node.get("nodes") or []
        if children:
            _bubble_up_indices(children)

            child_starts = [c["start_index"] for c in children if "start_index" in c]
            child_ends = [c["end_index"] for c in children if "end_index" in c]

            if child_starts:
                existing = node.get("start_index")
                node["start_index"] = (
                    min(min(child_starts), existing) if existing is not None else min(child_starts)
                )
            if child_ends:
                existing = node.get("end_index")
                node["end_index"] = (
                    max(max(child_ends), existing) if existing is not None else max(child_ends)
                )
