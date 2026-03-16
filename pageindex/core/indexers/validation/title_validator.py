import asyncio

from pageindex.core.indexers.prompts import load_prompt
from pageindex.core.utils.json_utils import extract_json
from pageindex.core.utils.llm_caller import call_llm_async


async def check_title_appearance(item, page_list, start_index=1, model=None):
    title = item['title']
    if 'physical_index' not in item or item['physical_index'] is None:
        return {'list_index': item.get('list_index'), 'answer': 'no', 'title': title, 'page_number': None}

    page_number = item['physical_index']
    page_text = page_list[page_number - start_index][0]

    prompt = load_prompt("check_title_appearance.txt", title=title, page_text=page_text)
    response = await call_llm_async(model=model, prompt=prompt)
    response = extract_json(response)
    answer = response.get('answer', 'no')
    return {'list_index': item['list_index'], 'answer': answer, 'title': title, 'page_number': page_number}


async def check_title_appearance_in_start(title, page_text, model=None, logger=None):
    prompt = load_prompt("check_title_appearance_in_start.txt", title=title, page_text=page_text)
    response = await call_llm_async(model=model, prompt=prompt)
    response = extract_json(response)
    if logger:
        logger.info(f"Response: {response}")
    return response.get("start_begin", "no")


async def check_title_appearance_in_start_concurrent(structure, page_list, model=None, logger=None):
    if logger:
        logger.info("Checking title appearance in start concurrently")

    for item in structure:
        if item.get('physical_index') is None:
            item['appear_start'] = 'no'

    tasks = []
    valid_items = []
    for item in structure:
        if item.get('physical_index') is not None:
            page_text = page_list[item['physical_index'] - 1][0]
            tasks.append(check_title_appearance_in_start(item['title'], page_text, model=model, logger=logger))
            valid_items.append(item)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for item, result in zip(valid_items, results):
        if isinstance(result, Exception):
            if logger:
                logger.error(f"Error checking start for {item['title']}: {result}")
            item['appear_start'] = 'no'
        else:
            item['appear_start'] = result

    return structure
