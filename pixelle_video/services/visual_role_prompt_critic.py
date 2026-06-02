from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_role_planning import (
    VisualRoleCritique,
    VisualRoleIntegratedPromptPlan,
    VisualRolePromptIssue,
)
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.models.visual_role_strategy import VisualRoleMode
from pixelle_video.services.visual_role_primary_contract import (
    has_non_primary_subject_signal,
    has_primary_subject_signal,
)

_FORBIDDEN_TERMS = (
    "角标",
    "水印",
    "贴纸",
    "logo",
    "corner badge",
    "watermark",
    "sticker",
    "overlay",
    "UI overlay",
    "floating icon",
    "hidden",
    "suppressed",
    "fallback",
    "not suitable",
    "省略视觉角色",
)


@dataclass(frozen=True)
class VisualRolePromptCritic:
    llm_service: Any | None = None

    async def critique(
        self,
        *,
        plan: VisualRoleIntegratedPromptPlan,
        visual_role_profile: VisualRoleProfile,
        visual_role_request: VisualRoleRequest,
        base_visual_brief: BaseVisualBrief | None = None,
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> VisualRoleCritique:
        rule_critique = self.critique_rule(
            plan=plan,
            visual_role_profile=visual_role_profile,
            visual_role_request=visual_role_request,
            base_visual_brief=base_visual_brief,
        )
        if not rule_critique.passed or self.llm_service is None:
            return rule_critique
        try:
            llm_critique = await self.critique_llm(
                plan=plan,
                visual_role_profile=visual_role_profile,
                visual_role_request=visual_role_request,
                base_visual_brief=base_visual_brief,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
        except Exception as exc:
            return VisualRoleCritique(
                frame_id=plan.frame_id,
                issues=(
                    VisualRolePromptIssue(
                        code="llm_critic_unavailable",
                        severity="blocking",
                        message=str(exc),
                        repair_instruction="LLM critic failed; retry critique after rewriting integrated_scene_prompt.",
                    ),
                ),
                reviewer="llm_unavailable",
            )
        if not llm_critique.issues:
            return llm_critique
        return VisualRoleCritique(
            frame_id=plan.frame_id,
            issues=llm_critique.issues,
            reviewer="rule+llm",
        )

    def critique_rule(
        self,
        *,
        plan: VisualRoleIntegratedPromptPlan,
        visual_role_profile: VisualRoleProfile,
        visual_role_request: VisualRoleRequest,
        base_visual_brief: BaseVisualBrief | None = None,
    ) -> VisualRoleCritique:
        issues: list[VisualRolePromptIssue] = []
        prompt = plan.integrated_scene_prompt.strip()
        prompt_lower = prompt.lower()

        if not prompt:
            issues.append(_issue("integrated_prompt_empty", "integrated_scene_prompt 不能为空", "重写并输出完整 integrated_scene_prompt。"))
        if any(term.lower() in prompt_lower for term in _FORBIDDEN_TERMS):
            issues.append(_issue("forbidden_visual_form", "prompt 包含 forbidden visual form", "移除角标、水印、贴纸、logo、overlay、hidden、suppressed、fallback 等语义。"))
        missing_required_traits = _missing_required_identity_traits(
            prompt,
            visual_role_profile.identity_contract.required_identity_traits,
        )
        if missing_required_traits:
            issues.append(
                _issue(
                    "required_identity_trait_missing",
                    "prompt is missing required IP identity traits: "
                    + ", ".join(missing_required_traits),
                    "Rewrite integrated_scene_prompt so every required_identity_trait appears naturally in the scene responsibility.",
                )
            )
        if not _contains_identity(prompt, visual_role_profile.identity_kernel):
            issues.append(_issue("identity_kernel_missing", "prompt 未包含视觉角色身份核", "把 identity_kernel 自然写入画面职责中。"))
        if plan.role_mode is VisualRoleMode.SUBJECT_REPLACEMENT and not _looks_primary(plan, prompt):
            issues.append(_issue("subject_replacement_not_primary", "主体代替模式下视觉角色不是核心主体", "重写为视觉角色作为核心主体或主角。"))
        if plan.role_mode is VisualRoleMode.SUPPORTING_INTEGRATION:
            if base_visual_brief and base_visual_brief.main_subjects and not any(subject in prompt for subject in base_visual_brief.main_subjects):
                issues.append(_issue("supporting_mode_replaced_subject", "辅助融入模式下原主体未保留", "保留原主体，并让视觉角色承担辅助场景职责。"))
            if _looks_like_overlay_only(prompt):
                issues.append(_issue("overlay_like_visual_role", "视觉角色像 overlay / decoration", "把视觉角色改成真实场景内角色或载体，并说明其动作职责。"))
        if not plan.role_action and not plan.role_manifestation:
            issues.append(_issue("role_missing", "视觉角色缺少动作或呈现职责", "补充 role_action 或 role_manifestation。"))

        return VisualRoleCritique(frame_id=plan.frame_id, issues=tuple(issues), reviewer="rule")

    async def critique_llm(
        self,
        *,
        plan: VisualRoleIntegratedPromptPlan,
        visual_role_profile: VisualRoleProfile,
        visual_role_request: VisualRoleRequest,
        base_visual_brief: BaseVisualBrief | None = None,
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> VisualRoleCritique:
        prompt = _render_llm_critic_prompt(
            plan=plan,
            visual_role_profile=visual_role_profile,
            visual_role_request=visual_role_request,
            base_visual_brief=base_visual_brief,
        )
        response = await self.llm_service(
            prompt=prompt,
            response_type=dict,
            temperature=0.0,
            max_tokens=1200,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        return _critique_from_llm_payload(plan.frame_id, response)


def _issue(code: str, message: str, repair_instruction: str) -> VisualRolePromptIssue:
    return VisualRolePromptIssue(
        code=code,
        severity="blocking",
        message=message,
        repair_instruction=repair_instruction,
    )


def _contains_identity(prompt: str, identity_kernel: tuple[str, ...]) -> bool:
    lowered = prompt.lower()
    return any(token and token.lower() in lowered for token in identity_kernel)


def _missing_required_identity_traits(
    prompt: str,
    required_identity_traits: Sequence[str],
) -> tuple[str, ...]:
    lowered = prompt.lower()
    missing: list[str] = []
    for trait in required_identity_traits:
        text = str(trait or "").strip()
        if text and text.lower() not in lowered:
            missing.append(text)
    return tuple(missing)


def _looks_primary(plan: VisualRoleIntegratedPromptPlan, prompt: str) -> bool:
    return has_primary_subject_signal(
        plan.role_assignment,
        plan.role_location,
        prompt,
    ) and not has_non_primary_subject_signal(
        plan.role_assignment,
        plan.role_location,
        prompt,
    )


def _looks_like_overlay_only(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(token in lowered for token in ("corner", "watermark", "sticker", "overlay", "角标", "水印", "贴纸"))


def _render_llm_critic_prompt(
    *,
    plan: VisualRoleIntegratedPromptPlan,
    visual_role_profile: VisualRoleProfile,
    visual_role_request: VisualRoleRequest,
    base_visual_brief: BaseVisualBrief | None,
) -> str:
    payload = {
        "task": "Critique one visual-role integrated prompt and return JSON.",
        "questions": [
            "Does the prompt preserve original visual intent?",
            "Does the visual role participate in expression rather than decoration?",
            "Is the visual role naturally integrated?",
            "Does it match expression mode and role mode?",
        ],
        "expected_json": {
            "passed": True,
            "issues": [
                {
                    "code": "role_missing",
                    "severity": "blocking",
                    "message": "...",
                    "repair_instruction": "...",
                }
            ],
        },
        "base_visual_brief": base_visual_brief.to_dict() if base_visual_brief else None,
        "visual_role_request": visual_role_request.to_dict(),
        "visual_role_profile": visual_role_profile.to_dict(),
        "plan": plan.to_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _critique_from_llm_payload(frame_id: str, payload: Mapping[str, Any]) -> VisualRoleCritique:
    raw_issues = payload.get("issues") or []
    if bool(payload.get("passed", False)) and not raw_issues:
        return VisualRoleCritique(frame_id=frame_id, issues=tuple(), reviewer="llm")
    issues: list[VisualRolePromptIssue] = []
    if isinstance(raw_issues, Mapping):
        raw_issues = [raw_issues]
    if isinstance(raw_issues, Sequence) and not isinstance(raw_issues, (str, bytes, bytearray)):
        for raw in raw_issues:
            if not isinstance(raw, Mapping):
                continue
            issues.append(
                VisualRolePromptIssue(
                    code=str(raw.get("code") or "llm_semantic_issue"),
                    severity="blocking" if str(raw.get("severity") or "blocking") == "blocking" else "warning",
                    message=str(raw.get("message") or "LLM critic rejected prompt"),
                    repair_instruction=str(raw.get("repair_instruction") or "Rewrite integrated_scene_prompt."),
                )
            )
    if not issues and not bool(payload.get("passed", False)):
        issues.append(_issue("llm_semantic_issue", "LLM critic rejected prompt", "重写 integrated_scene_prompt。"))
    return VisualRoleCritique(frame_id=frame_id, issues=tuple(issues), reviewer="llm")


__all__ = ["VisualRolePromptCritic"]
