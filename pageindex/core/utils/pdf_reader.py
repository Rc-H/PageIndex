import os
import re
from io import BytesIO

from pageindex.core.utils.image_upload import upload_image_bytes
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


def get_page_tokens(pdf_path, model="gpt-4o-2024-11-20", pdf_parser=None):
    encode = _build_encoder(model)

    if pdf_parser is None:
        pdf_parser = "PyMuPDF" if pymupdf is not None else "PyPDF2"

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


def extract_pdf_blocks(pdf_path, model="gpt-4o-2024-11-20"):
    encode = _build_encoder(model)
    mupdf = _require_pymupdf()
    if isinstance(pdf_path, BytesIO):
        doc = mupdf.open(stream=pdf_path, filetype="pdf")
    else:
        doc = mupdf.open(pdf_path)

    blocks = []
    block_no = 1
    char_offset_in_doc = 0
    for page_no, page in enumerate(doc, start=1):
        page_blocks, block_no, char_offset_in_doc = _extract_page_blocks(
            page,
            page_no=page_no,
            block_no_start=block_no,
            doc_char_offset=char_offset_in_doc,
            encode=encode,
        )
        blocks.extend(page_blocks)
    return blocks


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
        page_text = _extract_ordered_page_content(page)
        page_list.append((page_text, len(encode(page_text))))
    return page_list


def _get_page_tokens_pypdf2(pdf_path, encode):
    pdf_reader = _require_pypdf2().PdfReader(pdf_path)
    page_list = []
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        page_list.append((page_text, len(encode(page_text))))
    return page_list


def _extract_ordered_page_content(page) -> str:
    blocks = _get_ordered_blocks(page)
    return "\n".join(part for part in (_render_ordered_block(block) for block in blocks) if part).strip()


def _extract_page_blocks(page, page_no: int, block_no_start: int, doc_char_offset: int, encode):
    ordered_blocks = _get_ordered_blocks(page)
    rendered_blocks = [(_render_ordered_block(block), block) for block in ordered_blocks]
    non_empty_blocks = [(raw_content, block) for raw_content, block in rendered_blocks if raw_content]
    page_blocks = []
    page_char_offset = 0
    next_block_no = block_no_start

    for emitted_index, (raw_content, block) in enumerate(non_empty_blocks):
        block_order_in_page = emitted_index + 1
        normalized_text = _normalize_block_text(raw_content)
        metadata = {
            "type": "image" if block.get("type") == 1 else "text",
            "bbox": block.get("bbox"),
        }

        block_char_count = len(normalized_text)
        page_blocks.append(
            {
                "block_no": next_block_no,
                "page_no": page_no,
                "block_order_in_page": block_order_in_page,
                "start_index": page_no,
                "end_index": page_no,
                "raw_content": raw_content,
                "normalized_text": normalized_text,
                "display_text": raw_content,
                "char_start_in_doc": doc_char_offset,
                "char_end_in_doc": doc_char_offset + block_char_count - 1 if block_char_count else doc_char_offset,
                "char_start_in_page": page_char_offset,
                "char_end_in_page": page_char_offset + block_char_count - 1 if block_char_count else page_char_offset,
                "token_count": len(encode(normalized_text)),
                "metadata": metadata,
            }
        )

        next_block_no += 1
        doc_char_offset += block_char_count
        page_char_offset += block_char_count

        if emitted_index < len(non_empty_blocks) - 1:
            doc_char_offset += 1
            page_char_offset += 1

    return page_blocks, next_block_no, doc_char_offset


def _get_ordered_blocks(page):
    blocks = page.get_text("dict").get("blocks", [])
    return sorted(
        blocks,
        key=lambda block: (
            round(block.get("bbox", [0, 0, 0, 0])[1], 2),
            round(block.get("bbox", [0, 0, 0, 0])[0], 2),
        ),
    )


def _render_ordered_block(block: dict) -> str:
    block_type = block.get("type")
    if block_type == 0:
        return _extract_text_from_pymupdf_block(block)
    if block_type == 1:
        return _extract_image_markdown_from_pymupdf_block(block)
    return ""


def _extract_text_from_pymupdf_block(block: dict) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        line_text = "".join(
            span.get("text", "")
            for span in line.get("spans", [])
        ).strip()
        if line_text:
            lines.append(line_text)
    return "\n".join(lines)


def _extract_image_markdown_from_pymupdf_block(block: dict) -> str:
    image_bytes = block.get("image")
    if not image_bytes:
        return "![image]"
    ext = block.get("ext") or "png"
    return upload_image_bytes(image_bytes, filename=f"image.{ext}", content_type=f"image/{ext}") or "![image]"


def _normalize_block_text(text: str) -> str:
    return text.strip()
