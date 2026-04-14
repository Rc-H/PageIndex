"""Block-level outline generation for small/medium PDF documents.

Analogous to ``process_no_toc`` in the page-based fallback path, but uses
block-level markers (<block_N>) instead of page markers (<physical_index_N>).

The output is a flat list of nodes with ``structure``, ``title``, and
``start_block_no`` — ready for tree construction via ``build_tree_from_nodes``
after being converted to the ``start_index``/``end_index`` shape.
"""

from __future__ import annotations

import json
import math
from typing import Any

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.utils.llm_caller import call_llm_with_finish_reason


def process_block_outline(
    blocks: list[dict[str, Any]],
    model: str | None = None,
    logger=None,
) -> list[dict[str, Any]]:
    """Generate a hierarchical outline from block-annotated PDF content.

    Returns a flat list of ``{structure, title, start_block_no}`` dicts.
    """
    if not blocks:
        return []

    content_parts, block_ranges = _blocks_to_group_text(blocks)
    if logger:
        logger.info(f"Split blocks into {len(content_parts)} parts for block-outline processing")

    first_range = block_ranges[0]
    toc_content = _generate_init(content_parts[0], first_range[0], first_range[1], model=model)

    for part, (sb, eb) in zip(content_parts[1:], block_ranges[1:]):
        continued = _generate_continue(toc_content, part, sb, eb, model=model)
        toc_content.extend(continued)

    return _validate_block_nos(toc_content, blocks)


def _blocks_to_group_text(
    blocks: list[dict[str, Any]],
    max_tokens: int = 20000,
    overlap_blocks: int = 2,
) -> tuple[list[str], list[tuple[int, int]]]:
    """Group blocks into text chunks with <block_N> markers.

    Returns ``(text_parts, block_ranges)`` where each ``block_ranges[i]``
    is ``(start_block_no, end_block_no)`` for that part.
    """
    annotated = []
    token_counts = []
    for b in blocks:
        text = f"<block_{b['block_no']}>\n{b['normalized_text']}\n</block_{b['block_no']}>"
        annotated.append(text)
        token_counts.append(b["token_count"])

    total_tokens = sum(token_counts)
    if total_tokens <= max_tokens:
        all_text = "\n\n".join(annotated)
        return [all_text], [(blocks[0]["block_no"], blocks[-1]["block_no"])]

    parts: list[str] = []
    ranges: list[tuple[int, int]] = []

    expected_num = math.ceil(total_tokens / max_tokens)
    avg_per_part = math.ceil(((total_tokens / expected_num) + max_tokens) / 2)

    current_texts: list[str] = []
    current_tokens = 0
    part_start_idx = 0

    for i, (text, tok) in enumerate(zip(annotated, token_counts)):
        if current_tokens + tok > avg_per_part and current_texts:
            parts.append("\n\n".join(current_texts))
            ranges.append((blocks[part_start_idx]["block_no"], blocks[i - 1]["block_no"]))

            overlap_start = max(i - overlap_blocks, 0)
            current_texts = list(annotated[overlap_start:i])
            current_tokens = sum(token_counts[overlap_start:i])
            part_start_idx = overlap_start

        current_texts.append(text)
        current_tokens += tok

    if current_texts:
        parts.append("\n\n".join(current_texts))
        ranges.append((blocks[part_start_idx]["block_no"], blocks[-1]["block_no"]))

    return parts, ranges


def _normalize_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("result")
        if isinstance(items, list):
            return items
    raise ValueError(f"Unexpected block outline payload: {payload!r}")


def _generate_init(part: str, start_block: int, end_block: int, model=None) -> list[dict[str, Any]]:
    prompt = load_prompt(
        "step_01_outline_discovery/step_06_block_outline/prompts/block_toc_generate.txt",
        start_block=start_block,
        end_block=end_block,
    )
    prompt = prompt + "\nGiven content:\n" + part
    result = call_llm_with_finish_reason(model=model, prompt=prompt, json_response=True)
    if not isinstance(result, tuple):
        raise ValueError(f"Block outline init: LLM returned error")
    response, finish_reason = result
    if finish_reason == "finished":
        return _normalize_items(json.loads(response))
    raise ValueError(f"Block outline init: finish reason={finish_reason}")


def _generate_continue(
    toc_content: list[dict[str, Any]],
    part: str,
    start_block: int,
    end_block: int,
    model=None,
) -> list[dict[str, Any]]:
    prompt = load_prompt(
        "step_01_outline_discovery/step_06_block_outline/prompts/block_toc_generate_continue.txt",
    )
    prompt = (
        prompt
        + "\nGiven content:\n"
        + part
        + "\nPrevious tree structure:\n"
        + json.dumps(toc_content, indent=2)
    )
    result = call_llm_with_finish_reason(model=model, prompt=prompt, json_response=True)
    if not isinstance(result, tuple):
        raise ValueError(f"Block outline continue: LLM returned error")
    response, finish_reason = result
    if finish_reason == "finished":
        return _normalize_items(json.loads(response))
    raise ValueError(f"Block outline continue: finish reason={finish_reason}")


def _validate_block_nos(
    items: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter items with invalid block numbers and ensure monotonic order."""
    valid_block_nos = {b["block_no"] for b in blocks}
    min_bno = min(valid_block_nos)
    max_bno = max(valid_block_nos)

    validated = []
    for item in items:
        bno = item.get("start_block_no")
        if not isinstance(bno, int):
            continue
        if bno < min_bno or bno > max_bno:
            continue
        validated.append(item)

    # Ensure monotonically increasing
    result = []
    last_bno = -1
    for item in validated:
        if item["start_block_no"] > last_bno:
            result.append(item)
            last_bno = item["start_block_no"]

    return result
