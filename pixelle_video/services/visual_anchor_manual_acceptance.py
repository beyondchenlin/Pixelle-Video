from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANUAL_ACCEPTANCE_SCHEMA_VERSION = "visual_anchor_manual_acceptance.v4"
_SAFE_FRAME_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


class VisualAnchorManualAcceptanceChecks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    story_content_visible: bool
    identity_present: bool
    identity_instance_count_one: bool
    identity_traits_recognizable: bool
    perspective_lighting_material_natural: bool
    support_contact_occlusion_natural: bool
    no_sticker_floating_or_penetration: bool
    size_and_position_fit_current_composition: bool
    unique_final_plan_submitted: bool
    identity_condition_bound_to_first_request: bool
    generation_binding_and_post_audit_complete: bool
    continuous_scene_consistency: bool
    original_first_generation_unmodified: bool

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_preflight_check(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        legacy_story_check = normalized.pop("protected_facts_visible", None)
        normalized.setdefault("story_content_visible", legacy_story_check)
        legacy_value = normalized.pop(
            "preflight_and_post_audit_complete",
            None,
        )
        deterministic_value = normalized.pop(
            "deterministic_fusion_and_post_audit_complete",
            None,
        )
        legacy_identity_condition = normalized.pop(
            "first_generation_reference_bound",
            None,
        )
        normalized.setdefault(
            "identity_condition_bound_to_first_request",
            legacy_identity_condition,
        )
        normalized.setdefault(
            "generation_binding_and_post_audit_complete",
            deterministic_value if deterministic_value is not None else legacy_value,
        )
        return normalized

    @property
    def all_passed(self) -> bool:
        return all(self.model_dump().values())


class VisualAnchorManualAcceptanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[MANUAL_ACCEPTANCE_SCHEMA_VERSION] = (
        MANUAL_ACCEPTANCE_SCHEMA_VERSION
    )
    task_id: str
    acceptance_batch_id: str
    acceptance_round: int = Field(ge=1)
    sample_id: str
    frame_id: str
    random_seed: int = Field(ge=1, le=2**64 - 1)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    first_request_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["passed", "failed"]
    checks: VisualAnchorManualAcceptanceChecks
    failure_reasons: list[str] = Field(default_factory=list)
    reviewer: str
    recorded_at_utc: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    artifact_relative_path: str = ""

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_schema_version(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        if normalized.get("schema_version") in {
            "visual_anchor_manual_acceptance.v1",
            "visual_anchor_manual_acceptance.v2",
            "visual_anchor_manual_acceptance.v3",
        }:
            normalized["schema_version"] = MANUAL_ACCEPTANCE_SCHEMA_VERSION
        return normalized

    @field_validator(
        "task_id",
        "acceptance_batch_id",
        "sample_id",
        "frame_id",
        "reviewer",
        "recorded_at_utc",
        mode="before",
    )
    @classmethod
    def _validate_required_text(cls, value: object, info) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return " ".join(value.split())

    @field_validator("failure_reasons")
    @classmethod
    def _validate_failure_reasons(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("manual acceptance failure reasons must be non-empty")
            result.append(" ".join(item.split()))
        return result

    @model_validator(mode="after")
    def _validate_decision(self) -> "VisualAnchorManualAcceptanceRecord":
        if self.status == "passed":
            if not self.checks.all_passed:
                raise ValueError(
                    "manual acceptance cannot pass while any required check fails"
                )
            if self.failure_reasons:
                raise ValueError(
                    "passed manual acceptance cannot contain failure reasons"
                )
        else:
            if self.checks.all_passed:
                raise ValueError(
                    "failed manual acceptance must contain at least one failed check"
                )
            if not self.failure_reasons:
                raise ValueError(
                    "failed manual acceptance must contain failure reasons"
                )
        return self


def identity_condition_binding_succeeded(
    *,
    generation_request: Mapping[str, object],
    reference_condition: Mapping[str, object],
    binding_audit: Mapping[str, object],
) -> bool:
    """Report only whether the declared identity input reached the first request."""

    if binding_audit.get("status") != "passed":
        return False
    actual_execution = binding_audit.get("actual_execution")
    if not isinstance(actual_execution, Mapping):
        return False
    conditioning_mode = generation_request.get("identity_conditioning_mode")
    if conditioning_mode == "reference_image":
        expected_digest = reference_condition.get("asset_sha256")
        return (
            isinstance(expected_digest, str)
            and bool(expected_digest)
            and actual_execution.get("uploaded_reference_sha256")
            == expected_digest
            and actual_execution.get("reference_conditioning_input_count") == 1
        )
    if conditioning_mode == "text_profile":
        return (
            actual_execution.get("identity_conditioning_mode") == "text_profile"
            and actual_execution.get("reference_conditioning_input_count") == 0
        )
    return False


def record_visual_anchor_manual_acceptance(
    *,
    task_dir: str | Path,
    image_path: str | Path,
    rendered_audit_path: str | Path,
    first_request_binding_path: str | Path,
    record: VisualAnchorManualAcceptanceRecord,
) -> VisualAnchorManualAcceptanceRecord:
    """Persist an explicit human decision without modifying generated media."""

    root = Path(task_dir).resolve()
    if not root.is_dir():
        raise ValueError("visual-anchor acceptance task directory does not exist")
    image = _task_file(root, image_path, "generated image")
    rendered_audit = _task_file(root, rendered_audit_path, "rendered audit")
    first_binding = _task_file(
        root,
        first_request_binding_path,
        "first request binding",
    )
    comparisons = (
        (record.image_sha256, _file_sha256(image), "generated image"),
        (
            record.rendered_audit_sha256,
            _file_sha256(rendered_audit),
            "rendered audit",
        ),
        (
            record.first_request_binding_sha256,
            _file_sha256(first_binding),
            "first request binding",
        ),
    )
    for expected, actual, label in comparisons:
        if expected != actual:
            raise ValueError(f"manual acceptance {label} digest differs")
    rendered_payload = _json_object(rendered_audit, "rendered audit")
    binding_payload = _json_object(first_binding, "first request binding")
    expected_values = (
        (rendered_payload.get("status"), "passed", "rendered audit status"),
        (binding_payload.get("status"), "passed", "first request binding status"),
        (rendered_payload.get("task_id"), record.task_id, "rendered audit task id"),
        (binding_payload.get("task_id"), record.task_id, "binding task id"),
        (rendered_payload.get("frame_id"), record.frame_id, "rendered audit frame id"),
        (binding_payload.get("frame_id"), record.frame_id, "binding frame id"),
        (
            rendered_payload.get("random_seed"),
            record.random_seed,
            "rendered audit random seed",
        ),
        (
            binding_payload.get("random_seed"),
            record.random_seed,
            "binding random seed",
        ),
        (
            rendered_payload.get("image_sha256"),
            record.image_sha256,
            "rendered audit image digest",
        ),
    )
    for actual, expected, label in expected_values:
        if actual != expected:
            raise ValueError(f"manual acceptance {label} differs")

    output_dir = (root / "visual_anchor_generation" / "manual_acceptance").resolve()
    output_dir.relative_to(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (output_dir / f"{_safe_frame_id(record.frame_id)}.json").resolve()
    output_path.relative_to(output_dir)
    persisted = record.model_copy(
        update={"artifact_relative_path": output_path.relative_to(root).as_posix()}
    )
    if output_path.is_file():
        existing = VisualAnchorManualAcceptanceRecord.model_validate(
            _json_object(output_path, "existing manual acceptance")
        )
        if existing != persisted:
            raise ValueError(
                "manual acceptance is immutable; create a new task for another decision"
            )
        return existing
    temporary_path = output_dir / f".tmp-{uuid4().hex[:12]}"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                persisted.model_dump(mode="json"),
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return persisted


def manual_acceptance_artifact_relative_path(frame_id: str) -> str:
    return (
        "visual_anchor_generation/manual_acceptance/"
        f"{_safe_frame_id(frame_id)}.json"
    )


def _task_file(root: Path, value: str | Path, label: str) -> Path:
    candidate = Path(value)
    path = (
        candidate.resolve()
        if candidate.is_absolute()
        else (root / candidate).resolve()
    )
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manual acceptance {label} escaped the task directory") from exc
    if not path.is_file():
        raise ValueError(f"manual acceptance {label} does not exist")
    return path


def _safe_frame_id(frame_id: str) -> str:
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise ValueError("manual acceptance frame id is required")
    normalized = _SAFE_FRAME_ID_RE.sub("_", frame_id).strip("_") or "frame"
    digest = hashlib.sha256(frame_id.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:32].rstrip('_-') or 'frame'}-{digest}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manual acceptance {label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"manual acceptance {label} must be an object")
    return payload


__all__ = [
    "MANUAL_ACCEPTANCE_SCHEMA_VERSION",
    "VisualAnchorManualAcceptanceChecks",
    "VisualAnchorManualAcceptanceRecord",
    "identity_condition_binding_succeeded",
    "manual_acceptance_artifact_relative_path",
    "record_visual_anchor_manual_acceptance",
]
