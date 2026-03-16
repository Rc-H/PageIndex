import asyncio
import json

from pageindex.core.indexers.prompts import load_prompt
from pageindex.core.utils.json_utils import extract_json
from pageindex.core.utils.llm_caller import call_llm, call_llm_async
from pageindex.core.utils.pdf_reader import get_text_of_pdf_pages, get_text_of_pdf_pages_with_labels
from pageindex.core.utils.token_counter import count_tokens
from pageindex.core.utils.tree import list_to_tree, structure_to_list


def add_preface_if_needed(data):
    if not isinstance(data, list) or not data:
        return data
    if data[0]['physical_index'] is not None and data[0]['physical_index'] > 1:
        preface_node = {
            "structure": "0",
            "title": "Preface",
            "physical_index": 1,
        }
        data.insert(0, preface_node)
    return data


def post_processing(structure, end_physical_index):
    for i, item in enumerate(structure):
        item['start_index'] = item.get('physical_index')
        if i < len(structure) - 1:
            if structure[i + 1].get('appear_start') == 'yes':
                item['end_index'] = structure[i + 1]['physical_index'] - 1
            else:
                item['end_index'] = structure[i + 1]['physical_index']
        else:
            item['end_index'] = end_physical_index
    tree = list_to_tree(structure)
    if tree:
        return tree
    for node in structure:
        node.pop('appear_start', None)
        node.pop('physical_index', None)
    return structure


def clean_structure_post(data):
    if isinstance(data, dict):
        data.pop('page_number', None)
        data.pop('start_index', None)
        data.pop('end_index', None)
        if 'nodes' in data:
            clean_structure_post(data['nodes'])
    elif isinstance(data, list):
        for section in data:
            clean_structure_post(section)
    return data


def remove_fields(data, fields=None):
    if fields is None:
        fields = ['text']
    if isinstance(data, dict):
        return {k: remove_fields(v, fields) for k, v in data.items() if k not in fields}
    if isinstance(data, list):
        return [remove_fields(item, fields) for item in data]
    return data


def print_toc(tree, indent=0):
    for node in tree:
        print('  ' * indent + node['title'])
        if node.get('nodes'):
            print_toc(node['nodes'], indent + 1)


def print_json(data, max_len=40, indent=2):
    def simplify_data(obj):
        if isinstance(obj, dict):
            return {k: simplify_data(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [simplify_data(item) for item in obj]
        if isinstance(obj, str) and len(obj) > max_len:
            return obj[:max_len] + '...'
        return obj

    print(json.dumps(simplify_data(data), indent=indent, ensure_ascii=False))


def remove_structure_text(data):
    if isinstance(data, dict):
        data.pop('text', None)
        if 'nodes' in data:
            remove_structure_text(data['nodes'])
    elif isinstance(data, list):
        for item in data:
            remove_structure_text(item)
    return data


def check_token_limit(structure, limit=110000):
    nodes = structure_to_list(structure)
    for node in nodes:
        num_tokens = count_tokens(node['text'], model='gpt-4o')
        if num_tokens > limit:
            print(f"Node ID: {node['node_id']} has {num_tokens} tokens")
            print("Start Index:", node['start_index'])
            print("End Index:", node['end_index'])
            print("Title:", node['title'])
            print()


def convert_physical_index_to_int(data):
    if isinstance(data, list):
        for i in range(len(data)):
            if isinstance(data[i], dict) and 'physical_index' in data[i]:
                if isinstance(data[i]['physical_index'], str):
                    if data[i]['physical_index'].startswith('<physical_index_'):
                        data[i]['physical_index'] = int(data[i]['physical_index'].split('_')[-1].rstrip('>').strip())
                    elif data[i]['physical_index'].startswith('physical_index_'):
                        data[i]['physical_index'] = int(data[i]['physical_index'].split('_')[-1].strip())
    elif isinstance(data, str):
        if data.startswith('<physical_index_'):
            data = int(data.split('_')[-1].rstrip('>').strip())
        elif data.startswith('physical_index_'):
            data = int(data.split('_')[-1].strip())
        return data if isinstance(data, int) else None
    return data


def convert_page_to_int(data):
    for item in data:
        if 'page' in item and isinstance(item['page'], str):
            try:
                item['page'] = int(item['page'])
            except ValueError:
                pass
    return data


def add_node_text(node, pdf_pages):
    if isinstance(node, dict):
        start_page = node.get('start_index')
        end_page = node.get('end_index')
        node['text'] = get_text_of_pdf_pages(pdf_pages, start_page, end_page)
        if 'nodes' in node:
            add_node_text(node['nodes'], pdf_pages)
    elif isinstance(node, list):
        for item in node:
            add_node_text(item, pdf_pages)


def add_node_text_with_labels(node, pdf_pages):
    if isinstance(node, dict):
        start_page = node.get('start_index')
        end_page = node.get('end_index')
        node['text'] = get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page)
        if 'nodes' in node:
            add_node_text_with_labels(node['nodes'], pdf_pages)
    elif isinstance(node, list):
        for item in node:
            add_node_text_with_labels(item, pdf_pages)


async def generate_node_summary(node, model=None):
    prompt = load_prompt("node_summary.txt", text=node['text'])
    return await call_llm_async(model, prompt)


async def generate_summaries_for_structure(structure, model=None):
    nodes = structure_to_list(structure)
    tasks = [generate_node_summary(node, model=model) for node in nodes]
    summaries = await asyncio.gather(*tasks)
    for node, summary in zip(nodes, summaries):
        node['summary'] = summary
    return structure


def create_clean_structure_for_description(structure):
    if isinstance(structure, dict):
        clean_node = {}
        for key in ['title', 'node_id', 'summary', 'prefix_summary']:
            if key in structure:
                clean_node[key] = structure[key]
        if 'nodes' in structure and structure['nodes']:
            clean_node['nodes'] = create_clean_structure_for_description(structure['nodes'])
        return clean_node
    if isinstance(structure, list):
        return [create_clean_structure_for_description(item) for item in structure]
    return structure


def generate_doc_description(structure, model=None):
    prompt = load_prompt("doc_description.txt", structure=structure)
    return call_llm(model, prompt)


def reorder_dict(data, key_order):
    if not key_order:
        return data
    return {key: data[key] for key in key_order if key in data}


def format_structure(structure, order=None):
    if not order:
        return structure
    if isinstance(structure, dict):
        if 'nodes' in structure:
            structure['nodes'] = format_structure(structure['nodes'], order)
        if not structure.get('nodes'):
            structure.pop('nodes', None)
        structure = reorder_dict(structure, order)
    elif isinstance(structure, list):
        structure = [format_structure(item, order) for item in structure]
    return structure
