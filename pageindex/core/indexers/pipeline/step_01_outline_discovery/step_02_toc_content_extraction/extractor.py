import re

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_03_toc_structure_parsing import (
    check_if_toc_transformation_is_complete,
    detect_page_index,
)
from pageindex.core.utils.llm_caller import call_llm_with_finish_reason


def toc_extractor(page_list, toc_page_list, model):
    def transform_dots_to_colon(text):
        text = re.sub(r"\.{5,}", ": ", text)
        text = re.sub(r"(?:\. ){5,}\.?", ": ", text)
        return text

    toc_content = ""
    for page_index in toc_page_list:
        toc_content += page_list[page_index][0]
    toc_content = transform_dots_to_colon(toc_content)
    has_page_index = detect_page_index(toc_content, model=model)

    return {"toc_content": toc_content, "page_index_given_in_toc": has_page_index}


def extract_toc_content(content, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_02_toc_content_extraction/prompts/toc_extract_content.txt", content=content)
    response, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt)

    if_complete = check_if_toc_transformation_is_complete(content, response, model)
    if if_complete == "yes" and finish_reason == "finished":
        return response

    chat_history = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response},
    ]
    continue_prompt = load_prompt("step_01_outline_discovery/step_02_toc_content_extraction/prompts/toc_extract_content_continue.txt")
    new_response, finish_reason = call_llm_with_finish_reason(model=model, prompt=continue_prompt, chat_history=chat_history)
    response = response + new_response
    if_complete = check_if_toc_transformation_is_complete(content, response, model)

    while not (if_complete == "yes" and finish_reason == "finished"):
        chat_history = [
            {"role": "user", "content": continue_prompt},
            {"role": "assistant", "content": response},
        ]
        new_response, finish_reason = call_llm_with_finish_reason(model=model, prompt=continue_prompt, chat_history=chat_history)
        response = response + new_response
        if_complete = check_if_toc_transformation_is_complete(content, response, model)
        if len(chat_history) > 5:
            raise Exception("Failed to complete table of contents after maximum retries")

    return response
