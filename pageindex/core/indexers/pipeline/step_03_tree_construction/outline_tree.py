from __future__ import annotations

from pageindex.core.utils.tree import list_to_tree


def add_preface_if_needed(data):
    if not isinstance(data, list) or not data:
        return data
    if data[0]["physical_index"] is not None and data[0]["physical_index"] > 1:
        preface_node = {
            "structure": "0",
            "title": "Preface",
            "physical_index": 1,
        }
        data.insert(0, preface_node)
    return data


def post_processing(structure, end_physical_index):
    for index, item in enumerate(structure):
        item["start_index"] = item.get("physical_index")
        if index < len(structure) - 1:
            if structure[index + 1].get("appear_start") == "yes":
                item["end_index"] = max(structure[index + 1]["physical_index"] - 1, item["start_index"])
            else:
                item["end_index"] = structure[index + 1]["physical_index"]
        else:
            item["end_index"] = end_physical_index
    tree = list_to_tree(structure)
    if tree:
        return tree
    for node in structure:
        node.pop("appear_start", None)
        node.pop("physical_index", None)
    return structure
