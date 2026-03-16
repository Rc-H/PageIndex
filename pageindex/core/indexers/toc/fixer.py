import asyncio

from pageindex.core.indexers.prompts import load_prompt
from pageindex.core.indexers.validation.title_validator import check_title_appearance
from pageindex.core.utils.json_utils import extract_json
from pageindex.core.utils.llm_caller import call_llm
from pageindex.core.utils.structure_ops import convert_physical_index_to_int


def single_toc_item_index_fixer(section_title, content, model="gpt-4o-2024-11-20"):
    prompt = load_prompt("toc_item_index_fix.txt")
    prompt = prompt + '\nSection Title:\n' + str(section_title) + '\nDocument pages:\n' + content
    response = call_llm(model=model, prompt=prompt)
    return convert_physical_index_to_int(extract_json(response)['physical_index'])


async def fix_incorrect_toc(toc_with_page_number, page_list, incorrect_results, start_index=1, model=None, logger=None):
    incorrect_indices = {result['list_index'] for result in incorrect_results}
    end_index = len(page_list) + start_index - 1
    incorrect_results_and_range_logs = []

    async def process_and_check_item(incorrect_item):
        list_index = incorrect_item['list_index']
        if list_index < 0 or list_index >= len(toc_with_page_number):
            return {
                'list_index': list_index,
                'title': incorrect_item['title'],
                'physical_index': incorrect_item.get('physical_index'),
                'is_valid': False
            }

        prev_correct = None
        for i in range(list_index - 1, -1, -1):
            if i not in incorrect_indices and 0 <= i < len(toc_with_page_number):
                physical_index = toc_with_page_number[i].get('physical_index')
                if physical_index is not None:
                    prev_correct = physical_index
                    break
        if prev_correct is None:
            prev_correct = start_index - 1

        next_correct = None
        for i in range(list_index + 1, len(toc_with_page_number)):
            if i not in incorrect_indices and 0 <= i < len(toc_with_page_number):
                physical_index = toc_with_page_number[i].get('physical_index')
                if physical_index is not None:
                    next_correct = physical_index
                    break
        if next_correct is None:
            next_correct = end_index

        incorrect_results_and_range_logs.append({
            'list_index': list_index,
            'title': incorrect_item['title'],
            'prev_correct': prev_correct,
            'next_correct': next_correct
        })

        page_contents = []
        for page_index in range(prev_correct, next_correct + 1):
            idx = page_index - start_index
            if 0 <= idx < len(page_list):
                page_text = f"<physical_index_{page_index}>\n{page_list[idx][0]}\n<physical_index_{page_index}>\n\n"
                page_contents.append(page_text)
        content_range = ''.join(page_contents)

        physical_index_int = single_toc_item_index_fixer(incorrect_item['title'], content_range, model)

        check_item = incorrect_item.copy()
        check_item['physical_index'] = physical_index_int
        check_result = await check_title_appearance(check_item, page_list, start_index, model)

        return {
            'list_index': list_index,
            'title': incorrect_item['title'],
            'physical_index': physical_index_int,
            'is_valid': check_result['answer'] == 'yes'
        }

    tasks = [process_and_check_item(item) for item in incorrect_results]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    results = [r for r in results if not isinstance(r, Exception)]

    invalid_results = []
    for result in results:
        if result['is_valid']:
            list_idx = result['list_index']
            if 0 <= list_idx < len(toc_with_page_number):
                toc_with_page_number[list_idx]['physical_index'] = result['physical_index']
            else:
                invalid_results.append({'list_index': result['list_index'], 'title': result['title'], 'physical_index': result['physical_index']})
        else:
            invalid_results.append({'list_index': result['list_index'], 'title': result['title'], 'physical_index': result['physical_index']})

    logger.info(f'incorrect_results_and_range_logs: {incorrect_results_and_range_logs}')
    logger.info(f'invalid_results: {invalid_results}')
    return toc_with_page_number, invalid_results


async def fix_incorrect_toc_with_retries(toc_with_page_number, page_list, incorrect_results, start_index=1, max_attempts=3, model=None, logger=None):
    fix_attempt = 0
    current_toc = toc_with_page_number
    current_incorrect = incorrect_results

    while current_incorrect:
        current_toc, current_incorrect = await fix_incorrect_toc(current_toc, page_list, current_incorrect, start_index, model, logger)
        fix_attempt += 1
        if fix_attempt >= max_attempts:
            logger.info("Maximum fix attempts reached")
            break

    return current_toc, current_incorrect
