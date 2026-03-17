from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request

from pageindex.messages.models import CallbackTarget, IndexTaskRequest, RemoteFileReference, SubmittedFile


async def parse_task_request(request: Request) -> IndexTaskRequest:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        payload, uploaded_file = await _parse_multipart_payload(request)
    else:
        payload, uploaded_file = await _parse_json_payload(request)

    task_id = payload.get("task_id")
    callback_url = payload.get("callback_url")
    remote_file_url = payload.get("remote_file_url")

    if not task_id or not callback_url:
        raise HTTPException(status_code=400, detail="task_id and callback_url are required")
    if uploaded_file is None and not remote_file_url:
        raise HTTPException(status_code=400, detail="Either file or remote_file_url must be provided")
    if uploaded_file is not None and remote_file_url:
        raise HTTPException(status_code=400, detail="file and remote_file_url are mutually exclusive")

    return IndexTaskRequest(
        task_id=str(task_id),
        index_options=payload.get("index_options") or {},
        callback=CallbackTarget(
            url=str(callback_url),
            headers={str(k): str(v) for k, v in (payload.get("callback_headers") or {}).items()},
        ),
        uploaded_file=uploaded_file,
        remote_file=RemoteFileReference(
            url=str(remote_file_url),
            headers={str(k): str(v) for k, v in (payload.get("remote_file_headers") or {}).items()},
        )
        if remote_file_url
        else None,
    )


async def _parse_multipart_payload(request: Request) -> tuple[dict[str, Any], SubmittedFile | None]:
    form = await request.form()
    file_obj = form.get("file")
    uploaded_file = None
    if file_obj is not None and hasattr(file_obj, "read") and hasattr(file_obj, "filename"):
        uploaded_file = SubmittedFile(
            original_name=file_obj.filename or "uploaded.bin",
            content=await file_obj.read(),
        )

    payload = {
        "task_id": form.get("task_id"),
        "index_options": _parse_json_field(form.get("index_options"), "index_options"),
        "callback_url": form.get("callback_url"),
        "callback_headers": _parse_json_field(form.get("callback_headers"), "callback_headers", default={}),
        "remote_file_url": form.get("remote_file_url"),
        "remote_file_headers": _parse_json_field(
            form.get("remote_file_headers"),
            "remote_file_headers",
            default={},
        ),
    }
    return payload, uploaded_file


async def _parse_json_payload(request: Request) -> tuple[dict[str, Any], SubmittedFile | None]:
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON request body must be an object")

    payload["index_options"] = _require_mapping(payload.get("index_options"), "index_options")
    payload["callback_headers"] = _require_mapping(payload.get("callback_headers"), "callback_headers")
    payload["remote_file_headers"] = _require_mapping(payload.get("remote_file_headers"), "remote_file_headers")
    return payload, None


def _parse_json_field(raw_value: Any, field_name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if raw_value in (None, ""):
        return default or {}
    if isinstance(raw_value, dict):
        return raw_value
    try:
        return _require_mapping(json.loads(str(raw_value)), field_name)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in {field_name}: {exc}") from exc


def _require_mapping(raw_value: Any, field_name: str) -> dict[str, Any]:
    if raw_value in (None, ""):
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object")
