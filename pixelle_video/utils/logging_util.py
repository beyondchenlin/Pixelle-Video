from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from loguru import logger


_SENSITIVE_TOKENS = ("api_key", "authorization", "bearer", "token", "secret", "password")
_REQUIRED_FIELDS = (
    "timestamp",
    "level",
    "service",
    "channel",
    "message",
    "request_id",
    "session_id",
    "api_task_id",
    "task_id",
    "pipeline",
    "stage",
    "event",
    "status",
    "provider",
    "model",
    "latency_ms",
    "llm_call_count",
    "retry_count",
    "attempt",
    "batch_index",
    "batch_total",
    "narration_count",
    "workflow",
    "template",
)


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in _SENSITIVE_TOKENS)


def redact_mapping(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("***" if is_sensitive_key(key) else redact_mapping(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_mapping(item) for item in payload]
    return payload


def redact_text(message: str) -> str:
    redacted = str(message)
    token_pattern = "|".join(re.escape(token) for token in _SENSITIVE_TOKENS)
    assignment_pattern = re.compile(
        rf"([A-Za-z0-9_]*(?:{token_pattern})[A-Za-z0-9_]*['\"]?\s*[:=]\s*['\"]?)"
        rf"([^,'\"\s}}]+)",
        re.IGNORECASE,
    )
    redacted = assignment_pattern.sub(r"\1***", redacted)
    return re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", redacted, flags=re.IGNORECASE)


def build_content_observability(content: str | None, *, preview_chars: int = 120) -> dict[str, Any]:
    value = content or ""
    preview = value[:preview_chars]
    if len(value) > preview_chars:
        preview = f"{preview}..."
    return {
        "input_length": len(value),
        "content_hash": hashlib.sha256(value.encode("utf-8")).hexdigest()[:16],
        "preview": preview,
    }


def new_correlation_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def build_log_payload(record: dict[str, Any], *, service_name: str) -> dict[str, Any]:
    extra = redact_mapping(dict(record["extra"]))
    extra.pop("jsonl_payload", None)

    payload = {field: None for field in _REQUIRED_FIELDS}
    payload.update(
        {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "service": extra.get("service") or service_name,
            "channel": extra.get("channel", "runtime"),
            "message": redact_text(record["message"]),
            "extra": extra,
        }
    )
    for field in _REQUIRED_FIELDS:
        if field not in {"timestamp", "level", "service", "channel", "message"}:
            payload[field] = extra.get(field)
    return payload


def _resolve_logging_config(config: dict[str, Any] | None) -> dict[str, Any]:
    defaults = {
        "enabled": True,
        "level": "INFO",
        "log_dir": "logs",
        "rotation_mb": 50,
        "retention_days": 14,
        "task_logs_enabled": True,
        "ai_creation_logs_enabled": True,
        "preview_chars": 120,
    }
    return {**defaults, **(config or {})}


def _patch_record(service_name: str) -> Any:
    def _patch(record: dict[str, Any]) -> None:
        payload = build_log_payload(record, service_name=service_name)
        record["extra"]["jsonl_payload"] = json.dumps(payload, ensure_ascii=False, default=str)

    return _patch


def _serialize_record(record: dict[str, Any], *, service_name: str) -> str:
    return json.dumps(build_log_payload(record, service_name=service_name), ensure_ascii=False, default=str) + "\n"


def _jsonl_sink(path: Path, *, service_name: str) -> Any:
    def _write(message) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_serialize_record(message.record, service_name=service_name))

    return _write


def setup_logging(service_name: str, config: dict[str, Any] | None = None) -> list[int]:
    resolved = _resolve_logging_config(config)
    if not resolved["enabled"]:
        return []

    log_dir = Path(resolved["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(extra={"service": service_name}, patcher=_patch_record(service_name))
    console_sink = logger.add(sys.stderr, level=resolved["level"])
    file_sink = logger.add(
        log_dir / f"{service_name}.jsonl",
        level=resolved["level"],
        format="{extra[jsonl_payload]}\n",
        rotation=f"{resolved['rotation_mb']} MB",
        retention=f"{resolved['retention_days']} days",
    )
    return [console_sink, file_sink]


def teardown_logging(sink_ids: list[int]) -> None:
    for sink_id in sink_ids:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass


@dataclass
class TaskLogSession:
    sink_ids: list[int]
    context_manager: Any
    _closed: bool = field(default=False, init=False)

    def close(self) -> None:
        if self._closed:
            return
        for sink_id in self.sink_ids:
            try:
                logger.remove(sink_id)
            except ValueError:
                pass
        self.context_manager.__exit__(None, None, None)
        self._closed = True


def attach_task_log_sinks(
    *,
    task_id: str,
    task_dir: Path,
    service_name: str = "pipeline",
    ai_creation_enabled: bool = True,
) -> TaskLogSession:
    logs_dir = Path(task_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    def _task_filter(record: dict[str, Any]) -> bool:
        return record["extra"].get("task_id") == task_id

    def _ai_creation_filter(record: dict[str, Any]) -> bool:
        return _task_filter(record) and record["extra"].get("channel") == "ai_creation"

    context_manager = logger.contextualize(task_id=task_id, service=service_name)
    context_manager.__enter__()
    runtime_sink = logger.add(
        _jsonl_sink(logs_dir / "runtime.jsonl", service_name=service_name),
        filter=_task_filter,
    )
    sink_ids = [runtime_sink]
    if ai_creation_enabled:
        sink_ids.append(
            logger.add(
                _jsonl_sink(logs_dir / "ai_creation.jsonl", service_name=service_name),
                filter=_ai_creation_filter,
            )
        )
    return TaskLogSession(sink_ids=sink_ids, context_manager=context_manager)


@contextmanager
def bind_log_context(**context: Any) -> Iterator[None]:
    clean_context = {key: value for key, value in context.items() if value is not None}
    with logger.contextualize(**clean_context):
        yield
