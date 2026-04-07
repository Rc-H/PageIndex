from __future__ import annotations

import mimetypes
import re
from urllib.parse import urlparse

import httpx

from pageindex.core.utils.image_upload import infer_filename_from_url, upload_image_bytes
from pageindex.infrastructure.settings import load_settings

try:
    from docx.oxml.ns import qn
    from docx.text.run import Run
except Exception:
    qn = None
    Run = None


def get_heading_level(style_name: str) -> int | None:
    match = re.search(r"heading\s+(\d+)", style_name or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_table_cell_text(
    cell,
    image_cache: dict[object, str] | None = None,
    nested_table_renderer=None,
) -> str:
    """Render a single table cell as plain text.

    When ``nested_table_renderer`` is supplied, any tables nested directly
    inside the cell are also rendered (recursively, via the renderer) and
    their textualization is appended to the cell's parts list. The dedup
    ``seen`` set still applies, so a nested table whose textualization is
    identical to an existing paragraph is dropped.
    """

    parts: list[str] = []
    seen: set[str] = set()
    for paragraph in cell.paragraphs:
        text = extract_paragraph_text(paragraph, image_cache=image_cache).strip()
        if text and text not in seen:
            parts.append(text)
            seen.add(text)
    if nested_table_renderer is not None:
        for nested_table in cell.tables:
            nested_text = nested_table_renderer(nested_table, image_cache=image_cache).strip()
            if nested_text and nested_text not in seen:
                parts.append(nested_text)
                seen.add(nested_text)
    return " ".join(parts)


def extract_paragraph_text(paragraph, image_cache: dict[object, str] | None = None) -> str:
    if Run is None or qn is None:
        return paragraph.text.strip()

    cache = image_cache if image_cache is not None else {}
    parts: list[str] = []
    hyperlink_field_url: str | None = None
    hyperlink_field_text_parts: list[str] = []
    is_collecting_field_text = False

    def append_text(target: list[str], text: str):
        if text:
            target.append(text)

    def append_image(target: list[str], rel, rel_key: object):
        markdown = resolve_image_markdown(rel, rel_key, cache)
        target.append(markdown)

    def process_run(run, target: list[str]):
        drawing_elements = run.element.findall(
            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
        )
        has_drawing = False
        for drawing in drawing_elements:
            blip_elements = drawing.findall(
                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
            )
            for blip in blip_elements:
                embed_id = blip.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                )
                if embed_id and embed_id in paragraph.part.rels:
                    has_drawing = True
                    append_image(target, paragraph.part.rels[embed_id], embed_id)

        shape_elements = run.element.findall(
            ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pict"
        )
        for shape in shape_elements:
            shape_image = shape.find(
                ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}binData"
            )
            image_data = shape.find(".//{urn:schemas-microsoft-com:vml}imagedata")
            if shape_image is not None or image_data is not None:
                if not has_drawing:
                    rel_id = None
                    if shape_image is not None:
                        rel_id = shape_image.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    if image_data is not None:
                        rel_id = rel_id or image_data.get("id") or image_data.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                        )
                    if rel_id and rel_id in paragraph.part.rels:
                        append_image(target, paragraph.part.rels[rel_id], rel_id)
                    else:
                        target.append("![image]")
                has_drawing = True

        text = run.text.strip()
        if text:
            append_text(target, text)

    def process_hyperlink(hyperlink_elem, target: list[str]):
        r_id = hyperlink_elem.get(qn("r:id"))
        link_text_parts: list[str] = []
        for run_elem in hyperlink_elem.findall(qn("w:r")):
            run = Run(run_elem, paragraph)
            if run.text:
                link_text_parts.append(run.text)

        link_text = "".join(link_text_parts).strip()
        if r_id:
            rel = paragraph.part.rels.get(r_id)
            if rel and getattr(rel, "is_external", False):
                append_text(target, f"[{link_text or rel.target_ref}]({rel.target_ref})")
                return
        append_text(target, link_text)

    for child in paragraph._element:
        tag = child.tag
        if tag == qn("w:r"):
            run = Run(child, paragraph)
            fld_chars = child.findall(qn("w:fldChar"))
            instr_texts = child.findall(qn("w:instrText"))

            if fld_chars or instr_texts:
                for instr in instr_texts:
                    if instr.text and "HYPERLINK" in instr.text:
                        match = re.search(r'HYPERLINK\s+"([^"]+)"', instr.text, re.IGNORECASE)
                        if match:
                            hyperlink_field_url = match.group(1)

                for fld_char in fld_chars:
                    fld_char_type = fld_char.get(qn("w:fldCharType"))
                    if fld_char_type == "begin":
                        hyperlink_field_url = None
                        hyperlink_field_text_parts = []
                        is_collecting_field_text = False
                    elif fld_char_type == "separate":
                        if hyperlink_field_url:
                            is_collecting_field_text = True
                    elif fld_char_type == "end":
                        if is_collecting_field_text and hyperlink_field_url:
                            display_text = "".join(hyperlink_field_text_parts).strip()
                            if display_text:
                                append_text(parts, f"[{display_text}]({hyperlink_field_url})")
                        hyperlink_field_url = None
                        hyperlink_field_text_parts = []
                        is_collecting_field_text = False

            target = hyperlink_field_text_parts if is_collecting_field_text else parts
            process_run(run, target)
        elif tag == qn("w:hyperlink"):
            process_hyperlink(child, parts)

    return "".join(parts).strip()


def resolve_image_markdown(rel, rel_key: object, image_cache: dict[object, str]) -> str:
    cache_key = rel.target_part if not getattr(rel, "is_external", False) and hasattr(rel, "target_part") else rel_key
    if cache_key in image_cache:
        return image_cache[cache_key]

    markdown = None
    if getattr(rel, "is_external", False):
        markdown = upload_external_image(rel.target_ref)
    elif hasattr(rel, "target_part"):
        filename = infer_docx_part_filename(rel)
        content_type = mimetypes.guess_type(filename)[0]
        markdown = upload_image_bytes(rel.target_part.blob, filename=filename, content_type=content_type)

    image_cache[cache_key] = markdown or "![image]"
    return image_cache[cache_key]


def upload_external_image(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None

    timeout = load_settings().service.remote_file_timeout_seconds
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
        return upload_image_bytes(
            response.content,
            filename=infer_filename_from_url(url),
            content_type=response.headers.get("content-type"),
        )
    except Exception:
        return None


def infer_docx_part_filename(rel) -> str:
    target_ref = getattr(rel, "target_ref", "") or ""
    if "." in target_ref.rsplit("/", 1)[-1]:
        return target_ref.rsplit("/", 1)[-1]
    content_type = getattr(rel.target_part, "content_type", "") if hasattr(rel, "target_part") else ""
    extension = mimetypes.guess_extension(content_type) or ".bin"
    return f"image{extension}"


__all__ = [
    "Run",
    "extract_paragraph_text",
    "extract_table_cell_text",
    "get_heading_level",
    "infer_docx_part_filename",
    "qn",
    "resolve_image_markdown",
    "upload_external_image",
]
