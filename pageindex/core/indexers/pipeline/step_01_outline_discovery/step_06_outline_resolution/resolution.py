from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_02_toc_content_extraction import extract_toc_content
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_03_toc_structure_parsing import toc_transformer
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_04_outline_index_alignment import (
    add_page_number_to_toc,
    add_page_offset_to_toc_json,
    calculate_page_offset,
    extract_matching_page_pairs,
    process_none_page_numbers,
    remove_page_number,
    toc_index_extractor,
)
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_05_outline_fallback_generation import process_no_toc


def process_toc_no_page_numbers(toc_content, toc_page_list, page_list, start_index=1, model=None, logger=None):
    extracted_toc = extract_toc_content(toc_content, model=model)
    toc_json = toc_transformer(extracted_toc, model=model)
    page_pairs = process_none_page_numbers(toc_json, page_list, start_index=start_index, model=model)
    offset = calculate_page_offset(page_pairs)
    if offset is None:
        return process_no_toc(page_list, start_index=start_index, model=model, logger=logger)
    toc_json = add_page_offset_to_toc_json(toc_json, offset)
    return remove_page_number(toc_json)


def process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=None, model=None, logger=None):
    extracted_toc = extract_toc_content(toc_content, model=model)
    toc_json = toc_transformer(extracted_toc, model=model)
    toc_page = toc_index_extractor(toc_json, toc_content, model=model)
    toc_physical_index = add_page_number_to_toc(toc_content, toc_json, model=model)
    pairs = extract_matching_page_pairs(toc_page, toc_physical_index, toc_page_list[0] + 1)
    offset = calculate_page_offset(pairs)
    if offset is None:
        return process_toc_no_page_numbers(toc_content, toc_page_list, page_list, start_index=1, model=model, logger=logger)
    toc_json = add_page_offset_to_toc_json(toc_json, offset)
    return remove_page_number(toc_json)
