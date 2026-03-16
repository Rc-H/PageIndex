from __future__ import annotations

import re

from pageindex.core.utils.token_counter import count_tokens


def extract_nodes_from_markdown(markdown_content: str) -> tuple[list[dict[str, int | str]], list[str]]:
    header_pattern = r"^(#{1,6})\s+(.+)$"
    code_block_pattern = r"^```"
    node_list: list[dict[str, int | str]] = []

    lines = markdown_content.split("\n")
    in_code_block = False

    for line_num, line in enumerate(lines, 1):
        stripped_line = line.strip()

        if re.match(code_block_pattern, stripped_line):
            in_code_block = not in_code_block
            continue

        if not stripped_line:
            continue

        if not in_code_block:
            match = re.match(header_pattern, stripped_line)
            if match:
                title = match.group(2).strip()
                node_list.append({"node_title": title, "line_num": line_num})

    return node_list, lines


def extract_node_text_content(
    node_list: list[dict[str, int | str]],
    markdown_lines: list[str],
) -> list[dict[str, int | str]]:
    all_nodes: list[dict[str, int | str]] = []
    for node in node_list:
        line_num = int(node["line_num"])
        line_content = markdown_lines[line_num - 1]
        header_match = re.match(r"^(#{1,6})", line_content)

        if header_match is None:
            continue

        processed_node = {
            "title": str(node["node_title"]),
            "line_num": line_num,
            "level": len(header_match.group(1)),
        }
        all_nodes.append(processed_node)

    for index, node in enumerate(all_nodes):
        start_line = int(node["line_num"]) - 1
        if index + 1 < len(all_nodes):
            end_line = int(all_nodes[index + 1]["line_num"]) - 1
        else:
            end_line = len(markdown_lines)

        node["text"] = "\n".join(markdown_lines[start_line:end_line]).strip()
    return all_nodes


def update_node_list_with_text_token_count(
    node_list: list[dict[str, int | str]],
    model: str | None = None,
) -> list[dict[str, int | str]]:
    def find_all_children(parent_index: int, parent_level: int, nodes: list[dict[str, int | str]]) -> list[int]:
        children_indices: list[int] = []
        for child_index in range(parent_index + 1, len(nodes)):
            current_level = int(nodes[child_index]["level"])
            if current_level <= parent_level:
                break
            children_indices.append(child_index)
        return children_indices

    result_list = node_list.copy()

    for index in range(len(result_list) - 1, -1, -1):
        current_node = result_list[index]
        current_level = int(current_node["level"])
        children_indices = find_all_children(index, current_level, result_list)

        total_text = str(current_node.get("text", ""))
        for child_index in children_indices:
            child_text = str(result_list[child_index].get("text", ""))
            if child_text:
                total_text += "\n" + child_text

        current_node["text_token_count"] = count_tokens(total_text, model=model)

    return result_list


def tree_thinning_for_index(
    node_list: list[dict[str, int | str]],
    min_node_token: int | None = None,
    model: str | None = None,
) -> list[dict[str, int | str]]:
    def find_all_children(parent_index: int, parent_level: int, nodes: list[dict[str, int | str]]) -> list[int]:
        children_indices: list[int] = []
        for child_index in range(parent_index + 1, len(nodes)):
            current_level = int(nodes[child_index]["level"])
            if current_level <= parent_level:
                break
            children_indices.append(child_index)
        return children_indices

    result_list = node_list.copy()
    nodes_to_remove: set[int] = set()
    threshold = min_node_token or 0

    for index in range(len(result_list) - 1, -1, -1):
        if index in nodes_to_remove:
            continue

        current_node = result_list[index]
        current_level = int(current_node["level"])
        total_tokens = int(current_node.get("text_token_count", 0))

        if total_tokens < threshold:
            children_indices = find_all_children(index, current_level, result_list)

            children_texts: list[str] = []
            for child_index in sorted(children_indices):
                if child_index in nodes_to_remove:
                    continue
                child_text = str(result_list[child_index].get("text", ""))
                if child_text.strip():
                    children_texts.append(child_text)
                nodes_to_remove.add(child_index)

            if children_texts:
                merged_text = str(current_node.get("text", ""))
                for child_text in children_texts:
                    if merged_text and not merged_text.endswith("\n"):
                        merged_text += "\n\n"
                    merged_text += child_text

                current_node["text"] = merged_text
                current_node["text_token_count"] = count_tokens(merged_text, model=model)

    for index in sorted(nodes_to_remove, reverse=True):
        result_list.pop(index)

    return result_list
