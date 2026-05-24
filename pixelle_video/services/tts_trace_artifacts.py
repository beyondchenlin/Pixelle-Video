from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pixelle_video.workflow_content_contracts import (
    build_workflow_file_trace,
    extract_workflow_file_trace,
)

TTS_TRACE_ARTIFACT_DIR_NAME = "prompt_traces"
TTS_TRACE_ARTIFACT_FILE_NAME = "tts_workflow.md"
TTS_TRACE_RESULT_FILE_NAME = "tts_workflow_result.md"
TTS_SERVICE_RESULT_FILE_NAME = "tts_service_result.md"
TTS_TRACE_SCHEMA = "pixelle.tts_workflow_trace.v1"


def write_tts_workflow_trace_context(
    output_dir: Path,
    *,
    task_id: str | None,
    text: str,
    workflow: str,
    workflow_input: str,
    source: str,
    workflow_params: Mapping[str, Any],
) -> dict[str, Any]:
    resolved_text = str(text)
    if not resolved_text.strip():
        raise ValueError("TTS workflow trace text is required")
    trace_id = uuid.uuid4().hex
    resolved_task_id = str(task_id or f"tts-{trace_id}").strip()
    artifact_dir = output_dir / TTS_TRACE_ARTIFACT_DIR_NAME / "tts" / trace_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / TTS_TRACE_ARTIFACT_FILE_NAME
    normalized_params = normalize_tts_workflow_params(workflow_params)
    params_sha256 = tts_workflow_params_sha256(normalized_params)
    text_sha256 = hashlib.sha256(resolved_text.encode("utf-8")).hexdigest()
    workflow_file_trace = build_workflow_file_trace(workflow, workflow_input)
    request_context = {
        "schema": TTS_TRACE_SCHEMA,
        "trace_id": trace_id,
        "task_id": resolved_task_id,
        "source": str(source),
        "workflow": str(workflow),
        "workflow_input": str(workflow_input),
        "text_sha256": text_sha256,
        "workflow_params": normalized_params,
        "workflow_params_sha256": params_sha256,
        **workflow_file_trace,
    }
    artifact_path.write_text(
        "\n".join(
            [
                "# TTS Workflow Trace",
                "",
                f"Artifact schema: {TTS_TRACE_SCHEMA}",
                f"Trace ID: {trace_id}",
                f"Task ID: {resolved_task_id}",
                "",
                "## Request Context",
                "",
                "```json",
                json.dumps(request_context, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
                "## Text",
                "",
                *format_markdown_fence("text", resolved_text),
                "",
            ]
        ),
        encoding="utf-8",
    )
    artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    return {
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "trace_id": trace_id,
        "task_id": resolved_task_id,
        "text": resolved_text,
        "text_sha256": text_sha256,
        "workflow": str(workflow),
        "workflow_input": str(workflow_input),
        "workflow_params": normalized_params,
        "workflow_params_sha256": params_sha256,
        **workflow_file_trace,
    }


def validate_tts_workflow_trace_artifact(
    context: Mapping[str, Any] | None,
    *,
    text: str,
    workflow: str,
    workflow_input: str,
    workflow_params: Mapping[str, Any],
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise ValueError("tts_workflow_trace_context is required before TTS workflow execution")
    artifact_path = Path(str(context.get("artifact_path") or ""))
    if (
        artifact_path.name != TTS_TRACE_ARTIFACT_FILE_NAME
        or artifact_path.parent.parent.name != "tts"
        or artifact_path.parent.parent.parent.name != TTS_TRACE_ARTIFACT_DIR_NAME
    ):
        raise ValueError(
            "tts_workflow_trace_context artifact_path must point to "
            f"{TTS_TRACE_ARTIFACT_DIR_NAME}/tts/<trace_id>/{TTS_TRACE_ARTIFACT_FILE_NAME}"
        )
    if not artifact_path.is_file():
        raise ValueError("tts_workflow_trace_context artifact_path does not exist")
    artifact_bytes = artifact_path.read_bytes()
    expected_sha256 = str(context.get("artifact_sha256") or "").strip()
    if hashlib.sha256(artifact_bytes).hexdigest() != expected_sha256:
        raise ValueError("tts_workflow_trace_context artifact_sha256 does not match")
    artifact_text = artifact_bytes.decode("utf-8")
    request_context = _extract_request_context(artifact_text)
    artifact_tts_text = _extract_text_block(artifact_text)
    expected_text = str(text)
    if not expected_text.strip():
        raise ValueError("tts_workflow_trace_context text is required before TTS workflow execution")
    if artifact_tts_text != expected_text:
        raise ValueError("tts_workflow_trace_context artifact text does not match")
    if str(context.get("text") or "") != expected_text:
        raise ValueError("tts_workflow_trace_context text does not match")
    text_sha256 = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
    if str(context.get("text_sha256") or "") != text_sha256:
        raise ValueError("tts_workflow_trace_context text_sha256 does not match")
    if str(request_context.get("text_sha256") or "") != text_sha256:
        raise ValueError("tts_workflow_trace_context artifact text_sha256 does not match")
    if str(context.get("workflow") or "") != str(workflow):
        raise ValueError("tts_workflow_trace_context workflow does not match")
    if str(context.get("workflow_input") or "") != str(workflow_input):
        raise ValueError("tts_workflow_trace_context workflow_input does not match")
    if str(request_context.get("workflow") or "") != str(workflow):
        raise ValueError("tts_workflow_trace_context artifact workflow does not match")
    if str(request_context.get("workflow_input") or "") != str(workflow_input):
        raise ValueError("tts_workflow_trace_context artifact workflow_input does not match")
    normalized_params = normalize_tts_workflow_params(workflow_params)
    params_sha256 = tts_workflow_params_sha256(normalized_params)
    if _normalize_context_params(context.get("workflow_params")) != normalized_params:
        raise ValueError("tts_workflow_trace_context workflow_params do not match")
    if str(context.get("workflow_params_sha256") or "") != params_sha256:
        raise ValueError("tts_workflow_trace_context workflow_params_sha256 does not match")
    if _normalize_context_params(request_context.get("workflow_params")) != normalized_params:
        raise ValueError("tts_workflow_trace_context artifact workflow_params do not match")
    if str(request_context.get("workflow_params_sha256") or "") != params_sha256:
        raise ValueError(
            "tts_workflow_trace_context artifact workflow_params_sha256 does not match"
        )
    _validate_workflow_file_trace_context(
        context=context,
        request_context=request_context,
        context_name="tts_workflow_trace_context",
        expected_trace=workflow_file_trace,
    )
    return dict(context)


def write_tts_workflow_result_artifact(
    context: Mapping[str, Any],
    *,
    status: str,
    result: Mapping[str, Any],
) -> Path:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    result_path = _next_tts_trace_result_path(artifact_path, TTS_TRACE_RESULT_FILE_NAME)
    payload = {
        "schema": "pixelle.tts_workflow_result.v1",
        "trace_id": str(context.get("trace_id") or ""),
        "task_id": str(context.get("task_id") or ""),
        "request_artifact_path": str(artifact_path),
        "request_artifact_sha256": str(context.get("artifact_sha256") or ""),
        "status": str(status),
        "result": dict(result),
    }
    result_path.write_text(
        "\n".join(
            [
                "# TTS Workflow Result",
                "",
                "Artifact schema: pixelle.tts_workflow_result.v1",
                f"Trace ID: {payload['trace_id']}",
                f"Task ID: {payload['task_id']}",
                "",
                "## Result",
                "",
                "```json",
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return result_path


def write_tts_service_result_artifact(
    context: Mapping[str, Any],
    *,
    status: str,
    result: Mapping[str, Any],
) -> Path:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    result_path = _next_tts_trace_result_path(artifact_path, TTS_SERVICE_RESULT_FILE_NAME)
    payload = {
        "schema": "pixelle.tts_service_result.v1",
        "trace_id": str(context.get("trace_id") or ""),
        "task_id": str(context.get("task_id") or ""),
        "request_artifact_path": str(artifact_path),
        "request_artifact_sha256": str(context.get("artifact_sha256") or ""),
        "status": str(status),
        "result": dict(result),
    }
    result_path.write_text(
        "\n".join(
            [
                "# TTS Service Result",
                "",
                "Artifact schema: pixelle.tts_service_result.v1",
                f"Trace ID: {payload['trace_id']}",
                f"Task ID: {payload['task_id']}",
                "",
                "## Result",
                "",
                "```json",
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return result_path


def _next_tts_trace_result_path(artifact_path: Path, file_name: str) -> Path:
    first_path = artifact_path.with_name(file_name)
    if not first_path.exists():
        return first_path

    stem = first_path.stem
    suffix = first_path.suffix
    index = 2
    while True:
        candidate = first_path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def normalize_tts_workflow_params(workflow_params: Mapping[str, Any]) -> dict[str, Any]:
    normalized_params: dict[str, Any] = {}
    for key, value in sorted(workflow_params.items(), key=lambda item: str(item[0])):
        normalized_value = _normalize_trace_value(value)
        if normalized_value in (None, "", [], {}):
            continue
        normalized_params[str(key)] = normalized_value
    return normalized_params


def tts_workflow_params_sha256(workflow_params: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        normalize_tts_workflow_params(workflow_params),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_workflow_file_trace_context(
    *,
    context: Mapping[str, Any],
    request_context: Mapping[str, Any],
    context_name: str,
    expected_trace: Mapping[str, Any] | None = None,
) -> None:
    expected = extract_workflow_file_trace(expected_trace or {})
    context_trace = extract_workflow_file_trace(context)
    request_trace = extract_workflow_file_trace(request_context)
    if expected:
        if not context_trace:
            raise ValueError(f"{context_name} missing workflow file trace")
        if context_trace != expected:
            raise ValueError(
                f"{context_name} workflow file trace does not match resolved workflow file"
            )
        if not request_trace:
            raise ValueError(f"{context_name} artifact workflow file trace is missing")
        if request_trace != expected:
            raise ValueError(
                f"{context_name} artifact workflow file trace does not match resolved workflow file"
            )
        return
    if not context_trace and not request_trace:
        return
    if not context_trace:
        raise ValueError(f"{context_name} missing workflow file trace")
    if not request_trace:
        raise ValueError(f"{context_name} artifact workflow file trace is missing")
    if context_trace != request_trace:
        raise ValueError(f"{context_name} artifact workflow file trace does not match")


def format_markdown_fence(info: str, content: str) -> list[str]:
    text = str(content)
    longest_backtick_run = max(
        (len(match.group(0)) for match in re.finditer(r"`{3,}", text)),
        default=2,
    )
    fence = "`" * max(3, longest_backtick_run + 1)
    return [f"{fence}{info}", text, fence]


def _extract_request_context(artifact_text: str) -> dict[str, Any]:
    marker = "## Request Context"
    marker_index = artifact_text.find(marker)
    if marker_index < 0:
        raise ValueError("tts_workflow_trace_context artifact request context is missing")
    fenced = _extract_fenced_block(artifact_text[marker_index:], "json")
    try:
        payload = json.loads(fenced)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "tts_workflow_trace_context artifact request context is invalid"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != TTS_TRACE_SCHEMA:
        raise ValueError("tts_workflow_trace_context artifact schema is invalid")
    return payload


def _extract_text_block(artifact_text: str) -> str:
    marker = "## Text"
    marker_index = artifact_text.find(marker)
    if marker_index < 0:
        raise ValueError("tts_workflow_trace_context artifact text is missing")
    return _extract_fenced_block(artifact_text[marker_index:], "text")


def _extract_fenced_block(text: str, info: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"(`{3,})([A-Za-z0-9_-]+)", line.strip())
        if match is None or match.group(2) != info:
            continue
        fence = match.group(1)
        content_start = index + 1
        for content_end in range(content_start, len(lines)):
            if lines[content_end].strip() == fence:
                return "\n".join(lines[content_start:content_end])
        break
    raise ValueError("tts_workflow_trace_context artifact fenced block is invalid")


def _normalize_context_params(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return normalize_tts_workflow_params(value)


def _normalize_trace_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_trace_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_trace_value(item) for item in value]
    return value
