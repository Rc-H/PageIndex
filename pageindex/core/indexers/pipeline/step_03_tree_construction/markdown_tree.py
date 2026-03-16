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

        while stack and stack[-1][1] >= current_level:
            stack.pop()

        if not stack:
            root_nodes.append(tree_node)
        else:
            parent_node, _ = stack[-1]
            parent_node["nodes"].append(tree_node)

        stack.append((tree_node, current_level))

    return root_nodes
