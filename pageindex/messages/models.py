from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CallbackTarget:
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class SubmittedFile:
    original_name: str
    content: bytes


@dataclass(frozen=True)
class RemoteFileReference:
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class IndexTaskRequest:
    task_id: str
    index_options: dict[str, Any]
    callback: CallbackTarget
    uploaded_file: SubmittedFile | None = None
    remote_file: RemoteFileReference | None = None
