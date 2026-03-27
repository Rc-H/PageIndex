from __future__ import annotations

import logging
import mimetypes
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx

from pageindex.infrastructure.settings import load_settings


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
) -> str | None:
    attachment_id = upload_attachment_bytes(content, filename, content_type)
    if not attachment_id:
        return None
    return build_markdown_image(str(attachment_id), alt_text=alt_text)


def infer_filename_from_url(url: str, default_stem: str = "image") -> str:
    parsed = urlparse(url)
    name = PurePosixPath(parsed.path).name
    if name:
        return name
    return f"{default_stem}.bin"
