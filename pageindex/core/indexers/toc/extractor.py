import copy
import json
import math
import re

from pageindex.core.indexers.prompts import load_prompt
from pageindex.core.utils.json_utils import extract_json, get_json_content
from pageindex.core.utils.llm_caller import call_llm, call_llm_with_finish_reason
from pageindex.core.utils.structure_ops import convert_page_to_int, convert_physical_index_to_int
from pageindex.core.utils.token_counter import count_tokens


# --- TOC detection ---

def toc_detector_single_page(content, model=None):
    prompt = load_prompt("toc_detect_single_page.txt", content=content)
    response = call_llm(model=model, prompt=prompt)
    return extract_json(response)['toc_detected']


def find_toc_pages(start_page_index, page_list, opt, logger=None):
    last_page_is_yes = False
    toc_page_list = []
    i = start_page_index

    while i < len(page_list):
        if i >= opt.toc_check_page_num and not last_page_is_yes:
            break
        detected_result = toc_detector_single_page(page_list[i][0], model=opt.model)
        if detected_result == 'yes':
            if logger:
                logger.info(f'Page {i} has toc')
            toc_page_list.append(i)
            last_page_is_yes = True
        elif detected_result == 'no' and last_page_is_yes:
            if logger:
                logger.info(f'Found the last page with toc: {i-1}')
            break
        i += 1

    if not toc_page_list and logger:
        logger.info('No toc found')
    return toc_page_list


def check_toc(page_list, opt=None):
    toc_page_list = find_toc_pages(start_page_index=0, page_list=page_list, opt=opt)
    if not toc_page_list:
        return {'toc_content': None, 'toc_page_list': [], 'page_index_given_in_toc': 'no'}

    toc_json = toc_extractor(page_list, toc_page_list, opt.model)
    if toc_json['page_index_given_in_toc'] == 'yes':
        return {'toc_content': toc_json['toc_content'], 'toc_page_list': toc_page_list, 'page_index_given_in_toc': 'yes'}

    current_start_index = toc_page_list[-1] + 1
    while (toc_json['page_index_given_in_toc'] == 'no' and
           current_start_index < len(page_list) and
           current_start_index < opt.toc_check_page_num):
        additional_toc_pages = find_toc_pages(start_page_index=current_start_index, page_list=page_list, opt=opt)
        if not additional_toc_pages:
            break
        additional_toc_json = toc_extractor(page_list, additional_toc_pages, opt.model)
        if additional_toc_json['page_index_given_in_toc'] == 'yes':
            return {'toc_content': additional_toc_json['toc_content'], 'toc_page_list': additional_toc_pages, 'page_index_given_in_toc': 'yes'}
        current_start_index = additional_toc_pages[-1] + 1

    return {'toc_content': toc_json['toc_content'], 'toc_page_list': toc_page_list, 'page_index_given_in_toc': 'no'}


# --- TOC extraction & transformation ---

def toc_extractor(page_list, toc_page_list, model):
    def transform_dots_to_colon(text):
        text = re.sub(r'\.{5,}', ': ', text)
        text = re.sub(r'(?:\. ){5,}\.?', ': ', text)
        return text

    toc_content = ""
    for page_index in toc_page_list:
        toc_content += page_list[page_index][0]
    toc_content = transform_dots_to_colon(toc_content)
    has_page_index = detect_page_index(toc_content, model=model)

    return {"toc_content": toc_content, "page_index_given_in_toc": has_page_index}


def detect_page_index(toc_content, model=None):
    prompt = load_prompt("toc_detect_page_index.txt", toc_content=toc_content)
    response = call_llm(model=model, prompt=prompt)
    return extract_json(response)['page_index_given_in_toc']


def check_if_toc_transformation_is_complete(content, toc, model=None):
    prompt = load_prompt("toc_transformation_complete_check.txt")
    prompt = prompt + '\n Raw Table of contents:\n' + content + '\n Cleaned Table of contents:\n' + toc
    response = call_llm(model=model, prompt=prompt)
    return extract_json(response)['completed']


def extract_toc_content(content, model=None):
    prompt = load_prompt("toc_extract_content.txt", content=content)
    response, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt)

    if_complete = check_if_toc_transformation_is_complete(content, response, model)
    if if_complete == "yes" and finish_reason == "finished":
        return response

    chat_history = [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response},
    ]
    continue_prompt = load_prompt("toc_extract_content_continue.txt")
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
            raise Exception('Failed to complete table of contents after maximum retries')

    return response


def toc_transformer(toc_content, model=None):
    init_prompt = load_prompt("toc_transform.txt")
    prompt = init_prompt + '\n Given table of contents\n:' + toc_content
    last_complete, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt)
    if_complete = check_if_toc_transformation_is_complete(toc_content, last_complete, model)
    if if_complete == "yes" and finish_reason == "finished":
        last_complete = extract_json(last_complete)
        return convert_page_to_int(last_complete['table_of_contents'])

    last_complete = get_json_content(last_complete)
    while not (if_complete == "yes" and finish_reason == "finished"):
        position = last_complete.rfind('}')
        if position != -1:
            last_complete = last_complete[:position + 2]
        continue_prompt = load_prompt("toc_transform_continue.txt", toc_content=toc_content, last_complete=last_complete)
        new_complete, finish_reason = call_llm_with_finish_reason(model=model, prompt=continue_prompt)
        if new_complete.startswith('```json'):
            new_complete = get_json_content(new_complete)
            last_complete = last_complete + new_complete
        if_complete = check_if_toc_transformation_is_complete(toc_content, last_complete, model)

    last_complete = json.loads(last_complete)
    return convert_page_to_int(last_complete['table_of_contents'])


def toc_index_extractor(toc, content, model=None):
    prompt = load_prompt("toc_index_extract.txt")
    prompt = prompt + '\nTable of contents:\n' + str(toc) + '\nDocument pages:\n' + content
    response = call_llm(model=model, prompt=prompt)
    return extract_json(response)


# --- TOC page number processing ---

def add_page_number_to_toc(part, structure, model=None):
    prompt = load_prompt("toc_add_page_number.txt")
    prompt = prompt + f"\n\nCurrent Partial Document:\n{part}\n\nGiven Structure\n{json.dumps(structure, indent=2)}\n"
    current_json_raw = call_llm(model=model, prompt=prompt)
    json_result = extract_json(current_json_raw)
    for item in json_result:
        item.pop('start', None)
    return json_result


def remove_first_physical_index_section(text):
    pattern = r'<physical_index_\d+>.*?<physical_index_\d+>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return text.replace(match.group(0), '', 1)
    return text


def generate_toc_continue(toc_content, part, model="gpt-4o-2024-11-20"):
    prompt = load_prompt("toc_generate_continue.txt")
    prompt = prompt + '\nGiven text\n:' + part + '\nPrevious tree structure\n:' + json.dumps(toc_content, indent=2)
    response, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt)
    if finish_reason == 'finished':
        return extract_json(response)
    raise Exception(f'finish reason: {finish_reason}')


def generate_toc_init(part, model=None):
    prompt = load_prompt("toc_generate_init.txt")
    prompt = prompt + '\nGiven text\n:' + part
    response, finish_reason = call_llm_with_finish_reason(model=model, prompt=prompt)
    if finish_reason == 'finished':
        return extract_json(response)
    raise Exception(f'finish reason: {finish_reason}')


def page_list_to_group_text(page_contents, token_lengths, max_tokens=20000, overlap_page=1):
    num_tokens = sum(token_lengths)
    if num_tokens <= max_tokens:
        return ["".join(page_contents)]

    subsets = []
    current_subset = []
    current_token_count = 0

    expected_parts_num = math.ceil(num_tokens / max_tokens)
    average_tokens_per_part = math.ceil(((num_tokens / expected_parts_num) + max_tokens) / 2)

    for i, (page_content, page_tokens) in enumerate(zip(page_contents, token_lengths)):
        if current_token_count + page_tokens > average_tokens_per_part:
            subsets.append(''.join(current_subset))
            overlap_start = max(i - overlap_page, 0)
            current_subset = page_contents[overlap_start:i]
            current_token_count = sum(token_lengths[overlap_start:i])
        current_subset.append(page_content)
        current_token_count += page_tokens

    if current_subset:
        subsets.append(''.join(current_subset))
    return subsets


def remove_page_number(data):
    if isinstance(data, dict):
        data.pop('page_number', None)
        for key in list(data.keys()):
            if 'nodes' in key:
                remove_page_number(data[key])
    elif isinstance(data, list):
        for item in data:
            remove_page_number(item)
    return data


def extract_matching_page_pairs(toc_page, toc_physical_index, start_page_index):
    pairs = []
    for phy_item in toc_physical_index:
        for page_item in toc_page:
            if phy_item.get('title') == page_item.get('title'):
                physical_index = phy_item.get('physical_index')
                if physical_index is not None and int(physical_index) >= start_page_index:
                    pairs.append({
                        'title': phy_item.get('title'),
                        'page': page_item.get('page'),
                        'physical_index': physical_index
                    })
    return pairs


def calculate_page_offset(pairs):
    differences = []
    for pair in pairs:
        try:
            differences.append(pair['physical_index'] - pair['page'])
        except (KeyError, TypeError):
            continue
    if not differences:
        return None
    difference_counts = {}
    for diff in differences:
        difference_counts[diff] = difference_counts.get(diff, 0) + 1
    return max(difference_counts.items(), key=lambda x: x[1])[0]


def add_page_offset_to_toc_json(data, offset):
    for i in range(len(data)):
        if data[i].get('page') is not None and isinstance(data[i]['page'], int):
            data[i]['physical_index'] = data[i]['page'] + offset
            del data[i]['page']
    return data


# --- Processing modes ---

def process_no_toc(page_list, start_index=1, model=None, logger=None):
    page_contents = []
    token_lengths = []
    for page_index in range(start_index, start_index + len(page_list)):
        page_text = f"<physical_index_{page_index}>\n{page_list[page_index-start_index][0]}\n<physical_index_{page_index}>\n\n"
        page_contents.append(page_text)
        token_lengths.append(count_tokens(page_text, model))
    group_texts = page_list_to_group_text(page_contents, token_lengths)
    logger.info(f'len(group_texts): {len(group_texts)}')

    toc_with_page_number = generate_toc_init(group_texts[0], model)
    for group_text in group_texts[1:]:
        toc_with_page_number_additional = generate_toc_continue(toc_with_page_number, group_text, model)
        toc_with_page_number.extend(toc_with_page_number_additional)
    logger.info(f'generate_toc: {toc_with_page_number}')

    toc_with_page_number = convert_physical_index_to_int(toc_with_page_number)
    logger.info(f'convert_physical_index_to_int: {toc_with_page_number}')
    return toc_with_page_number


def process_toc_no_page_numbers(toc_content, toc_page_list, page_list, start_index=1, model=None, logger=None):
    page_contents = []
    token_lengths = []
    toc_content = toc_transformer(toc_content, model)
    logger.info(f'toc_transformer: {toc_content}')
    for page_index in range(start_index, start_index + len(page_list)):
        page_text = f"<physical_index_{page_index}>\n{page_list[page_index-start_index][0]}\n<physical_index_{page_index}>\n\n"
        page_contents.append(page_text)
        token_lengths.append(count_tokens(page_text, model))

    group_texts = page_list_to_group_text(page_contents, token_lengths)
    logger.info(f'len(group_texts): {len(group_texts)}')

    toc_with_page_number = copy.deepcopy(toc_content)
    for group_text in group_texts:
        toc_with_page_number = add_page_number_to_toc(group_text, toc_with_page_number, model)
    logger.info(f'add_page_number_to_toc: {toc_with_page_number}')

    toc_with_page_number = convert_physical_index_to_int(toc_with_page_number)
    logger.info(f'convert_physical_index_to_int: {toc_with_page_number}')
    return toc_with_page_number


def process_toc_with_page_numbers(toc_content, toc_page_list, page_list, toc_check_page_num=None, model=None, logger=None):
    toc_with_page_number = toc_transformer(toc_content, model)
    logger.info(f'toc_with_page_number: {toc_with_page_number}')

    toc_no_page_number = remove_page_number(copy.deepcopy(toc_with_page_number))
    start_page_index = toc_page_list[-1] + 1
    main_content = ""
    for page_index in range(start_page_index, min(start_page_index + toc_check_page_num, len(page_list))):
        main_content += f"<physical_index_{page_index+1}>\n{page_list[page_index][0]}\n<physical_index_{page_index+1}>\n\n"

    toc_with_physical_index = toc_index_extractor(toc_no_page_number, main_content, model)
    logger.info(f'toc_with_physical_index: {toc_with_physical_index}')

    toc_with_physical_index = convert_physical_index_to_int(toc_with_physical_index)
    logger.info(f'toc_with_physical_index: {toc_with_physical_index}')

    matching_pairs = extract_matching_page_pairs(toc_with_page_number, toc_with_physical_index, start_page_index)
    logger.info(f'matching_pairs: {matching_pairs}')

    offset = calculate_page_offset(matching_pairs)
    logger.info(f'offset: {offset}')

    toc_with_page_number = add_page_offset_to_toc_json(toc_with_page_number, offset)
    logger.info(f'toc_with_page_number: {toc_with_page_number}')

    toc_with_page_number = process_none_page_numbers(toc_with_page_number, page_list, model=model)
    logger.info(f'toc_with_page_number: {toc_with_page_number}')
    return toc_with_page_number


def process_none_page_numbers(toc_items, page_list, start_index=1, model=None):
    for i, item in enumerate(toc_items):
        if "physical_index" not in item:
            prev_physical_index = 0
            for j in range(i - 1, -1, -1):
                if toc_items[j].get('physical_index') is not None:
                    prev_physical_index = toc_items[j]['physical_index']
                    break

            next_physical_index = -1
            for j in range(i + 1, len(toc_items)):
                if toc_items[j].get('physical_index') is not None:
                    next_physical_index = toc_items[j]['physical_index']
                    break

            page_contents = []
            for page_index in range(prev_physical_index, next_physical_index + 1):
                list_index = page_index - start_index
                if 0 <= list_index < len(page_list):
                    page_text = f"<physical_index_{page_index}>\n{page_list[list_index][0]}\n<physical_index_{page_index}>\n\n"
                    page_contents.append(page_text)

            item_copy = copy.deepcopy(item)
            del item_copy['page']
            result = add_page_number_to_toc(page_contents, item_copy, model)
            if isinstance(result[0]['physical_index'], str) and result[0]['physical_index'].startswith('<physical_index'):
                item['physical_index'] = int(result[0]['physical_index'].split('_')[-1].rstrip('>').strip())
                del item['page']

    return toc_items
