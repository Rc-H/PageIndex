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
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_06_block_outline import process_block_outline
from pageindex.core.indexers.pipeline.step_03_tree_construction import add_preface_if_needed, build_block_tree, post_processing
from pageindex.core.indexers.pipeline.step_04_section_expansion import expand_pdf_sections
from pageindex.core.indexers.pipeline.step_05_enrichment import (
    add_node_text,
    create_clean_structure_for_description,
    generate_doc_description,
    generate_summaries_for_structure,
    remove_structure_text,
)
from pageindex.core.indexers.pipeline.step_06_finalize import (
    PAGEINDEX_NODE_ID_KEY,
    attach_block_node_ids,
    attach_block_node_ids_by_block_range,
    build_index_result,
)
from pageindex.core.utils.logger import get_logger
from pageindex.core.utils.pdf_reader import extract_pdf_blocks, get_page_tokens, get_pdf_name
from pageindex.core.utils.pdf import _extract_tables_by_page
from pageindex.core.utils.tree import write_node_id
from pageindex.infrastructure.settings import load_settings


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
        logger, page_list = _initialize_pdf_context(context)

        if _should_use_block_granularity(context.options, page_list):
            return await self._build_block_granularity(context, page_list, logger)
        return await self._build_page_granularity(context, page_list, logger)

    async def _build_page_granularity(self, context, page_list, logger):
        """Original page-level flow for large documents."""
        structure = await _build_pdf_structure(context, page_list, logger)
        blocks = _build_pdf_blocks(context, structure)
        # context.blocks stays None — page-granularity uses page ranges for text
        await _enrich_pdf_structure(context, structure, page_list)
        doc_description = await _build_pdf_doc_description(context, structure, page_list)
        return _build_pdf_result(context, structure, blocks, doc_description, page_list)

    async def _build_block_granularity(self, context, page_list, logger):
        """Block-level flow for small/medium documents (Word-style)."""
        # 1. Extract blocks first (before outline)
        blocks = extract_pdf_blocks(
            context.source_path,
            model=context.model,
            tables_by_page=context.pdf_tables_by_page,
        )
        if logger:
            logger.info({"block_granularity": True, "total_blocks": len(blocks)})

        # 2. Generate outline from block-annotated text (like Word heading extraction)
        outline_items = process_block_outline(blocks, model=context.model, logger=logger)

        # 3. Build tree from outline (like Word's build_tree_from_nodes)
        structure = build_block_tree(outline_items, blocks)

        # 4. Assign node IDs
        if context.options.if_add_node_id == "yes":
            write_node_id(structure)

        # 5. Attach block-to-node mapping (like Word's section_to_node_id)
        attach_block_node_ids_by_block_range(blocks, structure)

        # 6. Enrich with summaries (using block-level text)
        context.blocks = blocks
        await _enrich_pdf_structure(context, structure, page_list)
        doc_description = await _build_pdf_doc_description(context, structure, page_list)

        return _build_pdf_result(context, structure, blocks, doc_description, page_list)


def _initialize_pdf_context(context: PipelineContext):
    logger = get_logger(
        "pageindex.pdf",
        doc_name=context.doc_name,
        source_path=str(context.source_path),
        provider_type=context.provider_type,
        model=context.model,
    )
    pdf_tables_by_page = _extract_tables_by_page(context.source_path, model=context.model)
    page_list = get_page_tokens(context.source_path, model=context.model, tables_by_page=pdf_tables_by_page)
    context.page_list = page_list
    context.pdf_tables_by_page = pdf_tables_by_page
    context.logger = logger

    logger.info({"total_page_number": len(page_list)})
    logger.info({"total_token": sum(page[1] for page in page_list)})
    return logger, page_list


async def _build_pdf_structure(context: PipelineContext, page_list, logger):
    structure = await _build_pdf_tree(page_list, context.options, logger=logger)
    if context.options.if_add_node_id == "yes":
        write_node_id(structure)
    return structure


def _build_pdf_blocks(context: PipelineContext, structure):
    blocks = extract_pdf_blocks(
        context.source_path,
        model=context.model,
        tables_by_page=context.pdf_tables_by_page,
    )
    attach_block_node_ids(blocks, structure)
    return blocks


async def _enrich_pdf_structure(context: PipelineContext, structure, page_list):
    blocks = context.blocks
    if context.options.if_add_node_text == "yes":
        add_node_text(structure, page_list, blocks=blocks)
    if context.options.if_add_node_summary == "yes":
        if context.options.if_add_node_text == "no":
            add_node_text(structure, page_list, blocks=blocks)
        await generate_summaries_for_structure(structure, model=context.model)
        if context.options.if_add_node_text == "no":
            remove_structure_text(structure)


async def _build_pdf_doc_description(context: PipelineContext, structure, page_list):
    if context.options.if_add_doc_description != "yes":
        return None

    blocks = context.blocks
    if context.options.if_add_node_summary == "no":
        if context.options.if_add_node_text == "no":
            add_node_text(structure, page_list, blocks=blocks)
        await generate_summaries_for_structure(structure, model=context.model)
        if context.options.if_add_node_text == "no":
            remove_structure_text(structure)

    clean_structure = create_clean_structure_for_description(structure)
    return generate_doc_description(clean_structure, model=context.model)


def _build_pdf_result(context: PipelineContext, structure, blocks, doc_description, page_list):
    return build_index_result(
        doc_name=context.doc_name or get_pdf_name(context.source_path),
        structure=structure,
        doc_description=doc_description,
        page_count=len(page_list),
        char_count=(blocks[-1]["char_end_in_doc"] + 1) if blocks else 0,
        token_count=sum(block["token_count"] for block in blocks),
        extract={"blocks": blocks},
        content_images=_build_content_images(blocks),
    )


def _build_content_images(blocks):
    content_images = []
    for block in blocks:
        image = (block.get("metadata") or {}).get("image") or {}
        attachment_id = image.get("attachment_id")
        file_name = image.get("file_name")
        page_no = block.get("page_no")
        block_no = block.get("block_no")
        if not attachment_id or not file_name or not page_no or not block_no:
            continue
        content_images.append(
            {
                "page_no": page_no,
                "block_no": block_no,
                "file_name": file_name,
                "attachment_id": attachment_id,
            }
        )
    return content_images


def _should_use_block_granularity(options, page_list):
    threshold = options.block_granularity_page_threshold
    return threshold > 0 and len(page_list) <= threshold


def page_index_main(doc, opt=None):
    from pageindex.core.indexers.document_indexer import IndexingOptions

    is_valid_pdf = (
        (isinstance(doc, str) and os.path.isfile(doc) and doc.lower().endswith(".pdf")) or
        isinstance(doc, BytesIO)
    )
    if not is_valid_pdf:
        raise ValueError("Unsupported input type. Expected a PDF file path or BytesIO object.")

    llm_settings = load_settings().llm
    raw_options = {"model": llm_settings.model}
    if opt is not None and not isinstance(opt, IndexingOptions):
        raw_options.update(vars(opt))
    options = opt if isinstance(opt, IndexingOptions) else IndexingOptions.from_raw(raw_options)
    context = PipelineContext(
        source_path=doc,
        provider_type=llm_settings.provider,
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
