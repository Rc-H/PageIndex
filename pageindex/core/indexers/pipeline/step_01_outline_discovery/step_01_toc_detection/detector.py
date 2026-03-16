import json

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_02_toc_content_extraction import toc_extractor
from pageindex.core.utils.llm_caller import call_llm


def toc_detector_single_page(content, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_01_toc_detection/prompts/toc_detect_single_page.txt", content=content)
    response = call_llm(model=model, prompt=prompt, json_response=True)
    return json.loads(response)["toc_detected"]


def find_toc_pages(start_page_index, page_list, opt, logger=None):
    last_page_is_yes = False
    toc_page_list = []
    page_index = start_page_index

    while page_index < len(page_list):
        if page_index >= opt.toc_check_page_num and not last_page_is_yes:
            break
        detected_result = toc_detector_single_page(page_list[page_index][0], model=opt.model)
        if detected_result == "yes":
            if logger:
                logger.info(f"Page {page_index} has toc")
            toc_page_list.append(page_index)
            last_page_is_yes = True
        elif detected_result == "no" and last_page_is_yes:
            if logger:
                logger.info(f"Found the last page with toc: {page_index - 1}")
            break
        page_index += 1

    if not toc_page_list and logger:
        logger.info("No toc found")
    return toc_page_list


def check_toc(page_list, opt=None):
    toc_page_list = find_toc_pages(start_page_index=0, page_list=page_list, opt=opt)
    if not toc_page_list:
        return {"toc_content": None, "toc_page_list": [], "page_index_given_in_toc": "no"}

    toc_json = toc_extractor(page_list, toc_page_list, opt.model)
    if toc_json["page_index_given_in_toc"] == "yes":
        return {"toc_content": toc_json["toc_content"], "toc_page_list": toc_page_list, "page_index_given_in_toc": "yes"}

    current_start_index = toc_page_list[-1] + 1
    while (
        toc_json["page_index_given_in_toc"] == "no"
        and current_start_index < len(page_list)
        and current_start_index < opt.toc_check_page_num
    ):
        additional_toc_pages = find_toc_pages(start_page_index=current_start_index, page_list=page_list, opt=opt)
        if not additional_toc_pages:
            break
        additional_toc_json = toc_extractor(page_list, additional_toc_pages, opt.model)
        if additional_toc_json["page_index_given_in_toc"] == "yes":
            return {
                "toc_content": additional_toc_json["toc_content"],
                "toc_page_list": additional_toc_pages,
                "page_index_given_in_toc": "yes",
            }
        current_start_index = additional_toc_pages[-1] + 1

    return {"toc_content": toc_json["toc_content"], "toc_page_list": toc_page_list, "page_index_given_in_toc": "no"}
