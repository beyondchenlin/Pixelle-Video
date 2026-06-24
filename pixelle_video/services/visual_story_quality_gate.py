from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.ip_duty import IPDutyPreset
from pixelle_video.models.visual_story_engine import IPVisibilityLevel, VisualSignatureRole, VisualStoryEnginePlan


@dataclass(frozen=True)
class VisualStoryQualityFinding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


class VisualStoryQualityGate:
    """Hard boundary checks for the visual story engine.

    This is intentionally deterministic: LLMs recommend routes, but a route/fusion plan
    cannot pass if it drops frame coverage, omits selection, or asks IP to replace
    required article subjects.
    """

    def validate(self, plan: VisualStoryEnginePlan) -> list[VisualStoryQualityFinding]:
        findings: list[VisualStoryQualityFinding] = []
        route_ids = {route.route_id for route in plan.candidate_routes}
        if plan.selection.selected_route_id not in route_ids:
            findings.append(_error("selected_route_missing", "selected_route_id is not present in candidate_routes"))
        if not plan.candidate_routes:
            findings.append(_error("no_routes", "candidate_routes must not be empty"))
        if len(plan.frame_visual_plans) != len(plan.frame_ip_fusion_plans):
            findings.append(_error("frame_fusion_count_mismatch", "frame_visual_plans and frame_ip_fusion_plans must have equal length"))
        visual_ids = [item.frame_id for item in plan.frame_visual_plans]
        fusion_ids = [item.frame_id for item in plan.frame_ip_fusion_plans]
        if visual_ids and fusion_ids and visual_ids != fusion_ids:
            findings.append(_error("frame_fusion_order_mismatch", "frame fusion plans must match frame visual plan order"))
        for frame_plan, fusion_plan in zip(plan.frame_visual_plans, plan.frame_ip_fusion_plans, strict=False):
            text = " ".join(
                [
                    fusion_plan.placement_logic,
                    fusion_plan.action_or_function,
                    fusion_plan.relation_to_article_subject,
                    fusion_plan.positive_prompt_clause,
                    fusion_plan.duty_goal,
                    fusion_plan.action_verb,
                    fusion_plan.interaction_target,
                    fusion_plan.scene_binding,
                    fusion_plan.semantic_removal_test,
                    fusion_plan.channel_identity_removal_test,
                    " ".join(fusion_plan.negative_constraints),
                ]
            ).lower()
            has_ip_profile = fusion_plan.ip_role is not VisualSignatureRole.NONE and fusion_plan.ip_visibility is not IPVisibilityLevel.NONE
            if has_ip_profile:
                _validate_mandatory_ip_duty(frame_plan.frame_id, fusion_plan, findings)
            if _contains_replacement_language(text) and frame_plan.required_subjects:
                findings.append(
                    _error(
                        "ip_replacement_risk",
                        f"{frame_plan.frame_id}: IP fusion appears to replace required article subjects",
                    )
                )
        return findings

    def assert_valid(self, plan: VisualStoryEnginePlan) -> None:
        findings = self.validate(plan)
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            raise ValueError("visual story quality gate failed: " + "; ".join(error.message for error in errors))


def _validate_mandatory_ip_duty(frame_id: str, fusion_plan: Any, findings: list[VisualStoryQualityFinding]) -> None:
    if fusion_plan.ip_duty_preset in {IPDutyPreset.AUTO, IPDutyPreset.NONE}:
        findings.append(_error("missing_ip_duty_preset", f"{frame_id}: active IP frames require a concrete ip_duty_preset"))
    if not fusion_plan.action_verb.strip():
        findings.append(_error("missing_ip_action_verb", f"{frame_id}: active IP frames require action_verb"))
    if not fusion_plan.interaction_target.strip():
        findings.append(_error("missing_ip_interaction_target", f"{frame_id}: active IP frames require interaction_target"))
    if not fusion_plan.scene_binding.strip():
        findings.append(_error("missing_ip_scene_binding", f"{frame_id}: active IP frames require scene_binding"))
    if not fusion_plan.channel_identity_removal_test.strip():
        findings.append(_error("missing_channel_identity_removal_test", f"{frame_id}: active IP frames require channel_identity_removal_test"))
    decorative_terms = ("只是出现", "站在旁边", "quiet witness at the edge", "small supporting in-scene element")
    action_text = " ".join([fusion_plan.action_or_function, fusion_plan.duty_goal, fusion_plan.action_verb, fusion_plan.scene_binding]).lower()
    if any(term in action_text for term in decorative_terms) and fusion_plan.ip_duty_preset is not IPDutyPreset.BACKGROUND_SIGNATURE:
        findings.append(_error("decorative_ip_only", f"{frame_id}: IP duty is too decorative for an active-duty frame"))

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


__all__ = ["VisualStoryQualityFinding", "VisualStoryQualityGate"]
