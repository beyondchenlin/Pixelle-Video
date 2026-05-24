from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pixelle_video.workflow_content_contracts import (
    build_workflow_file_trace,
    extract_workflow_file_trace,
)

FINAL_PROMPT_ARTIFACT_SCHEMA = "pixelle.final_visual_prompts.v1"
FINAL_PROMPT_ARTIFACT_DIR_NAME = "prompt_traces"
FINAL_PROMPT_ARTIFACT_FILE_NAME = "final_visual_prompts.md"
MEDIA_TRACE_RESULT_SCHEMA = "pixelle.media_workflow_result.v1"
MEDIA_TRACE_RESULT_FILE_NAME = "media_workflow_result.md"
MEDIA_TRACE_CALL_DIR_NAME = "c"
MEDIA_TRACE_MEDIA_RESULT_SCHEMA = "pixelle.media_result.v1"
MEDIA_TRACE_MEDIA_RESULT_FILE_NAME = "media_result.md"
_TRACEABLE_WORKFLOW_PARAM_KEYS = frozenset(
    {
        "audio",
        "batch_size",
        "cfg",
        "clip_skip",
        "denoise",
        "duration",
        "fps",
        "frame_count",
        "frame_rate",
        "frames",
        "guidance",
        "guidance_scale",
        "image",
        "media",
        "motion_bucket_id",
        "noise_aug_strength",
        "num_frames",
        "ref_audio",
        "reference_audio",
        "reference_image",
        "sampler",
        "scheduler",
        "second",
        "seconds",
        "seed",
        "source_image",
        "steps",
        "strength",
        "target_image",
        "video",
    }
)
_TRACEABLE_WORKFLOW_PARAM_SUFFIXES = (
    "audio",
    "file",
    "image",
    "media",
    "path",
    "url",
    "video",
)
_NON_TRACEABLE_WORKFLOW_PARAM_KEYS = frozenset(
    {
        "height",
        "image_prompt",
        "negative",
        "negative_image_prompt",
        "negative_prompt",
        "negative_video_prompt",
        "prompt",
        "width",
    }
)
_WORKFLOW_PROMPT_ALIAS_PARAM_KEYS = frozenset(
    {
        "image_prompt",
        "positive_prompt",
        "text_prompt",
        "video_prompt",
    }
)
_WORKFLOW_NEGATIVE_PROMPT_ALIAS_PARAM_KEYS = frozenset(
    {
        "negative",
        "negative_image_prompt",
        "negative_prompt",
        "negative_video_prompt",
    }
)


def write_final_prompt_artifact(
    output_dir: Path,
    task_id: str,
    frames: Sequence[Mapping[str, Any]],
    generation_context: Mapping[str, Any] | None = None,
) -> Path:
    artifact_dir = Path(output_dir) / FINAL_PROMPT_ARTIFACT_DIR_NAME
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = _next_final_prompt_artifact_path(
        artifact_dir,
        task_id=task_id,
        frames=frames,
        generation_context=generation_context,
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Final Visual Prompts",
        "",
        f"Artifact schema: {FINAL_PROMPT_ARTIFACT_SCHEMA}",
        f"Task ID: {task_id}",
        f"Frame count: {len(frames)}",
        "",
    ]
    if generation_context:
        lines.extend(
            [
                "## Generation Context",
                "",
                "```json",
                json.dumps(generation_context, ensure_ascii=False, indent=2, default=str),
                "```",
                "",
            ]
        )
    for index, frame in enumerate(frames, start=1):
        frame_number = frame.get("index") if frame.get("index") is not None else index
        frame_id = str(frame.get("frame_id") or frame_number)
        positive_prompt = str(
            frame.get("prompt")
            if frame.get("prompt") is not None
            else frame.get("positive_prompt")
            if frame.get("positive_prompt") is not None
            else frame.get("image_prompt")
            if frame.get("image_prompt") is not None
            else ""
        )
        negative_prompt = str(frame.get("negative_prompt") or "")
        lines.extend(
            [
                f"## Frame {index}",
                "",
                f"Frame ID: {frame_id}",
                "",
                "Positive prompt:",
                "",
                *_format_markdown_fence("text", positive_prompt),
                "",
                "Negative prompt:",
                "",
                *_format_markdown_fence("text", negative_prompt),
                "",
            ]
        )

    artifact_path.write_text("\n".join(lines), encoding="utf-8")
    return artifact_path


def write_single_media_prompt_artifact(
    output_dir: Path,
    *,
    task_id: str,
    prompt: str,
    negative_prompt: str = "",
    generation_context: Mapping[str, Any] | None = None,
    frame_id: str | None = None,
) -> Path:
    return write_final_prompt_artifact(
        output_dir,
        task_id=task_id,
        frames=[
            {
                "index": 1,
                "frame_id": frame_id or "1",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
            }
        ],
        generation_context=generation_context,
    )


def write_single_media_prompt_trace_context(
    output_dir: Path,
    *,
    task_id: str,
    prompt: str,
    workflow: str,
    media_type: str,
    source: str,
    workflow_input: str | None = None,
    negative_prompt: str = "",
    frame_id: str | None = "1",
    media_width: int | None = None,
    media_height: int | None = None,
    generation_context: Mapping[str, Any] | None = None,
    workflow_params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_workflow_input = str(workflow_input or workflow)
    workflow_context = {
        "requested_workflow": workflow,
        "workflow": workflow,
        "workflow_input": resolved_workflow_input,
    }
    generation_context_mapping = dict(generation_context or {})
    workflow_file_trace = build_workflow_file_trace(
        workflow,
        resolved_workflow_input,
        generation_context_mapping.get("workflow_file"),
        generation_context_mapping.get("media_workflow"),
    )
    workflow_param_trace = build_workflow_params_trace(
        workflow_params,
        prompt=prompt,
    )
    artifact_path = write_single_media_prompt_artifact(
        output_dir,
        task_id=task_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        frame_id=frame_id,
        generation_context={
            "source": source,
            **generation_context_mapping,
            **workflow_context,
            **workflow_file_trace,
            **workflow_param_trace,
            "media_type": media_type,
            **(
                {"media_width": media_width}
                if media_width is not None
                else {}
            ),
            **(
                {"media_height": media_height}
                if media_height is not None
                else {}
            ),
        },
    )
    return build_media_prompt_trace_context(
        artifact_path=artifact_path,
        task_id=task_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        workflow_context=workflow_context,
        media_type=media_type,
        frame_id=frame_id,
        media_width=media_width,
        media_height=media_height,
        workflow_param_trace=workflow_param_trace,
        workflow_file_trace=workflow_file_trace,
    )


def media_workflow_trace_context(
    media_service: Any,
    *,
    workflow: str | None,
    media_type: str,
) -> dict[str, Any]:
    requested_workflow = workflow.strip() if isinstance(workflow, str) else workflow
    context: dict[str, Any] = {"requested_workflow": requested_workflow}
    trace_resolver = getattr(media_service, "resolve_workflow_trace_context", None)
    if callable(trace_resolver):
        resolved = trace_resolver(
            workflow=requested_workflow,
            media_type=media_type,
        )
        return {
            "requested_workflow": requested_workflow,
            **dict(resolved),
        }

    resolver = getattr(media_service, "resolve_workflow_key", None)
    if not callable(resolver):
        raise ValueError(
            "media_service.resolve_workflow_trace_context or "
            "resolve_workflow_key is required before writing media prompt traces"
        )

    resolved_workflow = resolver(
        workflow=requested_workflow,
        media_type=media_type,
    )
    context["workflow"] = resolved_workflow
    context["workflow_input"] = resolved_workflow
    return context


def build_media_prompt_trace_context(
    *,
    artifact_path: str | Path,
    task_id: str,
    prompt: str,
    workflow_context: Mapping[str, Any],
    media_type: str,
    frame_id: str | None = None,
    negative_prompt: str = "",
    media_width: int | None = None,
    media_height: int | None = None,
    workflow_param_trace: Mapping[str, Any] | None = None,
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_artifact_path = Path(artifact_path)
    return {
        "artifact_path": str(resolved_artifact_path),
        "artifact_sha256": _artifact_sha256(resolved_artifact_path),
        "task_id": str(task_id),
        "frame_id": frame_id,
        "prompt": str(prompt),
        "negative_prompt": str(negative_prompt or ""),
        "requested_workflow": workflow_context.get("requested_workflow"),
        "workflow": workflow_context.get("workflow"),
        "workflow_input": workflow_context.get(
            "workflow_input",
            workflow_context.get("workflow"),
        ),
        "media_type": media_type,
        "media_width": media_width,
        "media_height": media_height,
        **extract_workflow_file_trace(workflow_context),
        **dict(workflow_file_trace or {}),
        **dict(workflow_param_trace or {}),
    }


def write_media_workflow_result_artifact(
    context: Mapping[str, Any],
    *,
    status: str,
    result: Mapping[str, Any],
) -> Path:
    return _write_media_trace_result_artifact(
        context,
        schema=MEDIA_TRACE_RESULT_SCHEMA,
        file_name=MEDIA_TRACE_RESULT_FILE_NAME,
        title="Media Workflow Result",
        status=status,
        result=result,
    )


def write_media_result_artifact(
    context: Mapping[str, Any],
    *,
    status: str,
    result: Mapping[str, Any],
) -> Path:
    return _write_media_trace_result_artifact(
        context,
        schema=MEDIA_TRACE_MEDIA_RESULT_SCHEMA,
        file_name=MEDIA_TRACE_MEDIA_RESULT_FILE_NAME,
        title="Media Result",
        status=status,
        result=result,
    )


def _write_media_trace_result_artifact(
    context: Mapping[str, Any],
    *,
    schema: str,
    file_name: str,
    title: str,
    status: str,
    result: Mapping[str, Any],
) -> Path:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    result_path = _next_media_trace_result_path(artifact_path, file_name)
    payload = {
        "schema": schema,
        "task_id": str(context.get("task_id") or ""),
        "frame_id": str(context.get("frame_id") or ""),
        "request_artifact_path": str(artifact_path),
        "request_artifact_sha256": str(context.get("artifact_sha256") or ""),
        "status": str(status),
        "result": _normalize_trace_result(dict(result)),
    }
    result_path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                f"Artifact schema: {schema}",
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


def _next_media_trace_result_path(artifact_path: Path, file_name: str) -> Path:
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


def media_workflow_result_artifact_exists(context: Mapping[str, Any]) -> bool:
    artifact_path = Path(str(context.get("artifact_path") or ""))
    return artifact_path.with_name(MEDIA_TRACE_RESULT_FILE_NAME).is_file()


def summarize_media_workflow_result(result: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if isinstance(result, Mapping):
        source = result
    else:
        source = {
            key: getattr(result, key)
            for key in (
                "status",
                "msg",
                "images",
                "videos",
                "files",
                "audios",
                "texts",
                "outputs",
                "duration",
            )
            if hasattr(result, key)
        }
    for key, value in source.items():
        if value in (None, "", [], {}):
            continue
        summary[str(key)] = value
    return summary


def build_workflow_params_trace(
    workflow_params: Mapping[str, Any] | None,
    *,
    prompt: str | None = None,
) -> dict[str, Any]:
    _validate_workflow_prompt_aliases(workflow_params, prompt=prompt)
    _validate_workflow_negative_prompt_aliases(workflow_params)
    workflow_param_inputs = _traceable_workflow_param_inputs(workflow_params)
    if not workflow_param_inputs:
        return {}
    return {
        "workflow_param_inputs": workflow_param_inputs,
        "workflow_param_inputs_sha256": _workflow_param_inputs_sha256(
            workflow_param_inputs
        ),
    }


def require_media_prompt_trace_context(
    context: Mapping[str, Any] | None,
    *,
    prompt: str,
    media_type: str,
    width: int | None = None,
    height: int | None = None,
    negative_prompt: str | None = None,
) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise ValueError("media_prompt_trace_context is required before media generation")
    normalized = {str(key): value for key, value in context.items()}
    required_fields = (
        "artifact_path",
        "artifact_sha256",
        "task_id",
        "prompt",
        "media_type",
    )
    missing = [
        field
        for field in required_fields
        if not str(normalized.get(field) or "").strip()
    ]
    if missing:
        raise ValueError(
            "media_prompt_trace_context missing required fields: "
            + ", ".join(missing)
        )
    if str(normalized["prompt"]).strip() != str(prompt).strip():
        raise ValueError("media_prompt_trace_context prompt does not match media prompt")
    if str(normalized["media_type"]).strip() != str(media_type).strip():
        raise ValueError("media_prompt_trace_context media type does not match media call")
    if width is not None:
        _validate_media_prompt_trace_dimension(
            normalized,
            field_name="media_width",
            expected=width,
        )
    if height is not None:
        _validate_media_prompt_trace_dimension(
            normalized,
            field_name="media_height",
            expected=height,
        )
    if negative_prompt is not None:
        context_negative_prompt = str(normalized.get("negative_prompt") or "").strip()
        if context_negative_prompt != str(negative_prompt).strip():
            raise ValueError(
                "media_prompt_trace_context negative prompt does not match media call"
            )
    return normalized


def validate_media_prompt_trace_artifact(
    context: Mapping[str, Any],
    *,
    prompt: str,
    resolved_workflow: str,
    resolved_workflow_input: str | None = None,
    media_type: str,
    width: int | None = None,
    height: int | None = None,
    negative_prompt: str | None = None,
    workflow_param_trace: Mapping[str, Any] | None = None,
    workflow_file_trace: Mapping[str, Any] | None = None,
) -> None:
    expected_workflow = str(resolved_workflow).strip()
    expected_workflow_input = str(
        resolved_workflow_input or resolved_workflow
    ).strip()
    expected_frame_id = str(context.get("frame_id") or "").strip()
    context_workflow = str(context.get("workflow") or "").strip()
    if not context_workflow:
        raise ValueError("media_prompt_trace_context missing resolved workflow")
    if context_workflow != expected_workflow:
        raise ValueError(
            "media_prompt_trace_context workflow does not match resolved media workflow"
        )
    context_workflow_input = str(context.get("workflow_input") or "").strip()
    if not context_workflow_input:
        raise ValueError("media_prompt_trace_context missing workflow_input")
    if context_workflow_input != expected_workflow_input:
        raise ValueError(
            "media_prompt_trace_context workflow_input does not match resolved media workflow"
        )

    artifact_path = Path(str(context.get("artifact_path") or ""))
    if (
        artifact_path.name != FINAL_PROMPT_ARTIFACT_FILE_NAME
        or not _is_under_prompt_trace_dir(artifact_path)
    ):
        raise ValueError(
            "media_prompt_trace_context artifact_path must point to "
            f"{FINAL_PROMPT_ARTIFACT_DIR_NAME}/{FINAL_PROMPT_ARTIFACT_FILE_NAME}"
        )
    if not artifact_path.is_file():
        raise ValueError("media_prompt_trace_context artifact_path does not exist")
    try:
        artifact_bytes = artifact_path.read_bytes()
        artifact_text = artifact_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(
            "media_prompt_trace_context artifact_path could not be read"
        ) from exc

    expected_sha256 = str(context.get("artifact_sha256") or "").strip()
    actual_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "media_prompt_trace_context artifact_sha256 does not match artifact_path"
        )

    document = _parse_final_prompt_artifact(artifact_text)
    task_id = str(context.get("task_id") or "").strip()
    if document["task_id"] != task_id:
        raise ValueError("media_prompt_trace_context artifact task_id does not match")
    if not _generation_context_field_matches(
        document["generation_context"],
        allowed_keys={"workflow", "media_workflow"},
        expected=expected_workflow,
    ):
        raise ValueError("media_prompt_trace_context artifact workflow does not match")
    if not _generation_context_field_matches(
        document["generation_context"],
        allowed_keys={"workflow_input", "media_workflow_input"},
        expected=expected_workflow_input,
    ):
        raise ValueError("media_prompt_trace_context artifact workflow_input does not match")
    if not _generation_context_field_matches(
        document["generation_context"],
        allowed_keys={"media_type"},
        expected=media_type,
    ):
        raise ValueError("media_prompt_trace_context artifact media_type does not match")
    if width is not None and not _generation_context_field_matches(
        document["generation_context"],
        allowed_keys={"media_width", "width"},
        expected=int(width),
    ):
        raise ValueError("media_prompt_trace_context artifact media_width does not match")
    if height is not None and not _generation_context_field_matches(
        document["generation_context"],
        allowed_keys={"media_height", "height"},
        expected=int(height),
    ):
        raise ValueError("media_prompt_trace_context artifact media_height does not match")
    _validate_workflow_param_trace_chain(
        context=context,
        generation_context=document["generation_context"],
        actual_trace=workflow_param_trace,
    )
    _validate_workflow_file_trace_chain(
        context=context,
        generation_context=document["generation_context"],
        expected_trace=workflow_file_trace,
    )

    expected_prompt = str(prompt).strip()
    expected_negative_prompt = str(negative_prompt or "").strip()
    candidate_frames = document["frames"]
    if expected_frame_id:
        candidate_frames = [
            frame
            for frame in document["frames"]
            if frame["frame_id"] == expected_frame_id
        ]
        if not candidate_frames:
            raise ValueError(
                "media_prompt_trace_context artifact frame_id does not match"
            )
    matching_prompt_frames = [
        frame for frame in candidate_frames if frame["positive_prompt"] == expected_prompt
    ]
    if not matching_prompt_frames:
        raise ValueError("media_prompt_trace_context artifact prompt does not match")
    if not any(
        frame["negative_prompt"] == expected_negative_prompt
        for frame in matching_prompt_frames
    ):
        raise ValueError(
            "media_prompt_trace_context artifact negative prompt does not match"
        )


def _artifact_sha256(artifact_path: Path) -> str | None:
    try:
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _is_under_prompt_trace_dir(artifact_path: Path) -> bool:
    return any(
        parent.name == FINAL_PROMPT_ARTIFACT_DIR_NAME
        for parent in artifact_path.parents
    )


def _next_final_prompt_artifact_path(
    artifact_dir: Path,
    *,
    task_id: str,
    frames: Sequence[Mapping[str, Any]],
    generation_context: Mapping[str, Any] | None,
) -> Path:
    legacy_path = artifact_dir / FINAL_PROMPT_ARTIFACT_FILE_NAME
    if not legacy_path.exists():
        return legacy_path

    trace_id = _prompt_trace_id(
        task_id=task_id,
        frames=frames,
        generation_context=generation_context,
    )
    base_dir = artifact_dir / MEDIA_TRACE_CALL_DIR_NAME
    candidate = base_dir / trace_id / FINAL_PROMPT_ARTIFACT_FILE_NAME
    suffix = 2
    while candidate.exists():
        candidate = base_dir / f"{trace_id}-{suffix}" / FINAL_PROMPT_ARTIFACT_FILE_NAME
        suffix += 1
    return candidate


def _prompt_trace_id(
    *,
    task_id: str,
    frames: Sequence[Mapping[str, Any]],
    generation_context: Mapping[str, Any] | None,
) -> str:
    payload = {
        "task_id": str(task_id),
        "frames": list(frames),
        "generation_context": dict(generation_context or {}),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()
    return digest[:12]


def _validate_media_prompt_trace_dimension(
    context: Mapping[str, Any],
    *,
    field_name: str,
    expected: int,
) -> None:
    raw_value = context.get(field_name)
    if raw_value is None or str(raw_value).strip() == "":
        raise ValueError(f"media_prompt_trace_context missing {field_name}")
    try:
        actual = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"media_prompt_trace_context {field_name} must be an integer"
        ) from exc
    if actual != int(expected):
        raise ValueError(
            f"media_prompt_trace_context {field_name} does not match media call"
        )


def _parse_final_prompt_artifact(artifact_text: str) -> dict[str, Any]:
    lines = artifact_text.splitlines()
    if not lines or lines[0].strip() != "# Final Visual Prompts":
        raise ValueError("media_prompt_trace_context artifact is not a final prompt artifact")
    header = _parse_final_prompt_artifact_header(lines)
    if header["artifact_schema"] != FINAL_PROMPT_ARTIFACT_SCHEMA:
        raise ValueError("media_prompt_trace_context artifact schema is missing")

    task_id = header["task_id"]
    if not task_id:
        raise ValueError("media_prompt_trace_context artifact task_id is missing")

    sections = _top_level_sections(lines)
    _validate_final_prompt_artifact_sections(sections)
    generation_context = _extract_generation_context(sections)
    frames = _extract_frame_prompt_records(sections)
    if not frames:
        raise ValueError("media_prompt_trace_context artifact prompt blocks are missing")
    frame_count = _parse_artifact_frame_count(header["frame_count"])
    if frame_count != len(frames):
        raise ValueError(
            "media_prompt_trace_context artifact frame count does not match frame blocks"
        )

    return {
        "task_id": task_id,
        "frame_count": frame_count,
        "generation_context": generation_context,
        "frames": frames,
        "positive_prompts": [frame["positive_prompt"] for frame in frames],
        "negative_prompts": [frame["negative_prompt"] for frame in frames],
    }


def _parse_final_prompt_artifact_header(lines: Sequence[str]) -> dict[str, str]:
    expected_positions = {
        2: "Artifact schema",
        3: "Task ID",
        4: "Frame count",
    }
    header: dict[str, str] = {}
    for index, label in expected_positions.items():
        if index >= len(lines):
            raise ValueError(
                f"media_prompt_trace_context artifact header missing {label}"
            )
        prefix = f"{label}:"
        line = lines[index]
        if not line.startswith(prefix):
            raise ValueError(
                f"media_prompt_trace_context artifact header missing {label}"
            )
        key = label.lower().replace(" ", "_")
        header[key] = line[len(prefix):].strip()
    return header


def _parse_artifact_frame_count(value: str) -> int:
    try:
        frame_count = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "media_prompt_trace_context artifact frame count must be an integer"
        ) from exc
    if frame_count < 0:
        raise ValueError(
            "media_prompt_trace_context artifact frame count must be an integer"
        )
    return frame_count


def _top_level_sections(lines: Sequence[str]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    active_fence: str | None = None
    current_heading: str | None = None
    section_start = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if active_fence is not None:
            if stripped == active_fence:
                active_fence = None
            continue

        fence_delimiter = _parse_any_fence_start(stripped)
        if fence_delimiter is not None:
            active_fence = fence_delimiter
            continue

        if line.startswith("## "):
            if current_heading is not None:
                sections.append((current_heading, list(lines[section_start:index])))
            current_heading = stripped
            section_start = index + 1

    if active_fence is not None:
        raise ValueError("media_prompt_trace_context artifact fenced block is invalid")
    if current_heading is not None:
        sections.append((current_heading, list(lines[section_start:])))
    return sections


def _validate_final_prompt_artifact_sections(
    sections: Sequence[tuple[str, Sequence[str]]],
) -> None:
    frame_index = 0
    for heading, _section_lines in sections:
        if heading == "## Generation Context":
            continue
        match = re.fullmatch(r"## Frame ([1-9]\d*)", heading)
        if match is None:
            raise ValueError(
                "media_prompt_trace_context artifact unexpected section"
            )
        frame_index += 1
        if int(match.group(1)) != frame_index:
            raise ValueError(
                "media_prompt_trace_context artifact frame heading sequence is invalid"
            )


def _extract_generation_context(
    sections: Sequence[tuple[str, Sequence[str]]],
) -> Mapping[str, Any]:
    generation_context_sections = [
        (index, section_lines)
        for index, (heading, section_lines) in enumerate(sections)
        if heading == "## Generation Context"
    ]
    if len(generation_context_sections) != 1:
        raise ValueError("media_prompt_trace_context artifact generation context is missing")
    generation_context_index, section_lines = generation_context_sections[0]
    first_frame_index = next(
        (
            index
            for index, (heading, _section_lines) in enumerate(sections)
            if heading.startswith("## Frame ")
        ),
        None,
    )
    if first_frame_index is not None and generation_context_index > first_frame_index:
        raise ValueError("media_prompt_trace_context artifact generation context is missing")

    payload_text = _extract_section_fenced_block(
        section_lines,
        fence_info="json",
        error_label="generation context",
    )
    if payload_text is None:
        raise ValueError("media_prompt_trace_context artifact generation context is invalid")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "media_prompt_trace_context artifact generation context is invalid"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ValueError("media_prompt_trace_context artifact generation context is invalid")
    return payload


def _extract_frame_prompt_records(
    sections: Sequence[tuple[str, Sequence[str]]],
) -> list[dict[str, str]]:
    frames: list[dict[str, str]] = []
    for heading, section_lines in sections:
        if not heading.startswith("## Frame "):
            continue
        frame_id = _extract_frame_id(section_lines)
        if frame_id is None:
            raise ValueError("media_prompt_trace_context artifact frame_id is missing")
        if _count_labeled_text_blocks(section_lines, label="Positive prompt:") > 1:
            raise ValueError(
                "media_prompt_trace_context artifact positive prompt block is duplicated"
            )
        if _count_labeled_text_blocks(section_lines, label="Negative prompt:") > 1:
            raise ValueError(
                "media_prompt_trace_context artifact negative prompt block is duplicated"
            )
        positive_prompt = _extract_labeled_text_block(
            section_lines,
            label="Positive prompt:",
            error_label="positive prompt",
        )
        if positive_prompt is None:
            raise ValueError(
                "media_prompt_trace_context artifact positive prompt block is missing"
            )
        negative_prompt = _extract_labeled_text_block(
            section_lines,
            label="Negative prompt:",
            error_label="negative prompt",
        )
        if negative_prompt is None:
            raise ValueError(
                "media_prompt_trace_context artifact negative prompt block is missing"
            )
        frames.append(
            {
                "heading": heading,
                "frame_id": frame_id,
                "positive_prompt": positive_prompt.strip(),
                "negative_prompt": negative_prompt.strip(),
            }
        )
    return frames


def _extract_frame_id(lines: Sequence[str]) -> str | None:
    active_fence: str | None = None
    for line in lines:
        stripped = line.strip()
        if active_fence is not None:
            if stripped == active_fence:
                active_fence = None
            continue
        fence_delimiter = _parse_any_fence_start(stripped)
        if fence_delimiter is not None:
            active_fence = fence_delimiter
            continue
        prefix = "Frame ID:"
        if stripped.startswith(prefix):
            frame_id = stripped[len(prefix):].strip()
            return frame_id or None
    return None


def _count_labeled_text_blocks(lines: Sequence[str], *, label: str) -> int:
    active_fence: str | None = None
    count = 0
    for line in lines:
        stripped = line.strip()
        if active_fence is not None:
            if stripped == active_fence:
                active_fence = None
            continue
        fence_delimiter = _parse_any_fence_start(stripped)
        if fence_delimiter is not None:
            active_fence = fence_delimiter
            continue
        if stripped == label:
            count += 1
    return count


def _extract_labeled_text_block(
    lines: Sequence[str],
    *,
    label: str,
    error_label: str,
) -> str | None:
    active_fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if active_fence is not None:
            if stripped == active_fence:
                active_fence = None
            continue
        fence_delimiter = _parse_any_fence_start(stripped)
        if fence_delimiter is not None:
            active_fence = fence_delimiter
            continue
        if stripped != label:
            continue
        fence_index = index + 1
        while fence_index < len(lines) and not lines[fence_index].strip():
            fence_index += 1
        fence = _parse_expected_fence_start(
            lines[fence_index].strip() if fence_index < len(lines) else "",
            expected_info="text",
        )
        if fence is None:
            raise ValueError(
                f"media_prompt_trace_context artifact {error_label} block is invalid"
            )
        content_start = fence_index + 1
        content_end = content_start
        while content_end < len(lines) and lines[content_end].strip() != fence:
            content_end += 1
        if content_end >= len(lines):
            raise ValueError(
                f"media_prompt_trace_context artifact {error_label} block is invalid"
            )
        return "\n".join(lines[content_start:content_end]).strip()
    return None


def _extract_section_fenced_block(
    lines: Sequence[str],
    *,
    fence_info: str,
    error_label: str,
) -> str | None:
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    fence = _parse_expected_fence_start(
        lines[index].strip() if index < len(lines) else "",
        expected_info=fence_info,
    )
    if fence is None:
        return None
    content_start = index + 1
    content_end = content_start
    while content_end < len(lines) and lines[content_end].strip() != fence:
        content_end += 1
    if content_end >= len(lines):
        raise ValueError(
            f"media_prompt_trace_context artifact {error_label} is invalid"
        )
    return "\n".join(lines[content_start:content_end]).strip()


def _format_markdown_fence(info: str, content: str) -> list[str]:
    text = str(content)
    longest_backtick_run = max(
        (len(match.group(0)) for match in re.finditer(r"`{3,}", text)),
        default=2,
    )
    fence = "`" * max(3, longest_backtick_run + 1)
    return [f"{fence}{info}", text, fence]


def _parse_any_fence_start(stripped_line: str) -> str | None:
    match = re.fullmatch(r"(`{3,})([A-Za-z0-9_-]*)?", stripped_line)
    if match is None:
        return None
    return match.group(1)


def _parse_expected_fence_start(
    stripped_line: str,
    *,
    expected_info: str,
) -> str | None:
    match = re.fullmatch(r"(`{3,})([A-Za-z0-9_-]+)", stripped_line)
    if match is None or match.group(2) != expected_info:
        return None
    return match.group(1)


def _generation_context_field_matches(
    generation_context: Mapping[str, Any],
    *,
    allowed_keys: set[str],
    expected: object,
) -> bool:
    values = _generation_context_field_values(
        generation_context,
        allowed_keys=allowed_keys,
    )
    request = generation_context.get("request")
    if isinstance(request, Mapping):
        values.extend(
            _generation_context_field_values(
                request,
                allowed_keys=allowed_keys,
            )
        )
    return bool(values) and all(_values_match(value, expected) for value in values)


def _generation_context_field_values(
    generation_context: Mapping[str, Any],
    *,
    allowed_keys: set[str],
) -> list[Any]:
    return [
        generation_context[key]
        for key in allowed_keys
        if key in generation_context
    ]


def _validate_workflow_param_trace_chain(
    *,
    context: Mapping[str, Any],
    generation_context: Mapping[str, Any],
    actual_trace: Mapping[str, Any] | None,
) -> None:
    actual = _normalize_workflow_param_trace(actual_trace)
    context_trace = _extract_workflow_param_trace(context)
    artifact_traces: list[dict[str, Any]] = []
    artifact_trace = _extract_workflow_param_trace(generation_context)
    if artifact_trace:
        artifact_traces.append(artifact_trace)
    request = generation_context.get("request")
    if isinstance(request, Mapping):
        request_trace = _extract_workflow_param_trace(request)
        if request_trace:
            artifact_traces.append(request_trace)

    if not actual and not context_trace and not artifact_traces:
        return
    if not actual:
        raise ValueError(
            "media_prompt_trace_context workflow_param_inputs do not match workflow_params"
        )
    if not context_trace:
        raise ValueError("media_prompt_trace_context missing workflow_param_inputs")
    if not artifact_traces:
        raise ValueError(
            "media_prompt_trace_context artifact workflow_param_inputs are missing"
        )
    if context_trace != actual:
        raise ValueError(
            "media_prompt_trace_context workflow_param_inputs do not match workflow_params"
        )
    if any(artifact_trace != actual for artifact_trace in artifact_traces):
        raise ValueError(
            "media_prompt_trace_context artifact workflow_param_inputs do not match workflow_params"
        )


def _validate_workflow_file_trace_chain(
    *,
    context: Mapping[str, Any],
    generation_context: Mapping[str, Any],
    expected_trace: Mapping[str, Any] | None = None,
) -> None:
    expected = extract_workflow_file_trace(expected_trace or {})
    context_trace = extract_workflow_file_trace(context)
    artifact_traces: list[dict[str, Any]] = []
    artifact_trace = extract_workflow_file_trace(generation_context)
    if artifact_trace:
        artifact_traces.append(artifact_trace)
    request = generation_context.get("request")
    if isinstance(request, Mapping):
        request_trace = extract_workflow_file_trace(request)
        if request_trace:
            artifact_traces.append(request_trace)

    if expected:
        if not context_trace:
            raise ValueError("media_prompt_trace_context missing workflow file trace")
        if context_trace != expected:
            raise ValueError(
                "media_prompt_trace_context workflow file trace does not match resolved workflow file"
            )
        if not artifact_traces:
            raise ValueError(
                "media_prompt_trace_context artifact workflow file trace is missing"
            )
        if any(artifact_trace != expected for artifact_trace in artifact_traces):
            raise ValueError(
                "media_prompt_trace_context artifact workflow file trace does not match resolved workflow file"
            )
        return

    if not context_trace and not artifact_traces:
        return
    if not context_trace:
        raise ValueError("media_prompt_trace_context missing workflow file trace")
    if not artifact_traces:
        raise ValueError(
            "media_prompt_trace_context artifact workflow file trace is missing"
        )
    if any(artifact_trace != context_trace for artifact_trace in artifact_traces):
        raise ValueError(
            "media_prompt_trace_context artifact workflow file trace does not match"
        )


def _extract_workflow_param_trace(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if "workflow_param_inputs" not in payload:
        return {}
    normalized_inputs = _normalize_workflow_param_inputs(
        payload.get("workflow_param_inputs")
    )
    provided_sha = str(payload.get("workflow_param_inputs_sha256") or "").strip()
    if not normalized_inputs or not provided_sha:
        raise ValueError("media_prompt_trace_context workflow_param_inputs are invalid")
    expected_sha = _workflow_param_inputs_sha256(normalized_inputs)
    if provided_sha != expected_sha:
        raise ValueError(
            "media_prompt_trace_context workflow_param_inputs_sha256 does not match"
        )
    return {
        "workflow_param_inputs": normalized_inputs,
        "workflow_param_inputs_sha256": provided_sha,
    }


def _normalize_workflow_param_trace(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or "workflow_param_inputs" not in payload:
        return {}
    normalized_inputs = _normalize_workflow_param_inputs(
        payload.get("workflow_param_inputs")
    )
    if not normalized_inputs:
        return {}
    provided_sha = str(payload.get("workflow_param_inputs_sha256") or "").strip()
    expected_sha = _workflow_param_inputs_sha256(normalized_inputs)
    if provided_sha and provided_sha != expected_sha:
        raise ValueError(
            "media_prompt_trace_context workflow_param_inputs_sha256 does not match"
        )
    return {
        "workflow_param_inputs": normalized_inputs,
        "workflow_param_inputs_sha256": expected_sha,
    }


def _traceable_workflow_param_inputs(
    workflow_params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(workflow_params, Mapping):
        return {}
    inputs: dict[str, Any] = {}
    for key, value in workflow_params.items():
        name = str(key or "").strip()
        if not name or not _is_traceable_workflow_param(name, value):
            continue
        normalized = _normalize_workflow_param_value(value)
        if normalized not in (None, "", [], {}):
            inputs[name] = normalized
    return dict(sorted(inputs.items()))


def _is_traceable_workflow_param(name: str, value: Any) -> bool:
    normalized_name = name.lower()
    if normalized_name in _WORKFLOW_PROMPT_ALIAS_PARAM_KEYS:
        return False
    if normalized_name in _NON_TRACEABLE_WORKFLOW_PARAM_KEYS:
        return False
    if normalized_name in _TRACEABLE_WORKFLOW_PARAM_KEYS:
        return True
    if normalized_name.endswith(_TRACEABLE_WORKFLOW_PARAM_SUFFIXES):
        return True
    if isinstance(value, Mapping):
        return any(
            _is_traceable_workflow_param(str(key or ""), item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(
            _is_traceable_workflow_param(name, item)
            or bool(_normalize_workflow_param_value(item))
            for item in value
        )
    if isinstance(value, Path):
        return True
    if isinstance(value, (bool, int, float)):
        return True
    if _is_custom_text_workflow_param_value(value):
        return True
    return False


def _validate_workflow_prompt_aliases(
    workflow_params: Mapping[str, Any] | None,
    *,
    prompt: str | None,
) -> None:
    if not isinstance(workflow_params, Mapping):
        return
    canonical_prompt = str(prompt or "").strip()
    alias_values: list[tuple[str, str]] = []
    for key, value in workflow_params.items():
        name = str(key or "").strip().lower()
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        if name == "prompt":
            if not canonical_prompt:
                canonical_prompt = text
            elif text != canonical_prompt:
                raise ValueError(
                    "media_prompt_trace_context workflow prompt alias does not match prompt"
                )
        elif name in _WORKFLOW_PROMPT_ALIAS_PARAM_KEYS:
            alias_values.append((name, text))
    for _name, value in alias_values:
        if not canonical_prompt or value != canonical_prompt:
            raise ValueError(
                "media_prompt_trace_context workflow prompt alias does not match prompt"
            )


def _validate_workflow_negative_prompt_aliases(
    workflow_params: Mapping[str, Any] | None,
) -> None:
    if not isinstance(workflow_params, Mapping):
        return
    canonical_seen = False
    canonical_value = ""
    values: list[str] = []
    for key, value in workflow_params.items():
        name = str(key or "").strip().lower()
        if name not in _WORKFLOW_NEGATIVE_PROMPT_ALIAS_PARAM_KEYS:
            continue
        if not isinstance(value, str):
            continue
        text = value.strip()
        if name == "negative_prompt":
            canonical_seen = True
            canonical_value = text
        if text:
            values.append(text)
    if canonical_seen and not canonical_value and values:
        raise ValueError(
            "media_prompt_trace_context workflow negative prompt alias does not match negative prompt"
        )
    if canonical_seen and canonical_value and any(
        value != canonical_value for value in values
    ):
        raise ValueError(
            "media_prompt_trace_context workflow negative prompt alias does not match negative prompt"
        )
    if len(set(values)) > 1:
        raise ValueError(
            "media_prompt_trace_context workflow negative prompt alias does not match negative prompt"
        )


def _is_custom_text_workflow_param_value(value: Any) -> bool:
    if isinstance(value, (str, bytes)):
        return bool(_normalize_workflow_param_value(value))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(
            isinstance(item, (str, bytes, Path)) and bool(_normalize_workflow_param_value(item))
            for item in value
        )
    return False


def _normalize_workflow_param_inputs(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    inputs: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        normalized = _normalize_workflow_param_value(item)
        if normalized not in (None, "", [], {}):
            inputs[name] = normalized
    return dict(sorted(inputs.items()))


def _normalize_workflow_param_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_workflow_param_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_workflow_param_value(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _normalize_trace_result(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_trace_result(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_trace_result(item) for item in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _workflow_param_inputs_sha256(inputs: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _normalize_workflow_param_inputs(inputs),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _values_match(actual: object, expected: object) -> bool:
    if isinstance(expected, int):
        try:
            return int(actual) == expected
        except (TypeError, ValueError):
            return False
    return str(actual).strip() == str(expected).strip()


__all__ = [
    "FINAL_PROMPT_ARTIFACT_DIR_NAME",
    "FINAL_PROMPT_ARTIFACT_FILE_NAME",
    "FINAL_PROMPT_ARTIFACT_SCHEMA",
    "MEDIA_TRACE_MEDIA_RESULT_FILE_NAME",
    "MEDIA_TRACE_MEDIA_RESULT_SCHEMA",
    "MEDIA_TRACE_RESULT_FILE_NAME",
    "MEDIA_TRACE_RESULT_SCHEMA",
    "build_media_prompt_trace_context",
    "build_workflow_params_trace",
    "media_workflow_result_artifact_exists",
    "media_workflow_trace_context",
    "require_media_prompt_trace_context",
    "summarize_media_workflow_result",
    "validate_media_prompt_trace_artifact",
    "write_final_prompt_artifact",
    "write_media_result_artifact",
    "write_media_workflow_result_artifact",
    "write_single_media_prompt_artifact",
    "write_single_media_prompt_trace_context",
]
