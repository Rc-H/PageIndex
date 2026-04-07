"""Finalize raw Word blocks into PDF-shape block dicts.

Owns ALL the index/offset arithmetic for Word blocks: char offset
accumulation across the doc and within each section, token counting,
``block_no`` / ``block_order_in_page`` assignment, and the
``metadata.pageindex_node_id`` link to the structure tree.

All blocks emit ``metadata.type = "text"`` regardless of source — Word
tables are textualized by ``word_tables`` and treated identically to
paragraphs at this layer.
"""

from __future__ import annotations

from typing import Any

from pageindex.core.utils.token_counter import count_tokens


PAGEINDEX_NODE_ID_METADATA_KEY = "pageindex_node_id"
TEXT_METADATA_TYPE = "text"


def finalize_word_blocks(
    raw_blocks: list[dict[str, Any]],
    tree_structure: list[dict[str, Any]],
    model: str | None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Convert raw blocks into PDF-shape block dicts.

    Returns ``(blocks, char_count, token_count)`` where ``char_count`` is the
    sum of ``len(normalized_text)`` and ``token_count`` is the sum of per-block
    token counts.
    """

    section_to_node_id = _build_section_to_node_id_map(tree_structure)
    surviving_blocks = _strip_empty_blocks(raw_blocks)

    finalized: list[dict[str, Any]] = []
    block_no = 0
    doc_char_offset = 0
    page_char_offset = 0
    block_order_in_page = 0
    last_section_ordinal: int | None = None
    total_char_count = 0
    total_token_count = 0

    for raw in surviving_blocks:
        section_ordinal = raw["section_ordinal"]
        normalized_text = raw["normalized_text"]
        char_count = len(normalized_text)

        if section_ordinal != last_section_ordinal:
            page_char_offset = 0
            block_order_in_page = 0
            last_section_ordinal = section_ordinal

        if block_no > 0:
            doc_char_offset += 1
        if block_order_in_page > 0:
            page_char_offset += 1

        block_no += 1
        block_order_in_page += 1
        token_count = count_tokens(normalized_text, model=model)

        finalized.append({
            "block_no": block_no,
            "page_no": section_ordinal,
            "block_order_in_page": block_order_in_page,
            "start_index": section_ordinal,
            "end_index": section_ordinal,
            "raw_content": raw["raw_text"],
            "normalized_text": normalized_text,
            "display_text": raw["raw_text"],
            "char_start_in_doc": doc_char_offset,
            "char_end_in_doc": doc_char_offset + char_count - 1 if char_count else doc_char_offset,
            "char_start_in_page": page_char_offset,
            "char_end_in_page": page_char_offset + char_count - 1 if char_count else page_char_offset,
            "token_count": token_count,
            "metadata": {
                "type": TEXT_METADATA_TYPE,
                PAGEINDEX_NODE_ID_METADATA_KEY: section_to_node_id.get(section_ordinal),
            },
        })

        doc_char_offset += char_count
        page_char_offset += char_count
        total_char_count += char_count
        total_token_count += token_count

    return finalized, total_char_count, total_token_count


def _strip_empty_blocks(raw_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    surviving = []
    for raw in raw_blocks:
        normalized_text = (raw.get("raw_text") or "").strip()
        if not normalized_text:
            continue
        surviving.append({
            "section_ordinal": raw["section_ordinal"],
            "raw_text": raw["raw_text"],
            "normalized_text": normalized_text,
            "source": raw.get("source"),
        })
    return surviving


def _build_section_to_node_id_map(tree_structure: list[dict[str, Any]]) -> dict[int, str | None]:
    """Map each section ordinal to the deepest node whose range contains it.

    Walks the tree post-order and accumulates candidates. For each section
    ordinal, the candidate with the largest depth wins (leaf preferred over
    parent). Sections that fall outside every node's range map to ``None``.
    """

    candidates: list[tuple[int, str | None, int, int]] = []  # (depth, node_id, start, end)

    def walk(nodes, depth):
        for node in nodes:
            start = node.get("start_index")
            end = node.get("end_index")
            node_id = node.get("node_id")
            if start is not None and end is not None:
                candidates.append((depth, node_id, start, end))
            children = node.get("nodes") or []
            if children:
                walk(children, depth + 1)

    walk(tree_structure, depth=0)

    if not candidates:
        return {}

    all_sections = {
        section
        for _, _, start, end in candidates
        for section in range(start, end + 1)
    }

    result: dict[int, str | None] = {}
    for section in all_sections:
        best: tuple[int, str | None] | None = None
        for depth, node_id, start, end in candidates:
            if start <= section <= end:
                if best is None or depth > best[0]:
                    best = (depth, node_id)
        result[section] = best[1] if best else None

    return result


__all__ = [
    "PAGEINDEX_NODE_ID_METADATA_KEY",
    "TEXT_METADATA_TYPE",
    "finalize_word_blocks",
]
