import json

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.utils.llm_caller import call_llm, call_llm_with_finish_reason
from pageindex.core.utils.structure_ops import convert_page_to_int


def detect_page_index(toc_content, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_03_toc_structure_parsing/prompts/toc_detect_page_index.txt", toc_content=toc_content)
    response = call_llm(model=model, prompt=prompt, json_response=True)
    return json.loads(response)["page_index_given_in_toc"]


def check_if_toc_transformation_is_complete(content, toc, model=None):
    prompt = load_prompt("step_01_outline_discovery/step_03_toc_structure_parsing/prompts/toc_transformation_complete_check.txt")
    prompt = prompt + "\n Raw Table of contents:\n" + content + "\n Cleaned Table of contents:\n" + toc
    response = call_llm(model=model, prompt=prompt, json_response=True)
    return json.loads(response)["completed"]


def toc_transformer(toc_content, model=None):
    init_prompt = load_prompt("step_01_outline_discovery/step_03_toc_structure_parsing/prompts/toc_transform.txt")
    prompt = init_prompt + "\n Given table of contents\n:" + toc_content
    last_complete, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt, json_response=True)
    if_complete = check_if_toc_transformation_is_complete(toc_content, last_complete, model)
    if if_complete == "yes" and finish_reason == "finished":
        last_complete = json.loads(last_complete)
        return convert_page_to_int(last_complete["table_of_contents"])

    last_complete = last_complete.strip()
    while not (if_complete == "yes" and finish_reason == "finished"):
        position = last_complete.rfind("}")
        if position != -1:
            last_complete = last_complete[:position + 2]
        continue_prompt = load_prompt(
            "step_01_outline_discovery/step_03_toc_structure_parsing/prompts/toc_transform_continue.txt",
            toc_content=toc_content,
            last_complete=last_complete,
        )
        new_complete, finish_reason = call_llm_with_finish_reason(model=model, prompt=continue_prompt, json_response=True)
        last_complete = last_complete + new_complete.strip()
        if_complete = check_if_toc_transformation_is_complete(toc_content, last_complete, model)

    last_complete = json.loads(last_complete)
    return convert_page_to_int(last_complete["table_of_contents"])
