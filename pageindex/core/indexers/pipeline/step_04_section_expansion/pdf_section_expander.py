from __future__ import annotations

import asyncio

from pageindex.core.indexers.pipeline.step_02_outline_validation import (
    check_title_appearance_in_start_concurrent,
    resolve_pdf_outline,
)
from pageindex.core.indexers.pipeline.step_03_tree_construction import post_processing


async def _process_large_node_recursively(node, page_list, opt=None, logger=None):
    node_page_list = page_list[node["start_index"] - 1:node["end_index"]]
    token_num = sum(page[1] for page in node_page_list)

    if node["end_index"] - node["start_index"] > opt.max_page_num_each_node and token_num >= opt.max_token_num_each_node:
        node_toc_tree = await resolve_pdf_outline(
            node_page_list,
            mode="process_no_toc",
            start_index=node["start_index"],
            opt=opt,
            logger=logger,
        )
        node_toc_tree = await check_title_appearance_in_start_concurrent(node_toc_tree, page_list, model=opt.model, logger=logger)
        valid_node_toc_items = [item for item in node_toc_tree if item.get("physical_index") is not None]

        if valid_node_toc_items and node["title"].strip() == valid_node_toc_items[0]["title"].strip():
            node["nodes"] = post_processing(valid_node_toc_items[1:], node["end_index"])
            node["end_index"] = valid_node_toc_items[1]["start_index"] if len(valid_node_toc_items) > 1 else node["end_index"]
        else:
            node["nodes"] = post_processing(valid_node_toc_items, node["end_index"])
            node["end_index"] = valid_node_toc_items[0]["start_index"] if valid_node_toc_items else node["end_index"]

    if node.get("nodes"):
        tasks = [_process_large_node_recursively(child, page_list, opt, logger=logger) for child in node["nodes"]]
        await asyncio.gather(*tasks)
    return node


async def expand_pdf_sections(tree, page_list, opt=None, logger=None):
    tasks = [_process_large_node_recursively(node, page_list, opt, logger=logger) for node in tree]
    await asyncio.gather(*tasks)
    return tree
