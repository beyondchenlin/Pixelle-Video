from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.models.visual_role_planning import (
    VisualRoleCritique,
    VisualRoleIntegratedPromptPlan,
)
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import VisualRoleRequest
from pixelle_video.services.visual_role_image_prompt_compiler import (
    compile_visual_role_image_prompt,
)


class VisualRolePromptProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class VisualRolePromptProjector:
    renderer_id: str = "visual_role_prompt_projector"
    renderer_version: str = "v4_3_image_prompt_compiler"

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
                raise VisualRolePromptProjectionError(
                    "integrated_scene_prompt is required when visual role is enabled"
                )
            if not visual_role_critique.passed:
                raise VisualRolePromptProjectionError(
                    "integrated_scene_prompt did not pass critic: "
                    + ", ".join(issue.code for issue in visual_role_critique.issues)
                )

        positive_only = _is_positive_only(workflow, capabilities)
        identity_contract = visual_role_profile.identity_contract
        identity_guard_rules = (
            tuple(identity_contract.forbidden_identity_loss_rules)
            if visual_role_request.enabled
            else ()
        )
        compiled_prompt = compile_visual_role_image_prompt(
            base_visual_brief=base_visual_brief,
            visual_role_plan=visual_role_plan,
            visual_role_profile=visual_role_profile,
            visual_role_enabled=visual_role_request.enabled,
            positive_only=positive_only,
        )
        prompt_parts = dict(compiled_prompt.prompt_parts)
        prompt = compiled_prompt.prompt
        missing_traits = (
            _missing_required_traits(
                prompt,
                compiled_prompt.required_identity_traits,
            )
            if visual_role_request.enabled
            else ()
        )
        if missing_traits:
            raise VisualRolePromptProjectionError(
                "final prompt missing required_identity_traits: "
                + ", ".join(missing_traits)
            )

        all_negative_rules = tuple(_dedupe([*negative_rules, *identity_guard_rules]))
        negative_prompt = None if positive_only else _join_rules(all_negative_rules)
        projected_prompt_parts = {
            **prompt_parts,
            "projector_validation_passed": True,
            "positive_only_workflow": positive_only,
            "required_identity_traits": list(compiled_prompt.required_identity_traits),
        }
        contract = FinalVisualPromptContract(
            scene=prompt,
            composition=_join_non_empty(
                base_visual_brief.spatial_layout,
                base_visual_brief.camera_plan,
                base_visual_brief.composition_rules,
            )
            or "Complete image composition with the visual role participating in the scene.",
            style_assignment=prompt_parts.get("style_clause") or "Keep the original visual style and intent consistent.",
            character_layer_style=prompt_parts.get("role_clause")
            or "No visual role identity projection requested.",
            world_layer_style=visual_role_plan.transformed_scene_logic,
            integration_priority=(
                "The final prompt is compiled from structured visual-role plan fields and visible identity traits."
            ),
            negative_rules=all_negative_rules,
            metadata={
                "provider_prompt_projector": self.renderer_id,
                "visual_role_request": visual_role_request.to_dict(),
                "visual_role_profile": visual_role_profile.to_dict(),
                "visual_role_identity_contract": identity_contract.to_dict(),
                "visual_role_plan": visual_role_plan.to_dict(),
                "visual_role_critique": visual_role_critique.to_dict(),
                "projected_prompt_parts": projected_prompt_parts,
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
                "provider_prompt_mode": "image_facing_visual_role_prompt_compiler_v4_3",
                "visual_role_enabled": visual_role_request.enabled,
                "visual_role_critic_passed": visual_role_critique.passed,
                "visual_role_identity_contract": identity_contract.to_dict(),
                "projected_prompt_parts": projected_prompt_parts,
            },
        )


def _sanitize_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").split()).strip()


def _join_non_empty(*values: str) -> str:
    return "; ".join(str(value).strip() for value in values if str(value or "").strip())


def _join_prompt_parts(values: Sequence[str]) -> str:
    return "; ".join(str(value).strip() for value in values if str(value or "").strip())


def _join_rules(rules: Sequence[str]) -> str | None:
    normalized = _dedupe(rules)
    return ", ".join(normalized) if normalized else None


def _dedupe(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _missing_required_traits(
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


def _is_positive_only(workflow: str | None, capabilities: Any) -> bool:
    if capabilities is not None and getattr(capabilities, "supports_negative_prompt", True) is False:
        return True
    text = str(workflow or "").lower()
    return "z_image" in text or "z-image" in text


__all__ = ["VisualRolePromptProjectionError", "VisualRolePromptProjector"]
