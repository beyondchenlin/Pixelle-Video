from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pixelle_video.models.visual_anchor_two_stage import (
    VisualAnchorTwoStageFrameResult,
)
from pixelle_video.services.visual_anchor_generation_binding import (
    visual_anchor_first_request_binding_artifact_relative_path,
)
from pixelle_video.services.visual_anchor_reference_condition import (
    IDENTITY_REFERENCE_CONDITION_CROP,
    IDENTITY_REFERENCE_CONDITION_HEIGHT,
    IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD,
    IDENTITY_REFERENCE_CONDITION_WIDTH,
)

_SAFE_FRAME_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MANUAL_VISUAL_ACCEPTANCE_CHECKS = (
    "protected_facts_visible",
    "identity_present",
    "identity_instance_count_one",
    "identity_traits_recognizable",
    "perspective_lighting_material_natural",
    "support_contact_occlusion_natural",
    "no_sticker_floating_or_penetration",
    "size_and_position_fit_current_composition",
    "continuous_scene_consistency",
)


class VisualAnchorRenderedOutputAuditError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        result: VisualAnchorRenderedOutputAuditResult | None = None,
    ) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class VisualAnchorRenderedOutputAuditResult:
    """Deterministic evidence recorded immediately after the first image output."""

    status: Literal["passed", "failed"]
    reason: str
    task_id: str
    frame_id: str
    random_seed: int
    image_sha256: str
    reference_image_sha256: str
    checks: Mapping[str, bool]
    failure_codes: tuple[str, ...] = ()
    first_request_binding_artifact: str = ""
    audit_scope: Literal["first_generation_integrity"] = (
        "first_generation_integrity"
    )
    visual_acceptance_status: Literal["pending_manual_review"] = (
        "pending_manual_review"
    )
    manual_visual_acceptance_checks: tuple[str, ...] = (
        _MANUAL_VISUAL_ACCEPTANCE_CHECKS
    )
    artifact_relative_path: str = ""
    recorded_at_utc: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "visual_anchor_rendered_output_audit.v2",
            "status": self.status,
            "reason": self.reason,
            "audit_scope": self.audit_scope,
            "task_id": self.task_id,
            "frame_id": self.frame_id,
            "random_seed": self.random_seed,
            "image_sha256": self.image_sha256,
            "reference_image_sha256": self.reference_image_sha256,
            "checks": dict(self.checks),
            "failure_codes": list(self.failure_codes),
            "first_request_binding_artifact": self.first_request_binding_artifact,
            "visual_acceptance_status": self.visual_acceptance_status,
            "manual_visual_acceptance_checks": list(
                self.manual_visual_acceptance_checks
            ),
            "artifact_relative_path": self.artifact_relative_path,
            "recorded_at_utc": self.recorded_at_utc,
        }


class VisualAnchorRenderedOutputAudit:
    """Verify immutable first-generation provenance without another model call."""

    def __init__(self, *, task_dir: str | Path) -> None:
        self.task_dir = Path(task_dir).resolve()
        if not self.task_dir.is_dir():
            raise ValueError("visual-anchor audit task directory does not exist")

    async def evaluate(
        self,
        *,
        image_path: str | Path,
        frame_result: VisualAnchorTwoStageFrameResult | Mapping[str, Any],
    ) -> VisualAnchorRenderedOutputAuditResult:
        result_contract = (
            frame_result
            if isinstance(frame_result, VisualAnchorTwoStageFrameResult)
            else VisualAnchorTwoStageFrameResult.model_validate(frame_result)
        )
        request = result_contract.generation_request
        image = self._optional_task_file(image_path)
        reference = self._optional_task_file(
            self.task_dir
            / request.identity_reference_condition.workflow_asset_relative_path,
        )
        image_sha256 = _file_sha256(image) if image is not None else ""
        reference_sha256 = (
            _file_sha256(reference) if reference is not None else ""
        )
        binding_path = (
            self.task_dir
            / visual_anchor_first_request_binding_artifact_relative_path(
                request.frame_id
            )
        ).resolve()
        binding_path.relative_to(self.task_dir)

        failures: list[str] = []
        checks: dict[str, bool] = {}

        def check(name: str, condition: bool, failure_code: str) -> None:
            checks[name] = condition
            if not condition:
                failures.append(failure_code)

        check(
            "generated_image_exists",
            image is not None,
            "generated_image_missing",
        )
        check(
            "reference_image_exists",
            reference is not None,
            "reference_image_missing",
        )
        check(
            "reference_image_digest_unchanged",
            reference_sha256 == request.identity_reference_condition.asset_sha256,
            "reference_image_digest_changed",
        )
        check(
            "first_request_binding_artifact_exists",
            binding_path.is_file(),
            "first_request_binding_missing",
        )
        binding: Mapping[str, Any] = {}
        if binding_path.is_file():
            try:
                raw_binding = json.loads(
                    binding_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                raw_binding = None
            if not isinstance(raw_binding, Mapping):
                failures.append("first_request_binding_invalid")
                checks["first_request_binding_is_object"] = False
            else:
                binding = raw_binding
                checks["first_request_binding_is_object"] = True
        else:
            checks["first_request_binding_is_object"] = False

        expected_prompt_versions = {
            "content_stage": request.content_stage_prompt_version,
            "fusion_stage": request.fusion_stage_prompt_version,
            "preflight_review": request.preflight_review_prompt_version,
        }
        expected_reference = request.identity_reference_condition.model_dump(
            mode="json"
        )
        expected_execution = request.expected_execution.model_dump(mode="json")
        expected_sampler_config = {
            "seed": request.random_seed,
            "steps": request.expected_execution.steps,
            "cfg": request.expected_execution.cfg,
            "sampler_name": request.expected_execution.sampler_name,
            "scheduler": request.expected_execution.scheduler,
            "denoise": request.expected_execution.denoise,
        }
        actual_execution = binding.get("actual_execution")
        actual_execution = (
            actual_execution if isinstance(actual_execution, Mapping) else {}
        )
        actual_model_files = actual_execution.get("model_files")
        actual_sampler_config = actual_execution.get("sampler_config")
        captured_output_path = self._optional_task_file(
            actual_execution.get("generated_output_artifact"),
        )
        captured_output_sha256 = (
            _file_sha256(captured_output_path)
            if captured_output_path is not None
            else ""
        )
        actual_execution_config = {
            "workflow_key": request.workflow_key,
            "workflow_version_sha256": request.workflow_version_sha256,
            "width": actual_execution.get("width"),
            "height": actual_execution.get("height"),
            "model_files": actual_model_files,
            "sampler": actual_sampler_config,
            "reference_conditioning": {
                "mode": actual_execution.get("reference_conditioning_mode"),
                "input_count": actual_execution.get(
                    "reference_conditioning_input_count"
                ),
                "width": actual_execution.get("reference_conditioning_width"),
                "height": actual_execution.get("reference_conditioning_height"),
                "crop": actual_execution.get("reference_conditioning_crop"),
                "upscale_method": actual_execution.get(
                    "reference_conditioning_upscale_method"
                ),
                "auto_resize_images": actual_execution.get(
                    "reference_conditioning_auto_resize"
                ),
            },
        }
        comparisons = (
            ("binding_passed", binding.get("status") == "passed"),
            (
                "generation_request_version_preserved",
                binding.get("request_version") == request.request_version,
            ),
            ("task_id_preserved", binding.get("task_id") == request.task_id),
            ("frame_id_preserved", binding.get("frame_id") == request.frame_id),
            ("single_generation_attempt", binding.get("generation_attempt") == 1),
            ("random_seed_preserved", binding.get("random_seed") == request.random_seed),
            (
                "target_instance_count_one",
                binding.get("target_visual_anchor_instance_count") == 1,
            ),
            (
                "selected_fusion_method_preserved",
                binding.get("selected_fusion_method")
                == request.selected_fusion_method,
            ),
            (
                "final_manifestation_preserved",
                binding.get("final_manifestation") == request.final_manifestation,
            ),
            (
                "protected_fact_checks_preserved",
                binding.get("protected_fact_checks")
                == [
                    check.model_dump(mode="json")
                    for check in request.protected_fact_checks
                ],
            ),
            (
                "identity_trait_checks_preserved",
                binding.get("identity_trait_checks")
                == [
                    check.model_dump(mode="json")
                    for check in request.identity_trait_checks
                ],
            ),
            (
                "single_instance_evidence_preserved",
                binding.get("single_instance_prompt_evidence")
                == request.single_instance_prompt_evidence,
            ),
            (
                "prompt_versions_preserved",
                binding.get("prompt_versions") == expected_prompt_versions,
            ),
            (
                "positive_prompt_preserved",
                binding.get("positive_prompt_sha256")
                == _text_sha256(request.final_positive_prompt),
            ),
            (
                "negative_prompt_preserved",
                binding.get("negative_prompt_sha256")
                == _text_sha256(request.final_negative_prompt),
            ),
            (
                "identity_profile_preserved",
                binding.get("identity_profile_id") == request.identity_profile_id,
            ),
            (
                "identity_display_name_preserved",
                binding.get("identity_display_name")
                == request.identity_display_name,
            ),
            (
                "identity_core_traits_preserved",
                binding.get("identity_core_traits")
                == request.identity_core_traits,
            ),
            (
                "identity_resource_version_preserved",
                binding.get("identity_resource_version")
                == request.identity_resource_version,
            ),
            (
                "identity_digest_preserved",
                binding.get("identity_content_sha256")
                == request.identity_content_sha256,
            ),
            (
                "reference_condition_preserved",
                binding.get("reference_condition") == expected_reference,
            ),
            ("workflow_key_preserved", binding.get("workflow_key") == request.workflow_key),
            (
                "workflow_version_preserved",
                binding.get("workflow_version_sha256")
                == request.workflow_version_sha256,
            ),
            (
                "expected_execution_preserved",
                binding.get("expected_execution") == expected_execution,
            ),
            (
                "preflight_review_passed",
                binding.get("preflight_review_decision") == "pass",
            ),
            (
                "actual_comfyui_prompt_recorded",
                bool(str(actual_execution.get("comfyui_prompt_id") or "").strip()),
            ),
            (
                "actual_comfyui_execution_succeeded",
                actual_execution.get("execution_status") == "success",
            ),
            (
                "actual_uploaded_reference_preserved",
                actual_execution.get("uploaded_reference_sha256")
                == request.identity_reference_condition.asset_sha256,
            ),
            (
                "downloaded_image_matches_first_comfyui_output",
                actual_execution.get("generated_output_sha256") == image_sha256,
            ),
            (
                "captured_first_comfyui_output_preserved",
                captured_output_sha256 == image_sha256,
            ),
            (
                "actual_reference_input_node_preserved",
                actual_execution.get("reference_input_node_id")
                == request.identity_reference_condition.workflow_node_id,
            ),
            (
                "actual_conditioning_node_preserved",
                actual_execution.get("conditioning_node_id")
                == request.identity_reference_condition.conditioning_node_id,
            ),
            (
                "actual_conditioning_node_class_preserved",
                actual_execution.get("conditioning_node_class_type")
                == "TextEncodeZImageOmni",
            ),
            (
                "actual_single_reference_condition_preserved",
                actual_execution.get("reference_conditioning_input_count") == 1,
            ),
            (
                "actual_reference_scale_preserved",
                actual_execution.get("reference_scale_node_class_type")
                == "ImageScale"
                and actual_execution.get("reference_conditioning_width")
                == IDENTITY_REFERENCE_CONDITION_WIDTH
                and actual_execution.get("reference_conditioning_height")
                == IDENTITY_REFERENCE_CONDITION_HEIGHT
                and actual_execution.get("reference_conditioning_crop")
                == IDENTITY_REFERENCE_CONDITION_CROP
                and actual_execution.get(
                    "reference_conditioning_upscale_method"
                )
                == IDENTITY_REFERENCE_CONDITION_UPSCALE_METHOD
                and actual_execution.get("reference_conditioning_auto_resize")
                is False,
            ),
            (
                "actual_sampler_node_preserved",
                actual_execution.get("sampler_node_id")
                == request.identity_reference_condition.sampler_node_id,
            ),
            (
                "actual_binding_path_preserved",
                actual_execution.get("binding_path_node_ids")
                == request.identity_reference_condition.binding_path_node_ids,
            ),
            (
                "actual_resolution_recorded",
                actual_execution.get("width") == request.expected_execution.width
                and actual_execution.get("height")
                == request.expected_execution.height,
            ),
            (
                "actual_model_files_recorded",
                actual_model_files == request.expected_execution.model_files,
            ),
            (
                "actual_sampler_config_preserved",
                actual_sampler_config == expected_sampler_config,
            ),
            (
                "actual_execution_config_version_preserved",
                actual_execution.get("execution_config_sha256")
                == _canonical_json_sha256(actual_execution_config),
            ),
        )
        for name, condition in comparisons:
            check(name, condition, name)

        binding_artifact = (
            binding_path.relative_to(self.task_dir).as_posix()
            if binding_path.is_file()
            else ""
        )
        audit_result = self._write_result(
            VisualAnchorRenderedOutputAuditResult(
                status="failed" if failures else "passed",
                reason=(
                    failures[0]
                    if failures
                    else "first_generation_integrity_confirmed"
                ),
                task_id=request.task_id,
                frame_id=request.frame_id,
                random_seed=request.random_seed,
                image_sha256=image_sha256,
                reference_image_sha256=reference_sha256,
                checks=checks,
                failure_codes=tuple(failures),
                first_request_binding_artifact=binding_artifact,
            )
        )
        if not audit_result.passed:
            raise VisualAnchorRenderedOutputAuditError(
                "visual-anchor first-generation integrity audit failed",
                result=audit_result,
            )
        return audit_result

    def _optional_task_file(self, value: object) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        candidate = Path(text)
        path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.task_dir / candidate).resolve()
        )
        try:
            path.relative_to(self.task_dir)
        except ValueError:
            return None
        if not path.is_file() or path.is_symlink():
            return None
        return path

    def _write_result(
        self,
        result: VisualAnchorRenderedOutputAuditResult,
    ) -> VisualAnchorRenderedOutputAuditResult:
        output_dir = (
            self.task_dir / "visual_anchor_generation" / "rendered_audit"
        ).resolve()
        output_dir.relative_to(self.task_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = (output_dir / f"{_safe_frame_id(result.frame_id)}.json").resolve()
        output_path.relative_to(output_dir)
        result = replace(
            result,
            artifact_relative_path=output_path.relative_to(self.task_dir).as_posix(),
            recorded_at_utc=result.recorded_at_utc or datetime.now(UTC).isoformat(),
        )
        try:
            with output_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(result.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise ValueError(
                "visual-anchor rendered-output audit already exists; create a new task"
            ) from exc
        return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_frame_id(frame_id: str) -> str:
    normalized = _SAFE_FRAME_ID_RE.sub("_", frame_id).strip("._") or "frame"
    digest = hashlib.sha256(frame_id.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:32].rstrip('._-') or 'frame'}-{digest}"


__all__ = [
    "VisualAnchorRenderedOutputAudit",
    "VisualAnchorRenderedOutputAuditError",
    "VisualAnchorRenderedOutputAuditResult",
]
