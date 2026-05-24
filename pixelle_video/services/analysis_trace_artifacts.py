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

ANALYSIS_TRACE_ARTIFACT_DIR_NAME = "prompt_traces"
ANALYSIS_TRACE_ARTIFACT_FILE_NAME = "analysis_workflow.md"
ANALYSIS_TRACE_RESULT_FILE_NAME = "analysis_workflow_result.md"
ANALYSIS_SERVICE_RESULT_FILE_NAME = "analysis_service_result.md"
ANALYSIS_TRACE_SCHEMA = "pixelle.analysis_workflow_trace.v1"
ANALYSIS_TRACE_RESULT_SCHEMA = "pixelle.analysis_workflow_result.v1"
ANALYSIS_SERVICE_RESULT_SCHEMA = "pixelle.analysis_service_result.v1"


def write_analysis_workflow_trace_context(
    output_dir: Path,
    *,
    task_id: str | None,
    media_path: str,
    media_type: str,
    workflow: str,
    workflow_input: str,
    source: str,
    service_domain: str,
    workflow_params: Mapping[str, Any],
) -> dict[str, Any]:
    resolved_media_path = str(media_path)
    if not resolved_media_path.strip():
        raise ValueError("analysis workflow trace media_path is required")
    trace_id = uuid.uuid4().hex
    resolved_task_id = str(task_id or f"analysis-{trace_id}").strip()
    artifact_dir = output_dir / ANALYSIS_TRACE_ARTIFACT_DIR_NAME / "analysis" / trace_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / ANALYSIS_TRACE_ARTIFACT_FILE_NAME
    normalized_params = normalize_analysis_workflow_params(workflow_params)
    params_sha256 = analysis_workflow_params_sha256(normalized_params)
    media_path_sha256 = hashlib.sha256(resolved_media_path.encode("utf-8")).hexdigest()
    media_file_sha256 = _media_file_sha256(resolved_media_path)
    workflow_file_trace = build_workflow_file_trace(workflow, workflow_input)
    request_context = {
        "schema": ANALYSIS_TRACE_SCHEMA,
        "trace_id": trace_id,
        "task_id": resolved_task_id,
        "source": str(source),
        "service_domain": str(service_domain),
        "workflow": str(workflow),
        "workflow_input": str(workflow_input),
        "media_type": str(media_type),
        "media_path": resolved_media_path,
        "media_path_sha256": media_path_sha256,
        "media_file_sha256": media_file_sha256,
        "workflow_params": normalized_params,
        "workflow_params_sha256": params_sha256,
        **workflow_file_trace,
    }
    artifact_path.write_text(
        "\n".join(
            [
                "# Analysis Workflow Trace",
                "",
                f"Artifact schema: {ANALYSIS_TRACE_SCHEMA}",
                f"Trace ID: {trace_id}",
                f"Task ID: {resolved_task_id}",
                "",
                "## Request Context",
                "",
                "```json",
                json.dumps(request_context, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
                "## Media Path",
                "",
                *_format_markdown_fence("text", resolved_media_path),
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
        "source": str(source),
        "service_domain": str(service_domain),
        "workflow": str(workflow),
        "workflow_input": str(workflow_input),
        "media_type": str(media_type),
        "media_path": resolved_media_path,
        "media_path_sha256": media_path_sha256,
        "media_file_sha256": media_file_sha256,
        "workflow_params": normalized_params,
        "workflow_params_sha256": params_sha256,
        **workflow_file_trace,
    }


def validate_analysis_workflow_trace_artifact(
    context: Mapping[str, Any] | None,
    *,
    media_path: str,
    media_type: str,
    workflow: str,
    workflow_input: str,
    service_domain: str,
    workflow_params: Mapping[str, Any],
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise ValueError(
            "analysis_workflow_trace_context is required before analysis workflow execution"
        )
    artifact_path = Path(str(context.get("artifact_path") or ""))
    if (
        artifact_path.name != ANALYSIS_TRACE_ARTIFACT_FILE_NAME
        or artifact_path.parent.parent.name != "analysis"
        or artifact_path.parent.parent.parent.name != ANALYSIS_TRACE_ARTIFACT_DIR_NAME
    ):
        raise ValueError(
            "analysis_workflow_trace_context artifact_path must point to "
            f"{ANALYSIS_TRACE_ARTIFACT_DIR_NAME}/analysis/<trace_id>/"
            f"{ANALYSIS_TRACE_ARTIFACT_FILE_NAME}"
        )
    if not artifact_path.is_file():
        raise ValueError("analysis_workflow_trace_context artifact_path does not exist")
    artifact_bytes = artifact_path.read_bytes()
    expected_sha256 = str(context.get("artifact_sha256") or "").strip()
    if hashlib.sha256(artifact_bytes).hexdigest() != expected_sha256:
        raise ValueError("analysis_workflow_trace_context artifact_sha256 does not match")
    artifact_text = artifact_bytes.decode("utf-8")
    request_context = _extract_request_context(artifact_text)
    artifact_media_path = _extract_media_path_block(artifact_text)
    expected_media_path = str(media_path)
    if artifact_media_path != expected_media_path:
        raise ValueError("analysis_workflow_trace_context artifact media_path does not match")
    for field_name, expected in (
        ("media_path", expected_media_path),
        ("media_type", str(media_type)),
        ("workflow", str(workflow)),
        ("workflow_input", str(workflow_input)),
        ("service_domain", str(service_domain)),
    ):
        if str(context.get(field_name) or "") != expected:
            raise ValueError(f"analysis_workflow_trace_context {field_name} does not match")
        if str(request_context.get(field_name) or "") != expected:
            raise ValueError(
                f"analysis_workflow_trace_context artifact {field_name} does not match"
            )

    media_path_sha256 = hashlib.sha256(expected_media_path.encode("utf-8")).hexdigest()
    if str(context.get("media_path_sha256") or "") != media_path_sha256:
        raise ValueError("analysis_workflow_trace_context media_path_sha256 does not match")
    if str(request_context.get("media_path_sha256") or "") != media_path_sha256:
        raise ValueError(
            "analysis_workflow_trace_context artifact media_path_sha256 does not match"
        )
    expected_file_sha256 = _media_file_sha256(expected_media_path)
    if expected_file_sha256 is not None:
        if str(context.get("media_file_sha256") or "") != expected_file_sha256:
            raise ValueError(
                "analysis_workflow_trace_context media_file_sha256 does not match"
            )
        if str(request_context.get("media_file_sha256") or "") != expected_file_sha256:
            raise ValueError(
                "analysis_workflow_trace_context artifact media_file_sha256 does not match"
            )

    normalized_params = normalize_analysis_workflow_params(workflow_params)
    params_sha256 = analysis_workflow_params_sha256(normalized_params)
    if _normalize_context_params(context.get("workflow_params")) != normalized_params:
        raise ValueError("analysis_workflow_trace_context workflow_params do not match")
    if str(context.get("workflow_params_sha256") or "") != params_sha256:
        raise ValueError(
            "analysis_workflow_trace_context workflow_params_sha256 does not match"
        )
    if _normalize_context_params(request_context.get("workflow_params")) != normalized_params:
        raise ValueError(
            "analysis_workflow_trace_context artifact workflow_params do not match"
        )
    if str(request_context.get("workflow_params_sha256") or "") != params_sha256:
        raise ValueError(
            "analysis_workflow_trace_context artifact workflow_params_sha256 does not match"
        )
    _validate_workflow_file_trace_context(
        context=context,
        request_context=request_context,
        context_name="analysis_workflow_trace_context",
        expected_trace=workflow_file_trace,
    )
    return dict(context)


def write_analysis_workflow_result_artifact(
    context: Mapping[str, Any],
    *,
    status: str,
    result: Mapping[str, Any],
) -> Path:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    result_path = _next_analysis_trace_result_path(
        artifact_path,
        ANALYSIS_TRACE_RESULT_FILE_NAME,
    )
    payload = {
        "schema": ANALYSIS_TRACE_RESULT_SCHEMA,
        "trace_id": str(context.get("trace_id") or ""),
        "task_id": str(context.get("task_id") or ""),
        "request_artifact_path": str(artifact_path),
        "request_artifact_sha256": str(context.get("artifact_sha256") or ""),
        "status": str(status),
        "result": _normalize_trace_value(dict(result)),
    }
    result_path.write_text(
        "\n".join(
            [
                "# Analysis Workflow Result",
                "",
                f"Artifact schema: {ANALYSIS_TRACE_RESULT_SCHEMA}",
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


def write_analysis_service_result_artifact(
    context: Mapping[str, Any],
    *,
    status: str,
    returned_description: str,
    extraction_source: Mapping[str, Any],
) -> Path:
    description = str(returned_description)
    artifact_path = Path(str(context.get("artifact_path") or ""))
    result_path = _next_analysis_trace_result_path(
        artifact_path,
        ANALYSIS_SERVICE_RESULT_FILE_NAME,
    )
    payload = {
        "schema": ANALYSIS_SERVICE_RESULT_SCHEMA,
        "trace_id": str(context.get("trace_id") or ""),
        "task_id": str(context.get("task_id") or ""),
        "request_artifact_path": str(artifact_path),
        "request_artifact_sha256": str(context.get("artifact_sha256") or ""),
        "status": str(status),
        "returned_description_sha256": hashlib.sha256(
            description.encode("utf-8")
        ).hexdigest(),
        "extraction_source": _normalize_trace_value(dict(extraction_source)),
    }
    result_path.write_text(
        "\n".join(
            [
                "# Analysis Service Result",
                "",
                f"Artifact schema: {ANALYSIS_SERVICE_RESULT_SCHEMA}",
                f"Trace ID: {payload['trace_id']}",
                f"Task ID: {payload['task_id']}",
                "",
                "## Result Context",
                "",
                "```json",
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
                "## Returned Description",
                "",
                *_format_markdown_fence("text", description),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return result_path


def summarize_analysis_service_workflow_result(result: Any) -> dict[str, Any]:
    outputs = getattr(result, "outputs", {}) or {}
    if isinstance(outputs, Mapping):
        normalized_outputs = _normalize_trace_value(outputs)
    else:
        normalized_outputs = {}
    return {
        "status": str(getattr(result, "status", "")),
        "msg": str(getattr(result, "msg", "") or ""),
        "texts": [str(value) for value in getattr(result, "texts", []) or []],
        "files": [str(value) for value in getattr(result, "files", []) or []],
        "outputs": normalized_outputs,
    }


def normalize_analysis_workflow_params(workflow_params: Mapping[str, Any]) -> dict[str, Any]:
    normalized_params: dict[str, Any] = {}
    for key, value in sorted(workflow_params.items(), key=lambda item: str(item[0])):
        normalized_value = _normalize_trace_value(value)
        if normalized_value in (None, "", [], {}):
            continue
        normalized_params[str(key)] = normalized_value
    return normalized_params


def analysis_workflow_params_sha256(workflow_params: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        normalize_analysis_workflow_params(workflow_params),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _media_file_sha256(media_path: str) -> str | None:
    try:
        path = Path(media_path)
    except (TypeError, ValueError):
        return None
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _next_analysis_trace_result_path(artifact_path: Path, file_name: str) -> Path:
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


def _extract_request_context(artifact_text: str) -> dict[str, Any]:
    marker = "## Request Context"
    marker_index = artifact_text.find(marker)
    if marker_index < 0:
        raise ValueError("analysis_workflow_trace_context artifact request context is missing")
    fenced = _extract_fenced_block(artifact_text[marker_index:], "json")
    try:
        payload = json.loads(fenced)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "analysis_workflow_trace_context artifact request context is invalid"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != ANALYSIS_TRACE_SCHEMA:
        raise ValueError("analysis_workflow_trace_context artifact schema is invalid")
    return payload


def _extract_media_path_block(artifact_text: str) -> str:
    marker = "## Media Path"
    marker_index = artifact_text.find(marker)
    if marker_index < 0:
        raise ValueError("analysis_workflow_trace_context artifact media path is missing")
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
    raise ValueError("analysis_workflow_trace_context artifact fenced block is invalid")


def _format_markdown_fence(info: str, content: str) -> list[str]:
    text = str(content)
    longest_backtick_run = max(
        (len(match.group(0)) for match in re.finditer(r"`{3,}", text)),
        default=2,
    )
    fence = "`" * max(3, longest_backtick_run + 1)
    return [f"{fence}{info}", text, fence]


def _normalize_context_params(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return normalize_analysis_workflow_params(value)


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
