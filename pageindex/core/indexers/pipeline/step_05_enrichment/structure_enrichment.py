from __future__ import annotations

import asyncio

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.utils.llm_caller import call_llm, call_llm_async
from pageindex.core.utils.pdf_reader import get_text_of_pdf_pages
from pageindex.core.utils.token_counter import count_tokens
from pageindex.core.utils.tree import structure_to_list


def add_node_text(node, pdf_pages, blocks=None):
    if isinstance(node, dict):
        sb = node.get("start_block")
        eb = node.get("end_block")
        if blocks is not None and sb is not None and eb is not None:
            node["text"] = _get_text_from_blocks(blocks, sb, eb)
        else:
            start_page = node.get("start_index")
            end_page = node.get("end_index")
            node["text"] = get_text_of_pdf_pages(pdf_pages, start_page, end_page)
        if "nodes" in node:
            add_node_text(node["nodes"], pdf_pages, blocks=blocks)
    elif isinstance(node, list):
        for item in node:
            add_node_text(item, pdf_pages, blocks=blocks)


def _get_text_from_blocks(blocks, start_block, end_block):
    return "\n".join(
        b["normalized_text"] for b in blocks
        if start_block <= b["block_no"] <= end_block
    )


def remove_structure_text(data):
    if isinstance(data, dict):
        data.pop("text", None)
        if "nodes" in data:
            remove_structure_text(data["nodes"])
    elif isinstance(data, list):
        for item in data:
            remove_structure_text(item)
    return data


async def generate_node_summary(node, model: str | None = None):
    title = node.get("title", "")
    if title:
        prompt = load_prompt(
            "step_05_enrichment/prompts/node_summary_with_title.txt",
            title=title,
            text=node["text"],
        )
    else:
        prompt = load_prompt("step_05_enrichment/prompts/node_summary.txt", text=node["text"])
    return await call_llm_async(model, prompt)


async def generate_summaries_for_structure(structure, model: str | None = None):
    nodes = structure_to_list(structure)
    tasks = [generate_node_summary(node, model=model) for node in nodes]
    summaries = await asyncio.gather(*tasks)
    for node, summary in zip(nodes, summaries):
        node["summary"] = summary
    return structure


async def _get_markdown_node_summary(node, summary_token_threshold: int = 200, model: str | None = None):
    node_text = node.get("text")
    num_tokens = count_tokens(node_text, model=model)
    if num_tokens < summary_token_threshold:
        return node_text
    return await generate_node_summary(node, model=model)


async def generate_summaries_for_markdown_structure(structure, summary_token_threshold: int, model: str | None = None):
    nodes = structure_to_list(structure)
    tasks = [
        _get_markdown_node_summary(node, summary_token_threshold=summary_token_threshold, model=model)
        for node in nodes
    ]
    summaries = await asyncio.gather(*tasks)

    for node, summary in zip(nodes, summaries):
        if not node.get("nodes"):
            node["summary"] = summary
        else:
            node["prefix_summary"] = summary
    return structure


def create_clean_structure_for_description(structure):
    if isinstance(structure, dict):
        clean_node = {}
        for key in ["title", "node_id", "summary", "prefix_summary"]:
            if key in structure:
                clean_node[key] = structure[key]
        if "nodes" in structure and structure["nodes"]:
            clean_node["nodes"] = create_clean_structure_for_description(structure["nodes"])
        return clean_node
    if isinstance(structure, list):
        return [create_clean_structure_for_description(item) for item in structure]
    return structure


def generate_doc_description(structure, model: str | None = None):
    prompt = load_prompt("step_05_enrichment/prompts/doc_description.txt", structure=structure)
    return call_llm(model, prompt)


def _reorder_dict(data, key_order):
    if not key_order:
        return data
    return {key: data[key] for key in key_order if key in data}


def format_structure(structure, order=None):
    if not order:
        return structure
    if isinstance(structure, dict):
        if "nodes" in structure:
            structure["nodes"] = format_structure(structure["nodes"], order)
        if not structure.get("nodes"):
            structure.pop("nodes", None)
        structure = _reorder_dict(structure, order)
    elif isinstance(structure, list):
        structure = [format_structure(item, order) for item in structure]
    return structure
