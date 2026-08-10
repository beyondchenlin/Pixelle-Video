from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_story_engine import (
    IPVisibilityLevel,
    VisualSignatureRole,
    VisualStoryEnginePlan,
)


@dataclass(frozen=True)
class VisualStoryQualityFinding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


class VisualStoryQualityGate:
    """Validate the content-only Visual Story boundary.

    Visual Story owns content routes and frame visual plans only. Any active
    recurring-IP/signature plan at this stage is a regression because canonical
    V4.5 final projection is the sole visual-signature owner.
    """

    def validate(
        self,
        plan: VisualStoryEnginePlan,
        *,
        expected_frame_ids: Sequence[str] | None = None,
    ) -> list[VisualStoryQualityFinding]:
        findings: list[VisualStoryQualityFinding] = []
        route_ids = {route.route_id for route in plan.candidate_routes}
        if not plan.candidate_routes:
            findings.append(_error("no_routes", "candidate_routes must not be empty"))
        elif plan.selection.selected_route_id not in route_ids:
            findings.append(
                _error(
                    "selected_route_missing",
                    "selected_route_id is not present in candidate_routes",
                )
            )

        visual_ids = [item.frame_id for item in plan.frame_visual_plans]
        fusion_ids = [item.frame_id for item in plan.frame_ip_fusion_plans]
        if _duplicates(visual_ids):
            findings.append(
                _error("duplicate_frame_visual_id", "frame visual plan IDs must be unique")
            )
        if _duplicates(fusion_ids):
            findings.append(
                _error("duplicate_frame_fusion_id", "frame fusion plan IDs must be unique")
            )
        if fusion_ids and visual_ids != fusion_ids:
            findings.append(
                _error(
                    "frame_fusion_order_mismatch",
                    "compatibility fusion placeholders must match frame visual plan order",
                )
            )
        if len(plan.frame_visual_plans) != len(plan.frame_ip_fusion_plans):
            findings.append(
                _error(
                    "frame_fusion_count_mismatch",
                    "compatibility fusion placeholder count must match frame visual plans",
                )
            )

        if expected_frame_ids is not None:
            expected = [str(frame_id or "").strip() for frame_id in expected_frame_ids]
            if not expected or any(not frame_id for frame_id in expected) or _duplicates(expected):
                findings.append(
                    _error(
                        "invalid_expected_frame_ids",
                        "expected frame IDs must be non-empty and unique",
                    )
                )
            elif visual_ids != expected:
                findings.append(
                    _error(
                        "frame_visual_coverage_mismatch",
                        "frame visual plans must exactly cover expected frame IDs in order",
                    )
                )
            if fusion_ids and fusion_ids != expected:
                findings.append(
                    _error(
                        "frame_fusion_coverage_mismatch",
                        "compatibility fusion placeholders must cover expected frame IDs in order",
                    )
                )

        for fusion_plan in plan.frame_ip_fusion_plans:
            if _active_ip_fusion(fusion_plan):
                findings.append(
                    _error(
                        "legacy_ip_runtime_reintroduced",
                        f"{fusion_plan.frame_id}: active recurring-IP planning is forbidden in Visual Story; canonical V4.5 final projection owns visual signatures",
                    )
                )
        return findings

    def validate_context(self, context: Mapping[str, Any]) -> list[VisualStoryQualityFinding]:
        visual = context.get("frame_visual_plans") or ()
        fusion = context.get("frame_ip_fusion_plans") or ()
        findings: list[VisualStoryQualityFinding] = []

        visual_ids = _mapping_frame_ids(
            visual,
            invalid_code="invalid_context_frame_visual_record",
            invalid_message="visual story context contains an invalid frame visual record",
            findings=findings,
        )
        if _duplicates(visual_ids):
            findings.append(
                _error(
                    "duplicate_context_frame_visual_id",
                    "visual story context frame visual IDs must be unique",
                )
            )

        # Content-only prompt contexts may omit historical fusion placeholders.
        if not fusion:
            return findings

        fusion_ids = _mapping_frame_ids(
            fusion,
            invalid_code="invalid_context_frame_fusion_record",
            invalid_message="visual story context contains an invalid frame fusion record",
            findings=findings,
        )
        if _duplicates(fusion_ids):
            findings.append(
                _error(
                    "duplicate_context_frame_fusion_id",
                    "visual story context frame fusion IDs must be unique",
                )
            )
        if visual_ids and fusion_ids != visual_ids:
            findings.append(
                _error(
                    "context_frame_fusion_order_mismatch",
                    "compatibility fusion placeholder IDs must match visual frame IDs",
                )
            )
        for item in fusion:
            if isinstance(item, Mapping) and _active_ip_fusion_mapping(item):
                frame_id = str(item.get("frame_id") or "frame")
                findings.append(
                    _error(
                        "legacy_ip_runtime_reintroduced",
                        f"{frame_id}: active recurring-IP context is forbidden in Visual Story",
                    )
                )
        return findings

    def assert_valid(
        self,
        plan: VisualStoryEnginePlan,
        *,
        expected_frame_ids: Sequence[str] | None = None,
    ) -> None:
        findings = self.validate(plan, expected_frame_ids=expected_frame_ids)
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            raise ValueError(
                "visual story quality gate failed: "
                + "; ".join(error.message for error in errors)
            )

    def assert_context_valid(self, context: Mapping[str, Any]) -> None:
        findings = self.validate_context(context)
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            raise ValueError(
                "visual story context quality gate failed: "
                + "; ".join(error.message for error in errors)
            )


def _active_ip_fusion(fusion_plan: Any) -> bool:
    return (
        getattr(fusion_plan, "ip_role", VisualSignatureRole.NONE)
        is not VisualSignatureRole.NONE
        or getattr(fusion_plan, "ip_visibility", IPVisibilityLevel.NONE)
        is not IPVisibilityLevel.NONE
    )


def _active_ip_fusion_mapping(value: Mapping[str, Any]) -> bool:
    role = str(value.get("ip_role") or "none").strip().lower()
    visibility = str(value.get("ip_visibility") or "none").strip().lower()
    return role not in {"", "none"} or visibility not in {"", "none"}


def _mapping_frame_ids(
    values: Any,
    *,
    invalid_code: str,
    invalid_message: str,
    findings: list[VisualStoryQualityFinding],
) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        findings.append(_error(invalid_code, invalid_message))
        return []
    result: list[str] = []
    for item in values:
        if not isinstance(item, Mapping):
            findings.append(_error(invalid_code, invalid_message))
            continue
        frame_id = str(item.get("frame_id") or "").strip()
        if not frame_id:
            findings.append(_error(invalid_code, invalid_message))
            continue
        result.append(frame_id)
    return result


def _error(code: str, message: str) -> VisualStoryQualityFinding:
    return VisualStoryQualityFinding("error", code, message)


def _duplicates(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)


__all__ = ["VisualStoryQualityFinding", "VisualStoryQualityGate"]
