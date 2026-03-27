import json
import math
from typing import Any

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_04_outline_index_alignment import remove_page_number
from pageindex.core.utils.llm_caller import call_llm_with_finish_reason
from pageindex.core.utils.structure_ops import convert_physical_index_to_int


def _normalize_toc_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("result")
        if isinstance(items, list):
            return items
    raise ValueError(f"Unexpected no-TOC fallback payload: {payload!r}")


def generate_toc_continue(toc_content, part, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_05_outline_fallback_generation/prompts/toc_generate_continue.txt")
    prompt = prompt + "\nGiven text\n:" + part + "\nPrevious tree structure\n:" + json.dumps(toc_content, indent=2)
    response, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt, json_response=True)
    if finish_reason == "finished":
        return _normalize_toc_items(json.loads(response))
    raise Exception(f"finish reason: {finish_reason}")


def generate_toc_init(part, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_05_outline_fallback_generation/prompts/toc_generate_init.txt")
    prompt = prompt + "\nGiven text\n:" + part
    response, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt, json_response=True)
    if finish_reason == "finished":
        return _normalize_toc_items(json.loads(response))
    raise Exception(f"finish reason: {finish_reason}")


def page_list_to_group_text(page_contents, token_lengths, max_tokens=20000, overlap_page=1):
    num_tokens = sum(token_lengths)
    if num_tokens <= max_tokens:
        return ["".join(page_contents)]

    subsets = []
    current_subset = []
    current_token_count = 0

    expected_parts_num = math.ceil(num_tokens / max_tokens)
    average_tokens_per_part = math.ceil(((num_tokens / expected_parts_num) + max_tokens) / 2)

    for index, (page_content, page_tokens) in enumerate(zip(page_contents, token_lengths)):
        if current_token_count + page_tokens > average_tokens_per_part:
            subsets.append("".join(current_subset))
            overlap_start = max(index - overlap_page, 0)
            current_subset = page_contents[overlap_start:index]
            current_token_count = sum(token_lengths[overlap_start:index])
        current_subset.append(page_content)
        current_token_count += page_tokens

    if current_subset:
        subsets.append("".join(current_subset))
    return subsets


def process_no_toc(page_list, start_index=1, model=None, logger=None):
    content_text = []
    token_list = []
    for index, (page_text, token_num) in enumerate(page_list):
        content_text.append(f"<physical_index_{index + start_index}>\n{page_text}\n<physical_index_{index + start_index}>\n\n")
        token_list.append(token_num)

    parts = page_list_to_group_text(content_text, token_list)
    if logger:
        logger.info(f"Split content into {len(parts)} parts for no-TOC processing")

    toc_content = generate_toc_init(parts[0], model=model)
    for part in parts[1:]:
        continued = generate_toc_continue(toc_content, part, model=model)
        toc_content.extend(continued)

    toc_content = convert_physical_index_to_int(toc_content)
    return remove_page_number(toc_content)
