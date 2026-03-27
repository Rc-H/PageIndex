import logging
import json

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.utils.llm_caller import call_llm
from pageindex.core.utils.structure_ops import convert_physical_index_to_int

logger = logging.getLogger(__name__)


def _log_outline_item_types(name, items):
    if not isinstance(items, list):
        logger.warning("%s is not a list: type=%s value=%r", name, type(items).__name__, items)
        return

    bad_items = [
        {"index": index, "type": type(item).__name__, "value": repr(item)[:200]}
        for index, item in enumerate(items)
        if not isinstance(item, dict)
    ]
    if bad_items:
        logger.warning("%s contains non-dict items: %s", name, bad_items)


def toc_index_extractor(toc, content, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_04_outline_index_alignment/prompts/toc_index_extract.txt")
    results = []
    for item in toc:
        item_prompt = (
            prompt
            + f"\n\nSection To Check\n{json.dumps(item, indent=2)}\n\nDocument pages:\n{content}"
        )
        response = call_llm(model=model, prompt=item_prompt, json_response=True)
        parsed = json.loads(response)
        results.append(
            {
                "structure": parsed.get("structure", item.get("structure")),
                "title": parsed.get("title", item.get("title")),
                "page": parsed.get("page"),
            }
        )
    _log_outline_item_types("toc_index_extractor response", results)
    return results


def add_page_number_to_toc(part, structure, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_04_outline_index_alignment/prompts/toc_add_page_number.txt")
    results = []
    for item in structure:
        item_prompt = (
            prompt
            + f"\n\nCurrent Partial Document:\n{part}\n\nSection To Check\n{json.dumps(item, indent=2)}\n"
        )
        current_json_raw = call_llm(model=model, prompt=item_prompt, json_response=True)
        parsed = json.loads(current_json_raw)
        results.append(
            {
                "structure": parsed.get("structure", item.get("structure")),
                "title": parsed.get("title", item.get("title")),
                "physical_index": convert_physical_index_to_int(parsed.get("physical_index")),
            }
        )
    _log_outline_item_types("add_page_number_to_toc results", results)
    return results


def remove_page_number(data):
    if isinstance(data, dict):
        data.pop("page_number", None)
        for key in list(data.keys()):
            if "nodes" in key:
                remove_page_number(data[key])
    elif isinstance(data, list):
        for item in data:
            remove_page_number(item)
    return data


def extract_matching_page_pairs(toc_page, toc_physical_index, start_page_index):
    _log_outline_item_types("extract_matching_page_pairs.toc_page", toc_page)
    _log_outline_item_types("extract_matching_page_pairs.toc_physical_index", toc_physical_index)
    pairs = []
    for phy_item in toc_physical_index:
        for page_item in toc_page:
            if phy_item.get("title") == page_item.get("title"):
                physical_index = phy_item.get("physical_index")
                if physical_index is not None and int(physical_index) >= start_page_index:
                    pairs.append(
                        {
                            "title": phy_item.get("title"),
                            "page": page_item.get("page"),
                            "physical_index": physical_index,
                        }
                    )
    return pairs


def calculate_page_offset(pairs):
    differences = []
    for pair in pairs:
        try:
            differences.append(pair["physical_index"] - pair["page"])
        except (KeyError, TypeError):
            continue
    if not differences:
        return None
    difference_counts = {}
    for diff in differences:
        difference_counts[diff] = difference_counts.get(diff, 0) + 1
    return max(difference_counts, key=difference_counts.get)


def add_page_offset_to_toc_json(data, offset):
    if isinstance(data, list):
        for item in data:
            if "page" in item and item["page"] is not None:
                item["physical_index"] = item["page"] + offset
            if "nodes" in item:
                add_page_offset_to_toc_json(item["nodes"], offset)
    return data


def process_none_page_numbers(toc_items, page_list, start_index=1, model=None):
    from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_05_outline_fallback_generation import page_list_to_group_text

    page_contents = []
    token_lengths = []
    for index, (page_text, token_num) in enumerate(page_list):
        page_contents.append(f"<physical_index_{index + start_index}>\n{page_text}\n<physical_index_{index + start_index}>\n\n")
        token_lengths.append(token_num)

    parts = page_list_to_group_text(page_contents, token_lengths)
    groups = []
    for part in parts:
        response = toc_index_extractor(toc_items, part, model=model)
        groups.append(response)

    final_groups = []
    for group in groups:
        if isinstance(group, dict):
            content = group.get("table_of_contents", group.get("content", []))
            if isinstance(content, list):
                final_groups.extend(content)
        elif isinstance(group, list):
            final_groups.extend(group)
    return final_groups
