from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.content_bound_ip import (
    contains_decorative_ip_language,
    contains_weak_ip_action_language,
)
from pixelle_video.models.ip_duty import IPDutyPreset
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
    """Hard boundary checks for the final visual story plan used by prompt composition.

    The gate validates the final, merged frame plans.  It is not enough to validate
    the pre-batch route plan, because the batch loop owns the frame-level visual
    plans and IP fusion plans that actually reach the image prompt composer.
    """

    def validate(
        self,
        plan: VisualStoryEnginePlan,
        *,
        expected_frame_ids: Sequence[str] | None = None,
    ) -> list[VisualStoryQualityFinding]:
        findings: list[VisualStoryQualityFinding] = []
        route_ids = {route.route_id for route in plan.candidate_routes}
        if plan.selection.selected_route_id not in route_ids:
            findings.append(
                _error(
                    "selected_route_missing", "selected_route_id is not present in candidate_routes"
                )
            )
        if not plan.candidate_routes:
            findings.append(_error("no_routes", "candidate_routes must not be empty"))
        if len(plan.frame_visual_plans) != len(plan.frame_ip_fusion_plans):
            findings.append(
                _error(
                    "frame_fusion_count_mismatch",
                    "frame_visual_plans and frame_ip_fusion_plans must have equal length",
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
        if visual_ids and fusion_ids and visual_ids != fusion_ids:
            findings.append(
                _error(
                    "frame_fusion_order_mismatch",
                    "frame fusion plans must match frame visual plan order",
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
            else:
                if visual_ids != expected:
                    findings.append(
                        _error(
                            "frame_visual_coverage_mismatch",
                            "frame visual plans must exactly cover expected frame IDs in order",
                        )
                    )
                if fusion_ids != expected:
                    findings.append(
                        _error(
                            "frame_fusion_coverage_mismatch",
                            "frame fusion plans must exactly cover expected frame IDs in order",
                        )
                    )
        for frame_plan, fusion_plan in zip(
            plan.frame_visual_plans, plan.frame_ip_fusion_plans, strict=False
        ):
            text = _fusion_text(fusion_plan)
            has_ip_profile = (
                fusion_plan.ip_role is not VisualSignatureRole.NONE
                and fusion_plan.ip_visibility is not IPVisibilityLevel.NONE
            )
            if has_ip_profile:
                _validate_mandatory_ip_duty(frame_plan.frame_id, fusion_plan, findings)
                _validate_content_bound_ip(frame_plan.frame_id, frame_plan, fusion_plan, findings)
            if _contains_replacement_language(text) and frame_plan.required_subjects:
                findings.append(
                    _error(
                        "ip_replacement_risk",
                        f"{frame_plan.frame_id}: IP fusion appears to replace required article subjects",
                    )
                )
        return findings

    def validate_context(self, context: Mapping[str, Any]) -> list[VisualStoryQualityFinding]:
        # Lightweight context-level guard for callers that only have prompt_context.
        visual = context.get("frame_visual_plans") or ()
        fusion = context.get("frame_ip_fusion_plans") or ()
        findings: list[VisualStoryQualityFinding] = []
        if len(visual) != len(fusion):
            findings.append(
                _error(
                    "context_frame_fusion_count_mismatch",
                    "visual story context frame counts do not match",
                )
            )
        visual_ids = [
            str(item.get("frame_id") or "").strip() for item in visual if isinstance(item, Mapping)
        ]
        fusion_ids = [
            str(item.get("frame_id") or "").strip() for item in fusion if isinstance(item, Mapping)
        ]
        if len(visual_ids) != len(visual) or any(not frame_id for frame_id in visual_ids):
            findings.append(
                _error(
                    "invalid_context_frame_visual_record",
                    "visual story context contains an invalid frame visual record",
                )
            )
        if len(fusion_ids) != len(fusion) or any(not frame_id for frame_id in fusion_ids):
            findings.append(
                _error(
                    "invalid_context_frame_fusion_record",
                    "visual story context contains an invalid frame fusion record",
                )
            )
        if _duplicates(visual_ids):
            findings.append(
                _error(
                    "duplicate_context_frame_visual_id",
                    "visual story context frame visual IDs must be unique",
                )
            )
        if _duplicates(fusion_ids):
            findings.append(
                _error(
                    "duplicate_context_frame_fusion_id",
                    "visual story context frame fusion IDs must be unique",
                )
            )
        if visual_ids and fusion_ids and visual_ids != fusion_ids:
            findings.append(
                _error(
                    "context_frame_fusion_order_mismatch",
                    "visual story context frame IDs must match in order",
                )
            )
        by_id = {
            str(item.get("frame_id") or ""): item for item in visual if isinstance(item, Mapping)
        }
        for item in fusion:
            if not isinstance(item, Mapping):
                continue
            frame_id = str(item.get("frame_id") or "frame")
            _validate_content_bound_payload(frame_id, by_id.get(frame_id) or {}, item, findings)
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
                "visual story quality gate failed: " + "; ".join(error.message for error in errors)
            )

    def assert_context_valid(self, context: Mapping[str, Any]) -> None:
        findings = self.validate_context(context)
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            raise ValueError(
                "visual story context quality gate failed: "
                + "; ".join(error.message for error in errors)
            )


def _validate_mandatory_ip_duty(
    frame_id: str, fusion_plan: Any, findings: list[VisualStoryQualityFinding]
) -> None:
    if fusion_plan.ip_duty_preset in {
        IPDutyPreset.AUTO,
        IPDutyPreset.NONE,
        IPDutyPreset.BACKGROUND_SIGNATURE,
    }:
        findings.append(
            _error(
                "missing_content_bound_ip_duty_preset",
                f"{frame_id}: active IP frames require a concrete non-background content duty",
            )
        )
    if not fusion_plan.action_verb.strip():
        findings.append(
            _error("missing_ip_action_verb", f"{frame_id}: active IP frames require action_verb")
        )
    if not fusion_plan.interaction_target.strip():
        findings.append(
            _error(
                "missing_ip_interaction_target",
                f"{frame_id}: active IP frames require interaction_target",
            )
        )
    if not fusion_plan.scene_binding.strip():
        findings.append(
            _error(
                "missing_ip_scene_binding", f"{frame_id}: active IP frames require scene_binding"
            )
        )
    if not fusion_plan.channel_identity_removal_test.strip():
        findings.append(
            _error(
                "missing_channel_identity_removal_test",
                f"{frame_id}: active IP frames require channel_identity_removal_test",
            )
        )


def _validate_content_bound_ip(
    frame_id: str, frame_plan: Any, fusion_plan: Any, findings: list[VisualStoryQualityFinding]
) -> None:
    payload = fusion_plan.to_dict() if hasattr(fusion_plan, "to_dict") else dict(fusion_plan or {})
    visual_payload = (
        frame_plan.to_dict() if hasattr(frame_plan, "to_dict") else dict(frame_plan or {})
    )
    _validate_content_bound_payload(frame_id, visual_payload, payload, findings)


def _validate_content_bound_payload(
    frame_id: str,
    frame_plan: Mapping[str, Any],
    fusion_plan: Mapping[str, Any],
    findings: list[VisualStoryQualityFinding],
) -> None:
    if fusion_plan.get("rewrite_required"):
        findings.append(
            _error(
                "rewrite_required_not_consumed",
                f"{frame_id}: rewrite_required must trigger repair before prompt composition",
            )
        )
    if str(fusion_plan.get("content_relation_type") or "") != "content_bound":
        findings.append(
            _error(
                "missing_content_bound_relation",
                f"{frame_id}: IP fusion must declare content_relation_type=content_bound",
            )
        )
    if not isinstance(fusion_plan.get("content_bound_ip_presence_plan"), Mapping):
        findings.append(
            _error(
                "missing_content_bound_presence_plan",
                f"{frame_id}: IP fusion must carry content_bound_ip_presence_plan",
            )
        )
    for field in ("cognitive_anchor", "physical_metaphor", "scene_arena", "ip_action_affordance"):
        if not str(frame_plan.get(field) or fusion_plan.get(field) or "").strip():
            findings.append(
                _error(f"missing_{field}", f"{frame_id}: content-bound frame plan requires {field}")
            )
    text = _mapping_text(
        fusion_plan,
        (
            "placement_logic",
            "action_or_function",
            "positive_prompt_clause",
            "duty_goal",
            "action_verb",
            "interaction_target",
            "scene_binding",
            "presentation_form",
            "fallback_presentation",
        ),
    )
    if contains_decorative_ip_language(text):
        findings.append(
            _error(
                "decorative_ip_carrier",
                f"{frame_id}: IP uses decorative carrier language instead of content-bound participation",
            )
        )
    if contains_weak_ip_action_language(text):
        findings.append(
            _error("weak_ip_action", f"{frame_id}: IP action is too weak or decorative")
        )
    try:
        score = float(fusion_plan.get("decorative_risk_score") or 0.0)
    except (TypeError, ValueError):
        score = 1.0
    if score > 0.3:
        findings.append(
            _error(
                "decorative_risk_score_too_high",
                f"{frame_id}: decorative_risk_score must be <= 0.3",
            )
        )
    removal_test = str(fusion_plan.get("semantic_removal_test") or "")
    if not removal_test or not any(
        token in removal_test.lower() for token in ("weak", "weaken", "削弱", "失去", "loses")
    ):
        findings.append(
            _error(
                "missing_semantic_removal_test", f"{frame_id}: IP must pass semantic removal test"
            )
        )


def _fusion_text(fusion_plan: Any) -> str:
    values = [
        getattr(fusion_plan, "placement_logic", ""),
        getattr(fusion_plan, "action_or_function", ""),
        getattr(fusion_plan, "relation_to_article_subject", ""),
        getattr(fusion_plan, "positive_prompt_clause", ""),
        getattr(fusion_plan, "duty_goal", ""),
        getattr(fusion_plan, "action_verb", ""),
        getattr(fusion_plan, "interaction_target", ""),
        getattr(fusion_plan, "scene_binding", ""),
        getattr(fusion_plan, "semantic_removal_test", ""),
        getattr(fusion_plan, "channel_identity_removal_test", ""),
        " ".join(getattr(fusion_plan, "negative_constraints", ()) or ()),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _mapping_text(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    return " ".join(str(mapping.get(key) or "") for key in keys).lower()


def _contains_replacement_language(text: str) -> bool:
    markers = (
        "replace the article subject",
        "replace required subject",
        "替代文章主体",
        "替代原文主体",
        "替换文章主体",
        "替换原文主体",
    )
    return any(marker in text for marker in markers)


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
