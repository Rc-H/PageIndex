from __future__ import annotations

JSON_OBJECT_SCHEMA = {"type": "object", "additionalProperties": True}
STRING_MAP_SCHEMA = {"type": "object", "additionalProperties": {"type": "string"}}
URI_STRING_SCHEMA = {"type": "string", "format": "uri"}


def build_index_task_request_body() -> dict[str, object]:
    json_properties = {
        "task_id": {"type": "string"},
        "index_options": JSON_OBJECT_SCHEMA,
        "callback_url": URI_STRING_SCHEMA,
        "callback_headers": STRING_MAP_SCHEMA,
        "remote_file_url": URI_STRING_SCHEMA,
        "remote_file_headers": STRING_MAP_SCHEMA,
    }
    multipart_properties = {
        "task_id": {"type": "string"},
        "index_options": {"type": "string", "description": "JSON object string"},
        "callback_url": URI_STRING_SCHEMA,
        "callback_headers": {"type": "string", "description": "JSON object string"},
        "file": {"type": "string", "format": "binary"},
        "remote_file_url": URI_STRING_SCHEMA,
        "remote_file_headers": {"type": "string", "description": "JSON object string"},
    }

    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["task_id", "callback_url"],
                    "properties": json_properties,
                }
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["task_id", "callback_url"],
                    "properties": multipart_properties,
                }
            },
        },
    }


INDEX_TASK_REQUEST_BODY = build_index_task_request_body()
