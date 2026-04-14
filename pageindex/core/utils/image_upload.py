from __future__ import annotations

import logging
import mimetypes
import re
from base64 import b64encode
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx

from pageindex.core.utils.image_constants import (
    DEFAULT_IMAGE_ALT_TEXT,
    IMAGE_DESCRIPTION_PROMPT,
    IMAGE_TITLE_PROMPT,
    MAX_IMAGE_DESCRIPTION_LENGTH,
    MAX_IMAGE_TITLE_LENGTH,
)
from pageindex.infrastructure.llm import OpenAICompatibleLLMClient, get_active_llm_client
from pageindex.infrastructure.settings import load_settings, resolve_model_name


logger = logging.getLogger(__name__)


def build_markdown_image(reference: str, alt_text: str = "image") -> str:
    safe_alt_text = " ".join((alt_text or "image").strip().split()) or "image"
    safe_alt_text = safe_alt_text.replace("[", "(").replace("]", ")")
    return f"![{safe_alt_text}]({reference})"


def save_image_bytes(content: bytes, output_path: str | Path) -> str | None:
    if not content:
        return None

    try:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except Exception as exc:
        logger.warning("Failed to save image %s: %s", output_path, exc)
        return None

    return str(path)


def upload_attachment_bytes(content: bytes, filename: str, content_type: str | None = None) -> str | None:
    if not content:
        return None

    service = load_settings().service
    domain = service.attachment_upload_domain.strip()
    if not domain:
        return None

    headers: dict[str, str] = {}
    if service.attachment_upload_api_key:
        headers["x-api-key"] = service.attachment_upload_api_key

    mime_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    upload_url = domain.rstrip("/") + "/api/Attachment/upload"

    try:
        with httpx.Client(timeout=service.remote_file_timeout_seconds, headers=headers or None) as client:
            response = client.post(upload_url, files={"file": (filename, content, mime_type)})
            response.raise_for_status()
        uuid = response.json().get("data", {}).get("uuid")
    except Exception as exc:
        logger.warning("Failed to upload attachment %s: %s", filename, exc)
        return None

    if not uuid:
        logger.warning("Attachment upload succeeded without uuid for %s", filename)
        return None

    return str(uuid)


def upload_image_bytes(
    content: bytes,
    filename: str,
    content_type: str | None = None,
    alt_text: str = "image",
    model: str | None = None,
) -> str | None:
    attachment_id = upload_attachment_bytes(content, filename, content_type)
    if not attachment_id:
        return None

    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    generated_alt = generate_image_alt_text(content, content_type=mime, model=model)
    if generated_alt and generated_alt != DEFAULT_IMAGE_ALT_TEXT:
        alt_text = generated_alt

    markdown = build_markdown_image(str(attachment_id), alt_text=alt_text)

    description = generate_image_description(content, content_type=mime, model=model)
    if description:
        markdown += f"\n[图片内容：{description}]"

    return markdown


def summarize_image_with_llm(
    image_bytes: bytes, content_type: str, model: str | None = None, prompt: str | None = None
) -> str | None:
    try:
        client = get_active_llm_client()
    except Exception:
        return None

    if not isinstance(client, OpenAICompatibleLLMClient):
        return None

    from pageindex.core.utils.rate_limiter import get_rate_limiter
    get_rate_limiter().wait()

    image_data = b64encode(image_bytes).decode("utf-8")
    content = [
        {"type": "text", "text": prompt or IMAGE_TITLE_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_data}"}},
    ]

    try:
        return client.generate_text_from_content(model=resolve_model_name(model), content=content)
    except Exception:
        return None


def generate_image_alt_text(image_bytes: bytes, content_type: str, model: str | None = None) -> str:
    generated = summarize_image_with_llm(image_bytes, content_type=content_type, model=model)
    return normalize_image_alt_text(generated)


def generate_image_description(image_bytes: bytes, content_type: str, model: str | None = None) -> str:
    generated = summarize_image_with_llm(
        image_bytes, content_type=content_type, model=model, prompt=IMAGE_DESCRIPTION_PROMPT
    )
    return normalize_image_description(generated)


def normalize_image_description(value: str | None) -> str:
    if not value:
        return ""
    text = " ".join(value.strip().split())
    if len(text) > MAX_IMAGE_DESCRIPTION_LENGTH:
        text = text[:MAX_IMAGE_DESCRIPTION_LENGTH].rstrip()
    return text


def normalize_image_alt_text(value: str | None) -> str:
    if not value:
        return DEFAULT_IMAGE_ALT_TEXT

    first_line = value.strip().splitlines()[0].strip()
    first_line = re.sub(r"^[\"'\u201c\u201d\u2018\u2019《〈【\[\(]+", "", first_line)
    first_line = re.sub(r"[\"'\u201c\u201d\u2018\u2019》〉】\]\)]+$", "", first_line)
    first_line = re.sub(r"[。！!？?,，:：;；、]", "", first_line)
    first_line = " ".join(first_line.split())
    if not first_line:
        return DEFAULT_IMAGE_ALT_TEXT
    if len(first_line) > MAX_IMAGE_TITLE_LENGTH:
        first_line = first_line[:MAX_IMAGE_TITLE_LENGTH].rstrip()
    return first_line or DEFAULT_IMAGE_ALT_TEXT


def infer_filename_from_url(url: str, default_stem: str = "image") -> str:
    parsed = urlparse(url)
    name = PurePosixPath(parsed.path).name
    if name:
        return name
    return f"{default_stem}.bin"
