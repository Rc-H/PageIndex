from __future__ import annotations

import logging
import mimetypes
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

from pageindex.infrastructure.settings import load_settings


logger = logging.getLogger(__name__)


def upload_image_bytes(content: bytes, filename: str, content_type: str | None = None) -> str | None:
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
        logger.warning("Failed to upload image %s: %s", filename, exc)
        return None

    if not uuid:
        logger.warning("Attachment upload succeeded without uuid for %s", filename)
        return None
    return f"![image]({uuid})"


def infer_filename_from_url(url: str, default_stem: str = "image") -> str:
    parsed = urlparse(url)
    name = PurePosixPath(parsed.path).name
    if name:
        return name
    return f"{default_stem}.bin"
