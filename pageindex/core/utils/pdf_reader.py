import os
import re
from io import BytesIO

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
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text += page.extract_text()
    return text


def get_pdf_title(pdf_path):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    meta = pdf_reader.metadata
    return meta.title if meta and meta.title else 'Untitled'


def get_text_of_pages(pdf_path, start_page, end_page, tag=True):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    text = ""
    for page_num in range(start_page - 1, end_page):
        page = pdf_reader.pages[page_num]
        page_text = page.extract_text()
        if tag:
            text += f"<start_index_{page_num+1}>\n{page_text}\n<end_index_{page_num+1}>\n"
        else:
            text += page_text
    return text


def get_first_start_page_from_text(text):
    match = re.search(r'<start_index_(\d+)>', text)
    return int(match.group(1)) if match else -1


def get_last_start_page_from_text(text):
    matches = list(re.finditer(r'<start_index_(\d+)>', text))
    return int(matches[-1].group(1)) if matches else -1


def sanitize_filename(filename, replacement='-'):
    return filename.replace('/', replacement)


def get_pdf_name(pdf_path):
    if isinstance(pdf_path, str):
        return os.path.basename(pdf_path)
    if isinstance(pdf_path, BytesIO):
        pdf_reader = _require_pypdf2().PdfReader(pdf_path)
        meta = pdf_reader.metadata
        pdf_name = meta.title if meta and meta.title else 'Untitled'
        return sanitize_filename(pdf_name)
    return 'Untitled'


def get_number_of_pages(pdf_path):
    return len(_require_pypdf2().PdfReader(pdf_path).pages)


def get_page_tokens(pdf_path, model="gpt-4o-2024-11-20", pdf_parser="PyPDF2"):
    encode = _build_encoder(model)

    if pdf_parser == "PyMuPDF":
        return _get_page_tokens_pymupdf(pdf_path, encode)
    if pdf_parser == "PyPDF2":
        return _get_page_tokens_pypdf2(pdf_path, encode)
    raise ValueError(f"Unsupported PDF parser: {pdf_parser}")


def get_text_of_pdf_pages(pdf_pages, start_page, end_page):
    text = ""
    for page_num in range(start_page - 1, end_page):
        text += pdf_pages[page_num][0]
    return text


def get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page):
    text = ""
    for page_num in range(start_page - 1, end_page):
        text += f"<physical_index_{page_num+1}>\n{pdf_pages[page_num][0]}\n<physical_index_{page_num+1}>\n"
    return text


# --- private helpers ---

def _build_encoder(model):
    return get_token_encoder(model)


def _get_page_tokens_pymupdf(pdf_path, encode):
    mupdf = _require_pymupdf()
    if isinstance(pdf_path, BytesIO):
        doc = mupdf.open(stream=pdf_path, filetype="pdf")
    else:
        doc = mupdf.open(pdf_path)
    page_list = []
    for page in doc:
        page_text = page.get_text()
        page_list.append((page_text, len(encode(page_text))))
    return page_list


def _get_page_tokens_pypdf2(pdf_path, encode):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    page_list = []
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        page_list.append((page_text, len(encode(page_text))))
    return page_list
