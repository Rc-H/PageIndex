import asyncio
import logging
import time

from pageindex.infrastructure.llm import get_active_llm_client


MAX_RETRIES = 10


def call_llm(model, prompt, chat_history=None, json_response=False):
    for i in range(MAX_RETRIES):
        try:
            return get_active_llm_client().generate_text(
                model=model, prompt=prompt, chat_history=chat_history, json_response=json_response,
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            if i < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                logging.error('Max retries reached for prompt: ' + prompt)
                return "Error"


def call_llm_with_finish_reason(model, prompt, chat_history=None, json_response=False):
    for i in range(MAX_RETRIES):
        try:
            return get_active_llm_client().generate_text_with_finish_reason(
                model=model, prompt=prompt, chat_history=chat_history, json_response=json_response,
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            if i < MAX_RETRIES - 1:
                time.sleep(1)
            else:
                logging.error('Max retries reached for prompt: ' + prompt)
                return "Error"


async def call_llm_async(model, prompt, chat_history=None, json_response=False):
    for i in range(MAX_RETRIES):
        try:
            return await get_active_llm_client().generate_text_async(
                model=model, prompt=prompt, chat_history=chat_history, json_response=json_response,
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            if i < MAX_RETRIES - 1:
                await asyncio.sleep(1)
            else:
                logging.error('Max retries reached for prompt: ' + prompt)
                return "Error"
