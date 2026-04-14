import os
from pathlib import Path

from pageindex.core.utils.image_upload import (
    build_markdown_image,
    generate_image_alt_text,
    generate_image_description,
    normalize_image_alt_text,
    upload_attachment_bytes,
)
from pageindex.core.utils.image_constants import DEFAULT_IMAGE_ALT_TEXT


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

    if not _is_valid_image(image_bytes):
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
        description = _generate_image_description(image_bytes, content_type=content_type, model=model)
        block["_pageindex_uploaded_image"] = {
            "file_name": filename,
            "attachment_id": attachment_id,
            "img_title": alt_text,
            "img_description": description,
            "page_no": page_no,
            "image_index": image_index or 1,
        }
        markdown = build_markdown_image(filename, alt_text=alt_text)
        if description:
            markdown += f"\n[图片内容：{description}]"
        return markdown
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
    return generate_image_alt_text(image_bytes, content_type=content_type, model=model)


def _generate_image_description(image_bytes: bytes, content_type: str, model: str | None = None) -> str:
    return generate_image_description(image_bytes, content_type=content_type, model=model)


def _is_valid_image(image_bytes: bytes) -> bool:
    """Check if image bytes can be decoded by PIL before sending to LLM."""
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        return True
    except Exception:
        return False


# Keep _normalize_image_alt_text as a module-level alias for existing test imports
_normalize_image_alt_text = normalize_image_alt_text
