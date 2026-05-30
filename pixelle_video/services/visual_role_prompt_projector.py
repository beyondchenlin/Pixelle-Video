from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import FinalVisualPromptContract, RenderedMediaPrompt
from pixelle_video.models.visual_role_planning import VisualRoleCritique, VisualRoleIntegratedPromptPlan
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest


class VisualRolePromptProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class VisualRolePromptProjector:
    renderer_id: str = "visual_role_prompt_projector"
    renderer_version: str = "v4_1_expression"

    def project(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        visual_role_plan: VisualRoleIntegratedPromptPlan,
        visual_role_critique: VisualRoleCritique,
        visual_role_request: VisualRoleRequest,
        visual_role_profile: VisualRoleProfile,
        negative_rules: Sequence[str] = (),
        capabilities: Any = None,
        workflow: str | None = None,
    ) -> RenderedMediaPrompt:
        if visual_role_request.enabled:
            if not visual_role_plan.integrated_scene_prompt.strip():
                raise VisualRolePromptProjectionError("integrated_scene_prompt is required when visual role is enabled")
            if not visual_role_critique.passed:
                raise VisualRolePromptProjectionError(
                    "integrated_scene_prompt did not pass critic: "
                    + ", ".join(issue.code for issue in visual_role_critique.issues)
                )

        prompt = _sanitize_prompt(visual_role_plan.integrated_scene_prompt)
        negative_prompt = None if _is_positive_only(workflow, capabilities) else _join_rules(negative_rules)
        contract = FinalVisualPromptContract(
            scene=prompt,
            composition=_join_non_empty(
                base_visual_brief.spatial_layout,
                base_visual_brief.camera_plan,
                base_visual_brief.composition_rules,
            )
            or "视觉角色参与画面表达的完整构图",
            style_assignment=base_visual_brief.style_surface or "画面风格与原始意图一致",
            character_layer_style=(
                f"{visual_role_profile.display_name}：{visual_role_plan.role_manifestation}，"
                f"动作职责：{visual_role_plan.role_action}"
            ),
            world_layer_style=visual_role_plan.transformed_scene_logic,
            integration_priority="最终 prompt 必须来自 integrated_scene_prompt，禁止静默回 base prompt",
            negative_rules=tuple(negative_rules),
            metadata={
                "provider_prompt_projector": self.renderer_id,
                "visual_role_request": visual_role_request.to_dict(),
                "visual_role_profile": visual_role_profile.to_dict(),
                "visual_role_plan": visual_role_plan.to_dict(),
                "visual_role_critique": visual_role_critique.to_dict(),
                "base_visual_brief_version": base_visual_brief.version,
                "workflow": workflow,
            },
        )
        return RenderedMediaPrompt(
            prompt=prompt,
            negative_prompt=negative_prompt,
            prompt_contract=contract,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            metadata={
                "provider_prompt_mode": "image_facing_visual_role_expression_v4_1",
                "visual_role_enabled": visual_role_request.enabled,
                "visual_role_critic_passed": visual_role_critique.passed,
            },
        )


def _sanitize_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").split()).strip()


def _join_non_empty(*values: str) -> str:
    return "，".join(str(value).strip() for value in values if str(value or "").strip())


def _join_rules(rules: Sequence[str]) -> str | None:
    normalized: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        text = str(rule or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return ", ".join(normalized) if normalized else None


def _is_positive_only(workflow: str | None, capabilities: Any) -> bool:
    if capabilities is not None and getattr(capabilities, "supports_negative_prompt", True) is False:
        return True
    text = str(workflow or "").lower()
    return "z_image" in text or "z-image" in text


__all__ = ["VisualRolePromptProjectionError", "VisualRolePromptProjector"]
