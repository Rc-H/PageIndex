from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceSettings:
    libreoffice_command: str = "libreoffice"
    doc_conversion_timeout_seconds: int = 120
    remote_file_timeout_seconds: int = 60
    callback_timeout_seconds: int = 30
    callback_retry_count: int = 3
    seq_url: str = ""
    seq_api_key: str | None = None
    log_level: str = "INFO"
    log_timeout_seconds: int = 5
    attachment_upload_domain: str = ""
    attachment_upload_api_key: str | None = None


def load_service_settings() -> ServiceSettings:
    return ServiceSettings(
        libreoffice_command=os.getenv("PAGEINDEX_LIBREOFFICE_COMMAND", "libreoffice"),
        doc_conversion_timeout_seconds=int(os.getenv("PAGEINDEX_DOC_CONVERSION_TIMEOUT_SECONDS", "120")),
        remote_file_timeout_seconds=int(os.getenv("PAGEINDEX_REMOTE_FILE_TIMEOUT_SECONDS", "60")),
        callback_timeout_seconds=int(os.getenv("PAGEINDEX_CALLBACK_TIMEOUT_SECONDS", "30")),
        callback_retry_count=int(os.getenv("PAGEINDEX_CALLBACK_RETRY_COUNT", "3")),
        seq_url=os.getenv("PAGEINDEX_SEQ_URL", ""),
        seq_api_key=os.getenv("PAGEINDEX_SEQ_API_KEY") or None,
        log_level=os.getenv("PAGEINDEX_LOG_LEVEL", "INFO"),
        log_timeout_seconds=int(os.getenv("PAGEINDEX_LOG_TIMEOUT_SECONDS", "5")),
        attachment_upload_domain=os.getenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", ""),
        attachment_upload_api_key=os.getenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY") or None,
    )
