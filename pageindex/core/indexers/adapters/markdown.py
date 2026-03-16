from __future__ import annotations

import os

from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.core.indexers.pipeline.step_01_outline_discovery import (
    extract_node_text_content,
    extract_nodes_from_markdown,
    tree_thinning_for_index,
    update_node_list_with_text_token_count,
)
from pageindex.core.indexers.pipeline.step_03_tree_construction import build_tree_from_nodes
from pageindex.core.indexers.pipeline.step_05_enrichment import (
    create_clean_structure_for_description,
    format_structure,
    generate_doc_description,
    generate_summaries_for_markdown_structure,
)
from pageindex.core.indexers.pipeline.step_06_finalize import build_index_result
from pageindex.core.utils.tree import write_node_id


class MarkdownAdapter:
    async def build(self, context: PipelineContext):
        md_path = str(context.source_path)
        with open(md_path, "r", encoding="utf-8") as handle:
            markdown_content = handle.read()

        node_list, markdown_lines = extract_nodes_from_markdown(markdown_content)
        nodes_with_content = extract_node_text_content(node_list, markdown_lines)

        if context.options.if_thinning == "yes":
            nodes_with_content = update_node_list_with_text_token_count(nodes_with_content, model=context.model)
            nodes_with_content = tree_thinning_for_index(
                nodes_with_content,
                context.options.thinning_threshold,
                model=context.model,
            )

        tree_structure = build_tree_from_nodes(nodes_with_content)

        if context.options.if_add_node_id == "yes":
            write_node_id(tree_structure)

        if context.options.if_add_node_summary == "yes":
            tree_structure = format_structure(
                tree_structure,
                order=["title", "node_id", "summary", "prefix_summary", "text", "line_num", "nodes"],
            )
            tree_structure = await generate_summaries_for_markdown_structure(
                tree_structure,
                summary_token_threshold=context.options.summary_token_threshold,
                model=context.model,
            )

            if context.options.if_add_node_text == "no":
                tree_structure = format_structure(
                    tree_structure,
                    order=["title", "node_id", "summary", "prefix_summary", "line_num", "nodes"],
                )
        elif context.options.if_add_node_text == "yes":
            tree_structure = format_structure(
                tree_structure,
                order=["title", "node_id", "text", "line_num", "nodes"],
            )
        else:
            tree_structure = format_structure(
                tree_structure,
                order=["title", "node_id", "line_num", "nodes"],
            )

        doc_description = None
        if context.options.if_add_doc_description == "yes":
            clean_structure = create_clean_structure_for_description(tree_structure)
            doc_description = generate_doc_description(clean_structure, model=context.model)

        doc_name = context.doc_name or os.path.splitext(os.path.basename(md_path))[0]
        return build_index_result(doc_name=doc_name, structure=tree_structure, doc_description=doc_description)
