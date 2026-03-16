import asyncio
import os
import random
from io import BytesIO

from pageindex.core.indexers.toc.extractor import (
    check_toc,
    process_no_toc,
    process_toc_no_page_numbers,
    process_toc_with_page_numbers,
)
from pageindex.core.indexers.toc.fixer import fix_incorrect_toc_with_retries
from pageindex.core.indexers.validation.title_validator import (
    check_title_appearance,
    check_title_appearance_in_start_concurrent,
)
from pageindex.core.utils.config import ConfigLoader
from pageindex.core.utils.logger import JsonLogger
from pageindex.core.utils.pdf_reader import get_page_tokens, get_pdf_name
from pageindex.core.utils.structure_ops import (
    add_node_text,
    add_preface_if_needed,
    create_clean_structure_for_description,
    generate_doc_description,
    generate_summaries_for_structure,
    post_processing,
    remove_structure_text,
)
from pageindex.core.utils.tree import write_node_id


def validate_and_truncate_physical_indices(toc_with_page_number, page_list_length, start_index=1, logger=None):
    if not toc_with_page_number:
        return toc_with_page_number

    max_allowed_page = page_list_length + start_index - 1
    truncated_items = []

    for item in toc_with_page_number:
        if item.get('physical_index') is not None:
            original_index = item['physical_index']
            if original_index > max_allowed_page:
                item['physical_index'] = None
                truncated_items.append({'title': item.get('title', 'Unknown'), 'original_index': original_index})
                if logger:
                    logger.info(f"Removed physical_index for '{item.get('title', 'Unknown')}' (was {original_index}, too far beyond document)")

    if truncated_items and logger:
        logger.info(f"Total removed items: {len(truncated_items)}")
    return toc_with_page_number


async def verify_toc(page_list, list_result, start_index=1, N=None, model=None):
    last_physical_index = None
    for item in reversed(list_result):
        if item.get('physical_index') is not None:
            last_physical_index = item['physical_index']
            break

    if last_physical_index is None or last_physical_index < len(page_list) / 2:
        return 0, []

    if N is None:
        sample_indices = range(0, len(list_result))
    else:
        N = min(N, len(list_result))
        sample_indices = random.sample(range(0, len(list_result)), N)

    indexed_sample_list = []
    for idx in sample_indices:
        item = list_result[idx]
        if item.get('physical_index') is not None:
            item_with_index = item.copy()
            item_with_index['list_index'] = idx
            indexed_sample_list.append(item_with_index)

    tasks = [check_title_appearance(item, page_list, start_index, model) for item in indexed_sample_list]
    results = await asyncio.gather(*tasks)

    correct_count = sum(1 for r in results if r['answer'] == 'yes')
    incorrect_results = [r for r in results if r['answer'] != 'yes']
    accuracy = correct_count / len(results) if results else 0
    return accuracy, incorrect_results


async def meta_processor(page_list, mode=None, toc_content=None, toc_page_list=None, start_index=1, opt=None, logger=None):
    if mode == 'process_toc_with_page_numbers':
        toc_with_page_number = process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=opt.toc_check_page_num, model=opt.model, logger=logger)
    elif mode == 'process_toc_no_page_numbers':
        toc_with_page_number = process_toc_no_page_numbers(toc_content, toc_page_list, page_list, model=opt.model, logger=logger)
    else:
        toc_with_page_number = process_no_toc(page_list, start_index=start_index, model=opt.model, logger=logger)

    toc_with_page_number = [item for item in toc_with_page_number if item.get('physical_index') is not None]
    toc_with_page_number = validate_and_truncate_physical_indices(toc_with_page_number, len(page_list), start_index=start_index, logger=logger)

    accuracy, incorrect_results = await verify_toc(page_list, toc_with_page_number, start_index=start_index, model=opt.model)

    logger.info({'mode': mode, 'accuracy': accuracy, 'incorrect_results': incorrect_results})
    if accuracy == 1.0 and not incorrect_results:
        return toc_with_page_number
    if accuracy > 0.6 and incorrect_results:
        toc_with_page_number, _ = await fix_incorrect_toc_with_retries(toc_with_page_number, page_list, incorrect_results, start_index=start_index, max_attempts=3, model=opt.model, logger=logger)
        return toc_with_page_number

    if mode == 'process_toc_with_page_numbers':
        return await meta_processor(page_list, mode='process_toc_no_page_numbers', toc_content=toc_content, toc_page_list=toc_page_list, start_index=start_index, opt=opt, logger=logger)
    if mode == 'process_toc_no_page_numbers':
        return await meta_processor(page_list, mode='process_no_toc', start_index=start_index, opt=opt, logger=logger)
    raise Exception('Processing failed')


async def process_large_node_recursively(node, page_list, opt=None, logger=None):
    node_page_list = page_list[node['start_index'] - 1:node['end_index']]
    token_num = sum(page[1] for page in node_page_list)

    if node['end_index'] - node['start_index'] > opt.max_page_num_each_node and token_num >= opt.max_token_num_each_node:
        node_toc_tree = await meta_processor(node_page_list, mode='process_no_toc', start_index=node['start_index'], opt=opt, logger=logger)
        node_toc_tree = await check_title_appearance_in_start_concurrent(node_toc_tree, page_list, model=opt.model, logger=logger)
        valid_node_toc_items = [item for item in node_toc_tree if item.get('physical_index') is not None]

        if valid_node_toc_items and node['title'].strip() == valid_node_toc_items[0]['title'].strip():
            node['nodes'] = post_processing(valid_node_toc_items[1:], node['end_index'])
            node['end_index'] = valid_node_toc_items[1]['start_index'] if len(valid_node_toc_items) > 1 else node['end_index']
        else:
            node['nodes'] = post_processing(valid_node_toc_items, node['end_index'])
            node['end_index'] = valid_node_toc_items[0]['start_index'] if valid_node_toc_items else node['end_index']

    if 'nodes' in node and node['nodes']:
        tasks = [process_large_node_recursively(child, page_list, opt, logger=logger) for child in node['nodes']]
        await asyncio.gather(*tasks)
    return node


async def tree_parser(page_list, opt, doc=None, logger=None):
    check_toc_result = check_toc(page_list, opt)
    logger.info(check_toc_result)

    if check_toc_result.get("toc_content") and check_toc_result["toc_content"].strip() and check_toc_result["page_index_given_in_toc"] == "yes":
        toc_with_page_number = await meta_processor(page_list, mode='process_toc_with_page_numbers', start_index=1, toc_content=check_toc_result['toc_content'], toc_page_list=check_toc_result['toc_page_list'], opt=opt, logger=logger)
    else:
        toc_with_page_number = await meta_processor(page_list, mode='process_no_toc', start_index=1, opt=opt, logger=logger)

    toc_with_page_number = add_preface_if_needed(toc_with_page_number)
    toc_with_page_number = await check_title_appearance_in_start_concurrent(toc_with_page_number, page_list, model=opt.model, logger=logger)
    valid_toc_items = [item for item in toc_with_page_number if item.get('physical_index') is not None]

    toc_tree = post_processing(valid_toc_items, len(page_list))
    tasks = [process_large_node_recursively(node, page_list, opt, logger=logger) for node in toc_tree]
    await asyncio.gather(*tasks)
    return toc_tree


def page_index_main(doc, opt=None):
    logger = JsonLogger(doc)

    is_valid_pdf = (
        (isinstance(doc, str) and os.path.isfile(doc) and doc.lower().endswith(".pdf")) or
        isinstance(doc, BytesIO)
    )
    if not is_valid_pdf:
        raise ValueError("Unsupported input type. Expected a PDF file path or BytesIO object.")

    page_list = get_page_tokens(doc)
    logger.info({'total_page_number': len(page_list)})
    logger.info({'total_token': sum(page[1] for page in page_list)})

    async def page_index_builder():
        structure = await tree_parser(page_list, opt, doc=doc, logger=logger)
        if opt.if_add_node_id == 'yes':
            write_node_id(structure)
        if opt.if_add_node_text == 'yes':
            add_node_text(structure, page_list)
        if opt.if_add_node_summary == 'yes':
            if opt.if_add_node_text == 'no':
                add_node_text(structure, page_list)
            await generate_summaries_for_structure(structure, model=opt.model)
            if opt.if_add_node_text == 'no':
                remove_structure_text(structure)
            if opt.if_add_doc_description == 'yes':
                clean_structure = create_clean_structure_for_description(structure)
                doc_description = generate_doc_description(clean_structure, model=opt.model)
                return {'doc_name': get_pdf_name(doc), 'doc_description': doc_description, 'structure': structure}
        return {'doc_name': get_pdf_name(doc), 'structure': structure}

    return asyncio.run(page_index_builder())


def page_index(doc, model=None, toc_check_page_num=None, max_page_num_each_node=None, max_token_num_each_node=None,
               if_add_node_id=None, if_add_node_summary=None, if_add_doc_description=None, if_add_node_text=None):
    user_opt = {
        arg: value for arg, value in locals().items()
        if arg != "doc" and value is not None
    }
    opt = ConfigLoader().load(user_opt)
    return page_index_main(doc, opt)
