from __future__ import annotations

import asyncio
import os
from io import BytesIO

from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.core.indexers.pipeline.step_01_outline_discovery import check_toc
from pageindex.core.indexers.pipeline.step_02_outline_validation import (
    check_title_appearance_in_start_concurrent,
    resolve_pdf_outline,
)
from pageindex.core.indexers.pipeline.step_03_tree_construction import add_preface_if_needed, post_processing
from pageindex.core.indexers.pipeline.step_04_section_expansion import expand_pdf_sections
from pageindex.core.indexers.pipeline.step_05_enrichment import (
    add_node_text,
    create_clean_structure_for_description,
    generate_doc_description,
    generate_summaries_for_structure,
    remove_structure_text,
)
from pageindex.core.indexers.pipeline.step_06_finalize import build_index_result
from pageindex.core.utils.logger import get_logger
from pageindex.core.utils.pdf_reader import get_page_tokens, get_pdf_name
from pageindex.core.utils.tree import write_node_id


async def _build_pdf_tree(page_list, opt, logger=None):
    check_toc_result = check_toc(page_list, opt)
    if logger:
        logger.info(check_toc_result)

    if check_toc_result.get("toc_content") and check_toc_result["toc_content"].strip() and check_toc_result["page_index_given_in_toc"] == "yes":
        toc_with_page_number = await resolve_pdf_outline(
            page_list,
            mode="process_toc_with_page_numbers",
            start_index=1,
            toc_content=check_toc_result["toc_content"],
            toc_page_list=check_toc_result["toc_page_list"],
            opt=opt,
            logger=logger,
        )
    else:
        toc_with_page_number = await resolve_pdf_outline(
            page_list,
            mode="process_no_toc",
            start_index=1,
            opt=opt,
            logger=logger,
        )

    toc_with_page_number = add_preface_if_needed(toc_with_page_number)
    toc_with_page_number = await check_title_appearance_in_start_concurrent(
        toc_with_page_number,
        page_list,
        model=opt.model,
        logger=logger,
    )
    valid_toc_items = [item for item in toc_with_page_number if item.get("physical_index") is not None]

    toc_tree = post_processing(valid_toc_items, len(page_list))
    await expand_pdf_sections(toc_tree, page_list, opt, logger=logger)
    return toc_tree


class PdfAdapter:
    async def build(self, context: PipelineContext):
        logger = get_logger(
            "pageindex.pdf",
            doc_name=context.doc_name,
            source_path=str(context.source_path),
            provider_type=context.provider_type,
            model=context.model,
        )
        page_list = get_page_tokens(context.source_path)
        context.page_list = page_list
        context.logger = logger

        logger.info({"total_page_number": len(page_list)})
        logger.info({"total_token": sum(page[1] for page in page_list)})

        structure = await _build_pdf_tree(page_list, context.options, logger=logger)

        if context.options.if_add_node_id == "yes":
            write_node_id(structure)
        if context.options.if_add_node_text == "yes":
            add_node_text(structure, page_list)
        if context.options.if_add_node_summary == "yes":
            if context.options.if_add_node_text == "no":
                add_node_text(structure, page_list)
            await generate_summaries_for_structure(structure, model=context.model)
            if context.options.if_add_node_text == "no":
                remove_structure_text(structure)

        doc_description = None
        if context.options.if_add_doc_description == "yes":
            if context.options.if_add_node_summary == "no":
                if context.options.if_add_node_text == "no":
                    add_node_text(structure, page_list)
                await generate_summaries_for_structure(structure, model=context.model)
                if context.options.if_add_node_text == "no":
                    remove_structure_text(structure)
            clean_structure = create_clean_structure_for_description(structure)
            doc_description = generate_doc_description(clean_structure, model=context.model)

        return build_index_result(
            doc_name=context.doc_name or get_pdf_name(context.source_path),
            structure=structure,
            doc_description=doc_description,
        )


def page_index_main(doc, opt=None):
    from pageindex.core.indexers.document_indexer import IndexingOptions

    is_valid_pdf = (
        (isinstance(doc, str) and os.path.isfile(doc) and doc.lower().endswith(".pdf")) or
        isinstance(doc, BytesIO)
    )
    if not is_valid_pdf:
        raise ValueError("Unsupported input type. Expected a PDF file path or BytesIO object.")

    options = opt if isinstance(opt, IndexingOptions) else IndexingOptions.from_raw(vars(opt) if opt is not None else {})
    context = PipelineContext(
        source_path=doc,
        provider_type="openai",
        model=options.model,
        options=options,
        llm_client=None,
        doc_name=get_pdf_name(doc),
    )

    async def _run():
        return await PdfAdapter().build(context)

    return asyncio.run(_run())


def page_index(
    doc,
    model=None,
    toc_check_page_num=None,
    max_page_num_each_node=None,
    max_token_num_each_node=None,
    if_add_node_id=None,
    if_add_node_summary=None,
    if_add_doc_description=None,
    if_add_node_text=None,
):
    from pageindex.core.indexers.document_indexer import IndexingOptions

    user_opt = {
        arg: value for arg, value in locals().items()
        if arg != "doc" and value is not None
    }
    return page_index_main(doc, IndexingOptions.from_raw(user_opt))
