import os
from io import BytesIO

from pageindex.core.utils.pdf import (
    IMAGE_BLOCK_TYPE,
    PAGE_NUMBER_ARTIFACT_PATTERNS,
    TABLE_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
    _bbox_overlap_ratio,
    _block_overlaps_any_table,
    _build_item_metadata,
    _extract_ordered_page_content,
    _extract_page_blocks,
    _extract_image_markdown_from_pymupdf_block,
    _extract_text_from_pymupdf_block,
    _extract_tables_by_page,
    _extract_tables_with_camelot,
    _extract_tables_with_pdfplumber,
    _generate_table_summary,
    _generate_table_title,
    _get_ordered_blocks,
    _get_ordered_page_items,
    _is_image_item,
    _is_page_number_artifact,
    _normalize_image_alt_text,
    _normalize_block_text,
    _normalize_table,
    _ordered_item_key,
    _remove_page_number_artifacts,
    _render_ordered_item,
    _render_page_items,
    _render_table_block,
    _render_table_markdown,
    _table_to_markdown,
)
from pageindex.infrastructure.settings import resolve_model_name
from pageindex.core.utils.token_counter import get_token_encoder

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import pymupdf
except ImportError:
    pymupdf = None


def _require_pypdf2():
    if PyPDF2 is None:
        raise RuntimeError("PyPDF2 is required for PDF processing")
    return PyPDF2


def _require_pymupdf():
    if pymupdf is None:
        raise RuntimeError("pymupdf is required for PyMuPDF PDF processing")
    return pymupdf


def extract_text_from_pdf(pdf_path):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    return "".join(_remove_page_number_artifacts(page.extract_text()) for page in pdf_reader.pages)


def get_pdf_title(pdf_path):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    meta = pdf_reader.metadata
    return meta.title if meta and meta.title else "Untitled"


def get_text_of_pages(pdf_path, start_page, end_page, tag=True):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    parts = []
    for page_num in range(start_page - 1, end_page):
        page_text = _remove_page_number_artifacts(pdf_reader.pages[page_num].extract_text())
        if tag:
            parts.append(f"<start_index_{page_num + 1}>\n{page_text}\n<end_index_{page_num + 1}>\n")
        else:
            parts.append(page_text)
    return "".join(parts)


def get_first_start_page_from_text(text):
    import re

    match = re.search(r"<start_index_(\d+)>", text)
    return int(match.group(1)) if match else -1


def get_last_start_page_from_text(text):
    import re

    matches = list(re.finditer(r"<start_index_(\d+)>", text))
    return int(matches[-1].group(1)) if matches else -1


def sanitize_filename(filename, replacement="-"):
    return filename.replace("/", replacement)


def get_pdf_name(pdf_path):
    if isinstance(pdf_path, str):
        return os.path.basename(pdf_path)
    if isinstance(pdf_path, os.PathLike):
        return os.path.basename(os.fspath(pdf_path))
    if isinstance(pdf_path, BytesIO):
        pdf_reader = _require_pypdf2().PdfReader(pdf_path)
        meta = pdf_reader.metadata
        return sanitize_filename(meta.title if meta and meta.title else "Untitled")
    return "Untitled"


def get_number_of_pages(pdf_path):
    return len(_require_pypdf2().PdfReader(pdf_path).pages)


def get_page_tokens(pdf_path, model=None, pdf_parser=None, tables_by_page: dict[int, list[dict]] | None = None):
    resolved_model = resolve_model_name(model)
    encode = _build_encoder(resolved_model)
    parser = pdf_parser or ("PyMuPDF" if pymupdf is not None else "PyPDF2")
    if parser == "PyMuPDF":
        return _get_page_tokens_pymupdf(pdf_path, encode, model=resolved_model, tables_by_page=tables_by_page)
    if parser == "PyPDF2":
        return _get_page_tokens_pypdf2(pdf_path, encode)
    raise ValueError(f"Unsupported PDF parser: {parser}")


def get_text_of_pdf_pages(pdf_pages, start_page, end_page):
    return "".join(pdf_pages[page_num][0] for page_num in range(start_page - 1, end_page))


def get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page):
    return "".join(
        f"<physical_index_{page_num + 1}>\n{pdf_pages[page_num][0]}\n<physical_index_{page_num + 1}>\n"
        for page_num in range(start_page - 1, end_page)
    )


def extract_pdf_blocks(pdf_path, model=None, tables_by_page: dict[int, list[dict]] | None = None):
    resolved_model = resolve_model_name(model)
    encode = _build_encoder(resolved_model)
    doc = _open_pymupdf_doc(pdf_path)
    extracted_tables_by_page = tables_by_page or _extract_tables_by_page(pdf_path, model=resolved_model)

    blocks = []
    next_block_no = 1
    doc_char_offset = 0
    for page_no, page in enumerate(doc, start=1):
        page_blocks, next_block_no, doc_char_offset = _extract_page_blocks(
            page,
            page_no=page_no,
            block_no_start=next_block_no,
            doc_char_offset=doc_char_offset,
            encode=encode,
            pdf_path=pdf_path,
            model=resolved_model,
            page_tables=extracted_tables_by_page.get(page_no, []),
        )
        blocks.extend(page_blocks)
    return blocks


def _build_encoder(model):
    return get_token_encoder(model)


def _open_pymupdf_doc(pdf_path):
    mupdf = _require_pymupdf()
    if isinstance(pdf_path, BytesIO):
        return mupdf.open(stream=pdf_path, filetype="pdf")
    return mupdf.open(pdf_path)


def _get_page_tokens_pymupdf(pdf_path, encode, model=None, tables_by_page: dict[int, list[dict]] | None = None):
    doc = _open_pymupdf_doc(pdf_path)
    extracted_tables_by_page = tables_by_page or _extract_tables_by_page(pdf_path, model=model)
    page_list = []
    for page_no, page in enumerate(doc, start=1):
        page_text = _extract_ordered_page_content(page, render_images=False, page_tables=extracted_tables_by_page.get(page_no, []))
        page_list.append((page_text, len(encode(page_text))))
    return page_list


def _get_page_tokens_pypdf2(pdf_path, encode):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    page_tokens = []
    for page in pdf_reader.pages:
        page_text = _remove_page_number_artifacts(page.extract_text())
        page_tokens.append((page_text, len(encode(page_text))))
    return page_tokens
