from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from pageindex.core.indexers.pipeline.prompts import load_prompt
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_05_outline_fallback_generation import (
    process_no_toc,
)
from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_06_outline_resolution import (
    process_toc_no_page_numbers,
    process_toc_with_page_numbers,
)
from pageindex.core.indexers.pipeline.step_02_outline_validation.title_checks import check_title_appearance
from pageindex.core.utils.llm_caller import call_llm
from pageindex.core.utils.structure_ops import convert_physical_index_to_int

logger = logging.getLogger(__name__)


def _log_outline_item_types(name, items):
    if not isinstance(items, list):
        logger.warning("%s is not a list: type=%s value=%r", name, type(items).__name__, items)
        return

    bad_items = [
        {"index": index, "type": type(item).__name__, "value": repr(item)[:200]}
        for index, item in enumerate(items)
        if not isinstance(item, dict)
    ]
    if bad_items:
        logger.warning("%s contains non-dict items: %s", name, bad_items)


def single_toc_item_index_fixer(section_title, content, model=None):
    prompt = load_prompt("step_02_outline_validation/prompts/toc_item_index_fix.txt")
    prompt = prompt + "\nSection Title:\n" + str(section_title) + "\nDocument pages:\n" + content
    response = call_llm(model=model, prompt=prompt, json_response=True)
    return convert_physical_index_to_int(json.loads(response)["physical_index"])


async def fix_incorrect_toc(toc_with_page_number, page_list, incorrect_results, start_index=1, model=None, logger=None):
    incorrect_indices = {result["list_index"] for result in incorrect_results}
    end_index = len(page_list) + start_index - 1
    incorrect_results_and_range_logs = []

    async def process_and_check_item(incorrect_item):
        list_index = incorrect_item["list_index"]
        if list_index < 0 or list_index >= len(toc_with_page_number):
            return {
                "list_index": list_index,
                "title": incorrect_item["title"],
                "physical_index": incorrect_item.get("physical_index"),
                "is_valid": False,
            }

        prev_correct = None
        for i in range(list_index - 1, -1, -1):
            if i not in incorrect_indices and 0 <= i < len(toc_with_page_number):
                physical_index = toc_with_page_number[i].get("physical_index")
                if physical_index is not None:
                    prev_correct = physical_index
                    break
        if prev_correct is None:
            prev_correct = start_index - 1

        next_correct = None
        for i in range(list_index + 1, len(toc_with_page_number)):
            if i not in incorrect_indices and 0 <= i < len(toc_with_page_number):
                physical_index = toc_with_page_number[i].get("physical_index")
                if physical_index is not None:
                    next_correct = physical_index
                    break
        if next_correct is None:
            next_correct = end_index

        incorrect_results_and_range_logs.append(
            {
                "list_index": list_index,
                "title": incorrect_item["title"],
                "prev_correct": prev_correct,
                "next_correct": next_correct,
            }
        )

        page_contents = []
        for page_index in range(prev_correct, next_correct + 1):
            idx = page_index - start_index
            if 0 <= idx < len(page_list):
                page_text = f"<physical_index_{page_index}>\n{page_list[idx][0]}\n<physical_index_{page_index}>\n\n"
                page_contents.append(page_text)
        content_range = "".join(page_contents)

        physical_index_int = single_toc_item_index_fixer(incorrect_item["title"], content_range, model)

        check_item = incorrect_item.copy()
        check_item["physical_index"] = physical_index_int
        check_result = await check_title_appearance(check_item, page_list, start_index, model)

        return {
            "list_index": list_index,
            "title": incorrect_item["title"],
            "physical_index": physical_index_int,
            "is_valid": check_result["answer"] == "yes",
        }

    tasks = [process_and_check_item(item) for item in incorrect_results]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    results = [r for r in results if not isinstance(r, Exception)]

    invalid_results = []
    for result in results:
        if result["is_valid"]:
            list_idx = result["list_index"]
            if 0 <= list_idx < len(toc_with_page_number):
                toc_with_page_number[list_idx]["physical_index"] = result["physical_index"]
            else:
                invalid_results.append(
                    {"list_index": result["list_index"], "title": result["title"], "physical_index": result["physical_index"]}
                )
        else:
            invalid_results.append(
                {"list_index": result["list_index"], "title": result["title"], "physical_index": result["physical_index"]}
            )

    logger.info(f"incorrect_results_and_range_logs: {incorrect_results_and_range_logs}")
    logger.info(f"invalid_results: {invalid_results}")
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


def validate_and_truncate_physical_indices(
    toc_with_page_number: list[dict[str, Any]],
    page_list_length: int,
    start_index: int = 1,
    logger=None,
) -> list[dict[str, Any]]:
    if not toc_with_page_number:
        return toc_with_page_number

    max_allowed_page = page_list_length + start_index - 1
    truncated_items = []

    for item in toc_with_page_number:
        if item.get("physical_index") is not None:
            original_index = item["physical_index"]
            if original_index > max_allowed_page:
                item["physical_index"] = None
                truncated_items.append({"title": item.get("title", "Unknown"), "original_index": original_index})
                if logger:
                    logger.info(
                        f"Removed physical_index for '{item.get('title', 'Unknown')}' "
                        f"(was {original_index}, too far beyond document)"
                    )

    if truncated_items and logger:
        logger.info(f"Total removed items: {len(truncated_items)}")
    return toc_with_page_number


async def verify_toc(page_list, list_result, start_index: int = 1, sample_size: int | None = None, model: str | None = None):
    last_physical_index = None
    for item in reversed(list_result):
        if item.get("physical_index") is not None:
            last_physical_index = item["physical_index"]
            break

    if last_physical_index is None or last_physical_index < len(page_list) / 2:
        return 0, []

    if sample_size is None:
        sample_indices = range(0, len(list_result))
    else:
        sample_size = min(sample_size, len(list_result))
        sample_indices = random.sample(range(0, len(list_result)), sample_size)

    indexed_sample_list = []
    for index in sample_indices:
        item = list_result[index]
        if item.get("physical_index") is not None:
            item_with_index = item.copy()
            item_with_index["list_index"] = index
            indexed_sample_list.append(item_with_index)

    tasks = [check_title_appearance(item, page_list, start_index, model) for item in indexed_sample_list]
    results = await asyncio.gather(*tasks)

    correct_count = sum(1 for result in results if result["answer"] == "yes")
    incorrect_results = [result for result in results if result["answer"] != "yes"]
    accuracy = correct_count / len(results) if results else 0
    return accuracy, incorrect_results


async def resolve_pdf_outline(
    page_list,
    mode: str | None = None,
    toc_content=None,
    toc_page_list=None,
    start_index: int = 1,
    opt=None,
    logger=None,
):
    if mode == "process_toc_with_page_numbers":
        toc_with_page_number = process_toc_with_page_numbers(
            toc_content,
            toc_page_list,
            page_list,
            toc_check_page_num=opt.toc_check_page_num,
            model=opt.model,
            logger=logger,
        )
    elif mode == "process_toc_no_page_numbers":
        toc_with_page_number = process_toc_no_page_numbers(
            toc_content,
            toc_page_list,
            page_list,
            model=opt.model,
            logger=logger,
        )
    else:
        toc_with_page_number = process_no_toc(page_list, start_index=start_index, model=opt.model, logger=logger)

    _log_outline_item_types(f"resolve_pdf_outline[{mode or 'process_no_toc'}]", toc_with_page_number)
    toc_with_page_number = [item for item in toc_with_page_number if item.get("physical_index") is not None]
    toc_with_page_number = validate_and_truncate_physical_indices(
        toc_with_page_number,
        len(page_list),
        start_index=start_index,
        logger=logger,
    )

    accuracy, incorrect_results = await verify_toc(
        page_list,
        toc_with_page_number,
        start_index=start_index,
        model=opt.model,
    )

    if logger:
        logger.info({"mode": mode, "accuracy": accuracy, "incorrect_results": incorrect_results})

    if accuracy == 1.0 and not incorrect_results:
        return toc_with_page_number
    if accuracy > 0.6 and incorrect_results:
        toc_with_page_number, _ = await fix_incorrect_toc_with_retries(
            toc_with_page_number,
            page_list,
            incorrect_results,
            start_index=start_index,
            max_attempts=3,
            model=opt.model,
            logger=logger,
        )
        return toc_with_page_number

    if mode == "process_toc_with_page_numbers":
        return await resolve_pdf_outline(
            page_list,
            mode="process_toc_no_page_numbers",
            toc_content=toc_content,
            toc_page_list=toc_page_list,
            start_index=start_index,
            opt=opt,
            logger=logger,
        )
    if mode == "process_toc_no_page_numbers":
        return await resolve_pdf_outline(
            page_list,
            mode="process_no_toc",
            start_index=start_index,
            opt=opt,
            logger=logger,
        )
    raise Exception("Processing failed")
