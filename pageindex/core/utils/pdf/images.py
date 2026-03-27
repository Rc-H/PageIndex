import os
import re
from base64 import b64encode
from pathlib import Path

from pageindex.core.utils.image_upload import build_markdown_image, upload_attachment_bytes
from pageindex.infrastructure.llm import OpenAICompatibleLLMClient, get_active_llm_client
from pageindex.infrastructure.settings import resolve_model_name

from pageindex.core.utils.pdf.constants import (
    DEFAULT_IMAGE_ALT_TEXT,
    IMAGE_TITLE_PROMPT,
    MAX_IMAGE_TITLE_LENGTH,
)


def _extract_image_markdown_from_pymupdf_block(
    block: dict,
    pdf_path=None,
    page_no: int | None = None,
    image_index: int | None = None,
    render_images: bool = False,
    model: str | None = None,
) -> str:
    image_bytes = block.get("image")
    if not image_bytes or not render_images:
        return build_empty_image_markdown()

    ext = _normalize_image_extension(block.get("ext"))
    content_type = content_type_for_extension(ext)
    alt_text = _generate_image_alt_text(image_bytes, content_type=content_type, model=model)
    filename = build_uploaded_image_filename(
        pdf_path=pdf_path,
        page_no=page_no,
        image_index=image_index or 1,
        ext=ext,
    )

    attachment_id = upload_attachment_bytes(image_bytes, filename=filename, content_type=content_type)
    if attachment_id:
        block["_pageindex_uploaded_image"] = {
            "file_name": filename,
            "attachment_id": attachment_id,
            "img_title": alt_text,
            "page_no": page_no,
            "image_index": image_index or 1,
        }
        return build_markdown_image(filename, alt_text=alt_text)
    return build_empty_image_markdown(alt_text=alt_text)


def build_empty_image_markdown(alt_text: str = DEFAULT_IMAGE_ALT_TEXT) -> str:
    return build_markdown_image("image", alt_text).replace("(image)", "")


def _normalize_image_extension(ext: str | None) -> str:
    normalized = (ext or "png").strip().lower()
    return "jpeg" if normalized == "jpg" else normalized


def content_type_for_extension(ext: str) -> str:
    return "image/jpeg" if ext == "jpeg" else f"image/{ext}"


def build_pdf_image_filename(pdf_path, page_no: int, image_index: int, ext: str) -> str:
    base_name = Path(pdf_path).name
    suffix = "" if image_index == 1 else f"-{image_index}"
    return f"{base_name}-page-{page_no}{suffix}.{ext}"


def build_uploaded_image_filename(pdf_path=None, page_no: int | None = None, image_index: int = 1, ext: str = "png") -> str:
    if isinstance(pdf_path, (str, os.PathLike)) and page_no is not None:
        return build_pdf_image_filename(pdf_path, page_no, image_index, ext)
    page_prefix = f"page-{page_no}-" if page_no is not None else ""
    image_suffix = "" if image_index == 1 else f"{image_index}-"
    return f"{page_prefix}{image_suffix}image.{ext}"


def _generate_image_alt_text(image_bytes: bytes, content_type: str, model: str | None = None) -> str:
    generated = _summarize_image_with_llm(image_bytes, content_type=content_type, model=model)
    return _normalize_image_alt_text(generated)


def _summarize_image_with_llm(image_bytes: bytes, content_type: str, model: str | None = None) -> str | None:
    try:
        client = get_active_llm_client()
    except Exception:
        return None

    if not isinstance(client, OpenAICompatibleLLMClient):
        return None

    image_data = b64encode(image_bytes).decode("utf-8")
    content = [
        {"type": "text", "text": IMAGE_TITLE_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_data}"}},
    ]

    try:
        return client.generate_text_from_content(model=resolve_model_name(model), content=content)
    except Exception:
        return None


def _normalize_image_alt_text(value: str | None) -> str:
    if not value:
        return DEFAULT_IMAGE_ALT_TEXT

    first_line = value.strip().splitlines()[0].strip()
    first_line = re.sub(r"^[\"'“”‘’《〈【\[\(]+", "", first_line)
    first_line = re.sub(r"[\"'“”‘’》〉】\]\)]+$", "", first_line)
    first_line = re.sub(r"[。！!？?,，:：;；、]", "", first_line)
    first_line = " ".join(first_line.split())
    if not first_line:
        return DEFAULT_IMAGE_ALT_TEXT
    if len(first_line) > MAX_IMAGE_TITLE_LENGTH:
        first_line = first_line[:MAX_IMAGE_TITLE_LENGTH].rstrip()
    return first_line or DEFAULT_IMAGE_ALT_TEXT
