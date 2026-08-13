from __future__ import annotations

import hashlib
import json
import re
import sys
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterator

from loguru import logger

from pixelle_video.utils.os_util import get_pixelle_video_root_path, get_runtime_path
from pixelle_video.utils.secret_redaction import (
    is_sensitive_key,
    redact_credentials_in_text,
)

_PRIVATE_TEXT_KEYS = frozenset(
    {
        "caption_text",
        "content",
        "goods_text",
        "goods_title",
        "narration",
        "prompt",
        "prompt_text",
        "ref_audio_text",
        "reference_audio_text",
        "script",
        "source_text",
        "text",
        "title",
        "transcript",
    }
)
_PRIVATE_PATH_KEYS = frozenset(
    {
        "audio_path",
        "bgm_path",
        "file_path",
        "image_path",
        "path",
        "ref_audio",
        "reference_audio",
        "video_path",
    }
)
_PRIVATE_ASSET_COLLECTION_KEYS = frozenset(
    {
        "assets",
        "audio_assets",
        "character_assets",
        "goods_assets",
        "image_assets",
        "video_assets",
    }
)
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
    "exception_type",
    "exception_message",
    "exception_message_length",
    "exception_message_hash",
    "exception_traceback",
)

_EXCEPTION_LOGGED_ATTRIBUTE = "_pixelle_exception_logged"
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/](?:[^\\/\s:'\"<>|]+[\\/]?)+)"
)
_UNC_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_\\])(?:\\\\[^\\\s:'\"<>|]+\\[^\s:'\"<>|]+)"
)
_POSIX_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![:A-Za-z0-9_>])(?:/(?:[^/\s:'\"<>|]+/?)+)"
)


def _normalized_log_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(key).strip().lower())


def _is_private_text_key(key: Any) -> bool:
    return _normalized_log_key(key) in _PRIVATE_TEXT_KEYS


def _is_private_path_key(key: Any) -> bool:
    return _normalized_log_key(key) in _PRIVATE_PATH_KEYS


def _is_private_asset_collection_key(key: Any) -> bool:
    return _normalized_log_key(key) in _PRIVATE_ASSET_COLLECTION_KEYS


def _private_text_observability(value: Any) -> dict[str, Any]:
    text = str(value or "")
    return {
        "input_length": len(text),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "redacted": True,
    }


def _private_path_observability(value: Any) -> dict[str, Any]:
    text = str(value or "")
    return {
        "path_present": bool(text),
        "suffix": Path(text).suffix.lower() if text else "",
        "redacted": True,
    }


def _private_asset_collection_observability(value: Any) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        count = len(value)
    elif value:
        count = 1
    else:
        count = 0
    return {"count": count, "redacted": True}


def redact_mapping(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted = {}
        for key, value in payload.items():
            if is_sensitive_key(key):
                redacted[key] = "***"
            elif _is_private_text_key(key) and isinstance(value, str):
                redacted[key] = _private_text_observability(value)
            elif _is_private_path_key(key) and isinstance(value, (str, Path)):
                redacted[key] = _private_path_observability(value)
            elif _is_private_asset_collection_key(key):
                redacted[key] = _private_asset_collection_observability(value)
            else:
                redacted[key] = redact_mapping(value)
        return redacted
    if isinstance(payload, list):
        return [redact_mapping(item) for item in payload]
    return payload


def redact_text(message: str) -> str:
    redacted = redact_credentials_in_text(message)

    private_keys = sorted(
        _PRIVATE_TEXT_KEYS | _PRIVATE_PATH_KEYS | _PRIVATE_ASSET_COLLECTION_KEYS,
        key=len,
        reverse=True,
    )
    private_key_pattern = "|".join(re.escape(key) for key in private_keys)
    quoted_private_assignment_pattern = re.compile(
        rf"((?<![A-Za-z0-9_])['\"]?(?:{private_key_pattern})['\"]?\s*[:=]\s*)(['\"])(.*?)(\2)",
        re.IGNORECASE | re.DOTALL,
    )
    collection_private_assignment_pattern = re.compile(
        rf"((?<![A-Za-z0-9_])['\"]?(?:{private_key_pattern})['\"]?\s*[:=]\s*)\[[^\]]*\]",
        re.IGNORECASE | re.DOTALL,
    )
    redacted = quoted_private_assignment_pattern.sub(r"\1\2***\4", redacted)
    redacted = collection_private_assignment_pattern.sub(r"\1[***]", redacted)
    return redacted


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


def _diagnostic_path(path_text: str) -> str:
    """Return a useful traceback path without exposing machine-specific roots."""

    if path_text.startswith("\\\\"):
        return f"<unc-path>/{PureWindowsPath(path_text).name}"
    if PureWindowsPath(path_text).is_absolute():
        project_root = str(Path(get_pixelle_video_root_path()).resolve()).replace("/", "\\")
        normalized = str(PureWindowsPath(path_text)).replace("/", "\\")
        root_prefix = f"{project_root.rstrip(chr(92))}{chr(92)}"
        if normalized.casefold().startswith(root_prefix.casefold()):
            relative_path = normalized[len(root_prefix) :].replace(chr(92), "/")
            return f"<project-root>/{relative_path}"
        return f"<absolute-path>/{PureWindowsPath(path_text).name}"
    if PurePosixPath(path_text).is_absolute() and Path(path_text).anchor != Path(path_text).drive:
        try:
            path = Path(path_text).resolve()
            project_root = Path(get_pixelle_video_root_path()).resolve()
            if path.is_relative_to(project_root):
                return f"<project-root>/{path.relative_to(project_root).as_posix()}"
        except (OSError, RuntimeError, ValueError):
            pass
        return f"<absolute-path>/{PurePosixPath(path_text).name}"
    try:
        path = Path(path_text).resolve()
        project_root = Path(get_pixelle_video_root_path()).resolve()
        if path == project_root:
            return "<project-root>"
        if path.is_relative_to(project_root):
            return f"<project-root>/{path.relative_to(project_root).as_posix()}"
        return f"<external>/{path.name}"
    except (OSError, RuntimeError, ValueError):
        return f"<external>/{Path(path_text).name}"


def _sanitize_diagnostic_text(value: object) -> str:
    text = redact_text(str(value or ""))
    root = str(Path(get_pixelle_video_root_path()).resolve())
    for root_variant in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
        text = text.replace(root_variant, "<project-root>")
    text = _UNC_PATH_RE.sub(
        lambda match: _diagnostic_path(match.group(0)),
        text,
    )
    text = _WINDOWS_ABSOLUTE_PATH_RE.sub(
        lambda match: _diagnostic_path(match.group(0)),
        text,
    )
    return _POSIX_ABSOLUTE_PATH_RE.sub(
        lambda match: _diagnostic_path(match.group(0)),
        text,
    )


def _format_safe_traceback(traceback_exception: traceback.TracebackException) -> str:
    """Format stack structure without persisting exception message bodies."""

    sections: list[str] = []
    if traceback_exception.__cause__ is not None:
        sections.append(_format_safe_traceback(traceback_exception.__cause__))
        sections.append("The above exception was the direct cause of the following exception:")
    elif (
        traceback_exception.__context__ is not None
        and not traceback_exception.__suppress_context__
    ):
        sections.append(_format_safe_traceback(traceback_exception.__context__))
        sections.append("During handling of the above exception, another exception occurred:")

    if traceback_exception.stack:
        sections.append("Traceback (most recent call last):")
        for frame in traceback_exception.stack:
            sections.append(
                f'  File "{_diagnostic_path(frame.filename)}", '
                f"line {frame.lineno}, in {frame.name}"
            )

    exception_type = traceback_exception.exc_type
    sections.append(exception_type.__name__ if exception_type is not None else "Exception")
    for child in getattr(traceback_exception, "exceptions", None) or ():
        sections.append("Nested exception:")
        sections.append(_format_safe_traceback(child))
    return "\n".join(section for section in sections if section)


def _exception_observability(record: dict[str, Any]) -> dict[str, str | None]:
    exception = record.get("exception")
    if exception is None:
        return {
            "exception_type": None,
            "exception_message": None,
            "exception_message_length": None,
            "exception_message_hash": None,
            "exception_traceback": None,
        }

    exception_type, exception_value, exception_traceback = exception
    raw_message = str(exception_value or "")
    formatted = _format_safe_traceback(
        traceback.TracebackException(
            exception_type,
            exception_value,
            exception_traceback,
            compact=True,
        )
    )
    return {
        "exception_type": exception_type.__name__,
        "exception_message": "<redacted>",
        "exception_message_length": len(raw_message),
        "exception_message_hash": hashlib.sha256(raw_message.encode("utf-8")).hexdigest()[:16],
        "exception_traceback": _sanitize_diagnostic_text(formatted),
    }


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
            "message": (
                f"{record['exception'].type.__name__} raised"
                if record.get("exception") is not None
                and record["message"] == str(record["exception"].value)
                else redact_text(record["message"])
            ),
            "extra": extra,
        }
    )
    for field_name in _REQUIRED_FIELDS:
        if field_name not in {"timestamp", "level", "service", "channel", "message"}:
            payload[field_name] = extra.get(field_name)
    payload.update(_exception_observability(record))
    return payload


def _resolve_logging_config(config: dict[str, Any] | None) -> dict[str, Any]:
    defaults = {
        "enabled": True,
        "level": "INFO",
        "log_dir": "_runtime/logs",
        "rotation_mb": 50,
        "retention_days": 14,
        "task_logs_enabled": True,
        "ai_creation_logs_enabled": True,
        "preview_chars": 120,
    }
    resolved = {**defaults, **(config or {})}
    log_dir = str(resolved.get("log_dir", "")).replace("\\", "/").rstrip("/")
    if log_dir == "logs":
        resolved["log_dir"] = get_runtime_path("logs")
    elif log_dir == "_runtime/logs" or log_dir.startswith("_runtime/"):
        resolved["log_dir"] = get_runtime_path(*log_dir.split("/")[1:])
    return resolved


def _patch_record(service_name: str) -> Any:
    def _patch(record: dict[str, Any]) -> None:
        payload = build_log_payload(record, service_name=service_name)
        record["extra"]["jsonl_payload"] = json.dumps(payload, ensure_ascii=False, default=str)
        record["extra"]["redacted_message"] = payload["message"]
        traceback_text = payload.get("exception_traceback")
        record["extra"]["console_exception"] = (
            f"\n{traceback_text}" if traceback_text else ""
        )
        # Core sinks use callable formatters, so Loguru does not append its raw
        # exception rendering after this safe representation. The original
        # exception remains on the record for compatibility with additional sinks.

    return _patch


def _serialize_record(record: dict[str, Any], *, service_name: str) -> str:
    precomputed = record["extra"].get("jsonl_payload")
    if isinstance(precomputed, str):
        return f"{precomputed}\n"
    return json.dumps(
        build_log_payload(record, service_name=service_name),
        ensure_ascii=False,
        default=str,
    ) + "\n"


def _jsonl_sink(path: Path, *, service_name: str) -> Any:
    def _write(message) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_serialize_record(message.record, service_name=service_name))

    return _write


def _console_log_format(_record: dict[str, Any]) -> str:
    # A callable formatter avoids Loguru's implicit raw ``{exception}`` suffix.
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{extra[redacted_message]}</level>"
        "<level>{extra[console_exception]}</level>\n"
    )


def _jsonl_log_format(_record: dict[str, Any]) -> str:
    # Callable formatters must provide their own terminator. The exception is
    # already captured inside the one-line JSON payload.
    return "{extra[jsonl_payload]}\n"


def setup_logging(service_name: str, config: dict[str, Any] | None = None) -> list[int]:
    resolved = _resolve_logging_config(config)
    if not resolved["enabled"]:
        return []

    log_dir = Path(resolved["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(extra={"service": service_name}, patcher=_patch_record(service_name))
    console_sink = logger.add(
        sys.stderr,
        level=resolved["level"],
        format=_console_log_format,
        diagnose=False,
    )
    file_sink = logger.add(
        log_dir / f"{service_name}.jsonl",
        level=resolved["level"],
        format=_jsonl_log_format,
        rotation=f"{resolved['rotation_mb']} MB",
        retention=f"{resolved['retention_days']} days",
        diagnose=False,
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


def emit_stage_event(
    *,
    channel: str,
    stage: str,
    event: str,
    message: str,
    callback: Callable[[dict[str, Any]], None] | None = None,
    **fields: Any,
) -> None:
    payload = {"channel": channel, "stage": stage, "event": event, **fields}
    logger.bind(**payload).info(message)
    if callback is not None:
        callback(payload)


def log_exception_once(error: BaseException, message: str) -> bool:
    """Log one complete exception chain even when several layers observe it."""

    if getattr(error, _EXCEPTION_LOGGED_ATTRIBUTE, False):
        return False
    try:
        setattr(error, _EXCEPTION_LOGGED_ATTRIBUTE, True)
    except (AttributeError, TypeError):
        # Exceptions without a writable instance dictionary are uncommon. It is
        # safer to retain diagnostics than to suppress a potentially first log.
        pass
    logger.opt(
        exception=(type(error), error, error.__traceback__),
    ).error(message)
    return True


@contextmanager
def bind_log_context(**context: Any) -> Iterator[None]:
    clean_context = {key: value for key, value in context.items() if value is not None}
    with logger.contextualize(**clean_context):
        yield
