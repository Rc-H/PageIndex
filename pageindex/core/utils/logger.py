from __future__ import annotations

import json
import logging
import traceback
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any


_STANDARD_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def _to_seq_level(level_name: str) -> str:
    return {
        "CRITICAL": "Fatal",
        "ERROR": "Error",
        "WARNING": "Warning",
        "INFO": "Information",
        "DEBUG": "Debug",
        "NOTSET": "Verbose",
    }.get(level_name, level_name.title())


def _normalize_seq_url(server_url: str) -> str:
    return f"{server_url.rstrip('/')}/api/events/raw?clef"


def _iso_utc_from_record(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _extract_properties(record: logging.LogRecord) -> dict[str, Any]:
    properties = {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
    }
    return properties


class SeqLogHandler(logging.Handler):
    def __init__(self, server_url: str, api_key: str | None = None, timeout_seconds: int = 5):
        super().__init__()
        self._url = _normalize_seq_url(server_url)
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = self._build_event(record)
            payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            headers = {"Content-Type": "application/vnd.serilog.clef"}
            if self._api_key:
                headers["X-Seq-ApiKey"] = self._api_key

            request = urllib.request.Request(
                self._url,
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self._timeout_seconds):
                return
        except Exception:
            self.handleError(record)

    def _build_event(self, record: logging.LogRecord) -> dict[str, Any]:
        properties = _extract_properties(record)
        if isinstance(record.msg, dict):
            properties.update(record.msg)
            message_template = record.msg.get("message", "structured log")
        else:
            message_template = record.getMessage()

        event: dict[str, Any] = {
            "@t": _iso_utc_from_record(record),
            "@mt": message_template,
            "@l": _to_seq_level(record.levelname),
            "logger": record.name,
        }
        if properties:
            event.update(properties)
        if record.exc_info:
            event["@x"] = "".join(traceback.format_exception(*record.exc_info))
        return event


class SeqLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        extra = dict(self.extra)
        extra.update(kwargs.get("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(
    *,
    seq_url: str,
    seq_api_key: str | None = None,
    level: str = "INFO",
    timeout_seconds: int = 5,
) -> None:
    if not seq_url:
        raise ValueError("PAGEINDEX_SEQ_URL must be configured")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(SeqLogHandler(seq_url, api_key=seq_api_key, timeout_seconds=timeout_seconds))


def get_logger(name: str, **context: Any) -> logging.Logger | SeqLoggerAdapter:
    logger = logging.getLogger(name)
    if context:
        return SeqLoggerAdapter(logger, context)
    return logger


__all__ = [
    "SeqLogHandler",
    "SeqLoggerAdapter",
    "configure_logging",
    "get_logger",
]
