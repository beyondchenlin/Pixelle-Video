from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.visual_anchor_two_stage import (
    VisualAnchorImageGenerationRequest,
    VisualAnchorTwoStageFrameResult,
)
from pixelle_video.utils.os_util import get_task_path


@dataclass(frozen=True)
class VisualAnchorRegenerationContext:
    """An inherited, immutable two-stage request for one workbench regeneration."""

    frame_result: VisualAnchorTwoStageFrameResult
    task_root: Path

    @property
    def generation_request(self) -> VisualAnchorImageGenerationRequest:
        return self.frame_result.generation_request


def prepare_visual_anchor_regeneration(
    *,
    prompt_plan: PromptPlan,
    task_id: str,
) -> VisualAnchorRegenerationContext | None:
    """Clone an approved request without rerunning either planning stage."""

    raw = prompt_plan.metadata.get("visual_anchor_two_stage")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(
            "visual-anchor prompt-plan metadata must be a mapping"
        )
    raw_request = raw.get("generation_request")
    if not isinstance(raw_request, Mapping):
        raise ValueError(
            "visual-anchor prompt-plan metadata must contain a generation request"
        )
    if prompt_plan.contract_version != raw_request.get("request_version"):
        raise ValueError(
            "visual-anchor regeneration contract version differs from prompt plan"
        )
    if prompt_plan.contract_content_sha256 != _contract_sha256(raw):
        raise ValueError(
            "visual-anchor regeneration contract digest differs from prompt plan"
        )

    source_result = VisualAnchorTwoStageFrameResult.model_validate(raw)
    source_request = source_result.generation_request
    if prompt_plan.frame_id != source_result.frame_id:
        raise ValueError("visual-anchor regeneration frame id differs from prompt plan")
    if prompt_plan.final_prompt != source_request.final_positive_prompt:
        raise ValueError(
            "visual-anchor regeneration positive prompt differs from prompt plan"
        )
    if (prompt_plan.final_negative_prompt or "") != source_request.final_negative_prompt:
        raise ValueError(
            "visual-anchor regeneration negative prompt differs from prompt plan"
        )
    if prompt_plan.identity_content_sha256 != source_request.identity_content_sha256:
        raise ValueError(
            "visual-anchor regeneration identity digest differs from prompt plan"
        )
    cloned_payload = source_result.model_dump(mode="json")
    cloned_payload["generation_request"] = {
        **cloned_payload["generation_request"],
        "task_id": task_id,
    }
    cloned_result = VisualAnchorTwoStageFrameResult.model_validate(cloned_payload)
    task_root = Path(get_task_path(task_id)).resolve()
    task_root.mkdir(parents=True, exist_ok=True)
    _inherit_reference_asset(
        source_request=source_request,
        target_request=cloned_result.generation_request,
        target_task_root=task_root,
    )
    return VisualAnchorRegenerationContext(
        frame_result=cloned_result,
        task_root=task_root,
    )


def visual_anchor_regenerated_image_path(
    context: VisualAnchorRegenerationContext,
) -> Path:
    normalized_frame_id = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in context.frame_result.frame_id
    ).strip("_")
    if not normalized_frame_id:
        raise ValueError("visual-anchor regeneration frame id is invalid")
    frame_digest = hashlib.sha256(
        context.frame_result.frame_id.encode("utf-8")
    ).hexdigest()[:12]
    safe_frame_id = f"{normalized_frame_id[:32].rstrip('_-') or 'frame'}-{frame_digest}"
    result = (
        context.task_root
        / "frames"
        / f"{safe_frame_id}_regenerated.png"
    ).resolve()
    result.relative_to(context.task_root)
    return result


def _inherit_reference_asset(
    *,
    source_request: VisualAnchorImageGenerationRequest,
    target_request: VisualAnchorImageGenerationRequest,
    target_task_root: Path,
) -> None:
    if source_request.identity_reference_condition != target_request.identity_reference_condition:
        raise ValueError("visual-anchor regeneration changed the reference condition")
    condition = target_request.identity_reference_condition
    if condition is None:
        return
    source_task_root = Path(get_task_path(source_request.task_id)).resolve()
    source_path = (
        source_task_root / condition.workflow_asset_relative_path
    ).resolve()
    target_path = (
        target_task_root / condition.workflow_asset_relative_path
    ).resolve()
    try:
        source_path.relative_to(source_task_root)
        target_path.relative_to(target_task_root)
    except ValueError as exc:
        raise ValueError(
            "visual-anchor regeneration reference path escaped its task"
        ) from exc
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError(
            "visual-anchor regeneration source reference is unavailable"
        )
    if _file_sha256(source_path) != condition.asset_sha256:
        raise ValueError(
            "visual-anchor regeneration source reference digest changed"
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        if not target_path.is_file() or _file_sha256(target_path) != condition.asset_sha256:
            raise ValueError(
                "visual-anchor regeneration target reference conflicts with the contract"
            )
    else:
        temporary_path = target_path.parent / f".tmp-{uuid4().hex[:12]}"
        try:
            shutil.copyfile(source_path, temporary_path)
            if _file_sha256(temporary_path) != condition.asset_sha256:
                raise ValueError(
                    "visual-anchor regeneration copied reference digest changed"
                )
            os.replace(temporary_path, target_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    asset_payload = {
        "version": "reference_image_asset/v1",
        "original_display_name": "inherited_visual_anchor_reference",
        "asset": {
            "sha256": condition.asset_sha256,
            "workflow_sha256": condition.asset_sha256,
            "workflow_mime_type": condition.mime_type,
            "workflow_width": condition.width,
            "workflow_height": condition.height,
            "workflow_byte_size": condition.byte_size,
            "mime_type": condition.mime_type,
            "width": condition.width,
            "height": condition.height,
            "byte_size": condition.byte_size,
            "task_asset_relative_path": condition.workflow_asset_relative_path,
            "vision_asset_relative_path": None,
            "workflow_asset_relative_path": condition.workflow_asset_relative_path,
            "source_kind": "visual_anchor_inherited_regeneration",
        },
        "metadata": {
            "artifact_version": "reference_image_asset/v1",
            "identity_resource_version": target_request.identity_resource_version,
            "source_task_id": source_request.task_id,
        },
    }
    asset_path = (target_task_root / "reference_image" / "asset.json").resolve()
    asset_path.relative_to(target_task_root)
    _write_immutable_json(asset_path, asset_payload)


def _contract_sha256(frame_result: Mapping[str, object]) -> str:
    payload = json.dumps(
        _json_compatible_copy(frame_result),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_compatible_copy(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _json_compatible_copy(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible_copy(item) for item in value]
    return value


def _write_immutable_json(path: Path, payload: Mapping[str, object]) -> None:
    serialized = json.dumps(
        dict(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if path.read_text(encoding="utf-8") != serialized:
            raise ValueError(
                "visual-anchor regeneration reference metadata is immutable"
            )
        return
    temporary_path = path.parent / f".tmp-{uuid4().hex[:12]}"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "VisualAnchorRegenerationContext",
    "prepare_visual_anchor_regeneration",
    "visual_anchor_regenerated_image_path",
]
