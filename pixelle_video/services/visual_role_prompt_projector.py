from __future__ import annotations

import re
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

_INTERNAL_MODE_TOKENS = (
    "explanatory_diagram",
    "infographic_layout",
    "cognitive_metaphor",
    "environment_branding",
    "supporting_integration",
    "subject_replacement",
    "structure_mode",
    "participation_mode",
    "in-scene responsibility",
    "辅助视觉角色",
    "视觉角色出现",
    "必须以真实场景内角色",
    "真实场景内角色或载体",
)


class VisualRolePromptProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class VisualRolePromptProjector:
    renderer_id: str = "visual_role_prompt_projector"
    renderer_version: str = "v4_3_image_facing_identity_contract"

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
        image_facing_scene = _image_facing_scene_clause(
            visual_role_plan.integrated_scene_prompt,
            identity_contract=identity_contract,
            style_surface=base_visual_brief.style_surface,
        )
        identity_presence_clause = _identity_presence_clause(
            display_name=visual_role_profile.display_name,
            required_traits=identity_contract.required_identity_traits,
            context_text=image_facing_scene,
        )
        participation_clause = _participation_clause(
            display_name=visual_role_profile.display_name,
            role_manifestation=visual_role_plan.role_manifestation,
            role_action=visual_role_plan.role_action,
            context_text=image_facing_scene,
        )
        style_clause = _image_facing_style_surface(
            base_visual_brief.style_surface,
            base_prompt=image_facing_scene or base_visual_brief.base_image_prompt,
        ) or "Keep the original visual style and intent consistent."
        identity_guard_clause = (
            _positive_identity_guard_clause(identity_guard_rules, context_text=image_facing_scene)
            if positive_only
            else ""
        )
        prompt_parts = {
            "identity_contract_clause": identity_presence_clause if visual_role_request.enabled else "",
            "content_structure_clause": image_facing_scene,
            "participation_clause": participation_clause if visual_role_request.enabled else "",
            "style_clause": style_clause,
            "negative_guard_clause": identity_guard_clause,
        }
        prompt = _sanitize_prompt(_join_prompt_parts(prompt_parts.values()))
        missing_traits = (
            _missing_required_traits(
                prompt,
                identity_contract.required_identity_traits,
                identity_name=visual_role_profile.display_name
                or identity_contract.canonical_identity_name,
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
            "required_identity_traits": list(identity_contract.required_identity_traits),
        }
        contract = FinalVisualPromptContract(
            scene=prompt,
            composition=_join_non_empty(
                base_visual_brief.spatial_layout,
                base_visual_brief.camera_plan,
                base_visual_brief.composition_rules,
            )
            or "Complete image composition with the visual role participating in the scene.",
            style_assignment=prompt_parts["style_clause"],
            character_layer_style=prompt_parts["participation_clause"]
            or "No visual role identity projection requested.",
            world_layer_style=visual_role_plan.transformed_scene_logic,
            integration_priority=(
                "The final prompt must be projected from integrated_scene_prompt and the identity contract."
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
                "provider_prompt_mode": "image_facing_visual_role_identity_contract_v4_2",
                "visual_role_enabled": visual_role_request.enabled,
                "visual_role_critic_passed": visual_role_critique.passed,
                "visual_role_identity_contract": identity_contract.to_dict(),
                "projected_prompt_parts": projected_prompt_parts,
            },
        )


def _sanitize_prompt(prompt: str) -> str:
    cleaned = " ".join(str(prompt or "").split()).strip()
    cleaned = _dedupe_prompt_clauses(cleaned)
    cleaned = _remove_empty_punctuation(cleaned)
    return cleaned


def _join_non_empty(*values: str) -> str:
    return "; ".join(_dedupe(str(value).strip() for value in values if str(value or "").strip()))


def _join_prompt_parts(values: Sequence[str]) -> str:
    return "; ".join(_dedupe(str(value).strip() for value in values if str(value or "").strip()))


def _identity_guard_clause(rules: Sequence[str]) -> str:
    if not rules:
        return ""
    return "Identity protection rules: " + "; ".join(_dedupe(rules))


def _image_facing_scene_clause(
    prompt: str,
    *,
    identity_contract: Any,
    style_surface: str,
) -> str:
    cleaned = str(prompt or "").strip()
    fixed_clause = str(getattr(identity_contract, "fixed_identity_clause", "") or "").strip()
    if fixed_clause:
        cleaned = cleaned.replace(fixed_clause, "")
    if style_surface:
        cleaned = cleaned.replace(str(style_surface).strip(), "")
    cleaned = re.sub(
        r"Fixed IP identity\s*:\s*[^.;；。]*[.;；。]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"required identity traits\s*:\s*[^.;；。]*[.;；。]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"Identity protection rules\s*:\s*.*?(?=$|[。；])",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"Identity kernel\s*:\s*[^.;；。]*[.;；。]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"Scene responsibility\s*:\s*[^.;；。]*[.;；。]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bnon[- ]?IP\b[^.;；。]*[.;；。]?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _replace_internal_terms(cleaned)
    cleaned = _remove_clauses_with_internal_tokens(cleaned)
    cleaned = _remove_identity_trait_only_clauses(
        cleaned,
        getattr(identity_contract, "required_identity_traits", ()),
    )
    return _sanitize_prompt(cleaned)


def _identity_presence_clause(
    *,
    display_name: str,
    required_traits: Sequence[str],
    context_text: str,
) -> str:
    name = str(display_name or "").strip()
    if not name:
        return ""
    traits = _identity_traits_without_name(name, required_traits)
    if _contains_cjk(f"{name} {context_text}"):
        if traits:
            return f"固定视觉角色{name}以真实场景内角色出现，保留{_join_list_for_prompt(traits)}。"
        return f"固定视觉角色{name}以真实场景内角色出现。"
    if traits:
        return f"{name} appears as a real in-scene role with {_join_list_for_prompt(traits)}."
    return f"{name} appears as a real in-scene role."


def _participation_clause(
    *,
    display_name: str,
    role_manifestation: str,
    role_action: str,
    context_text: str,
) -> str:
    name = str(display_name or "").strip()
    manifestation = _replace_internal_terms(str(role_manifestation or "").strip())
    action = _replace_internal_terms(str(role_action or "").strip())
    if not name:
        return ""
    if _contains_cjk(f"{name} {manifestation} {action} {context_text}"):
        parts = []
        if manifestation and manifestation not in context_text:
            parts.append(manifestation)
        if action and action not in context_text:
            parts.append(f"承担{action}职责")
        if not parts:
            return ""
        return f"{name}{'，'.join(parts)}。"
    parts = []
    if manifestation and manifestation not in context_text:
        parts.append(manifestation)
    if action and action not in context_text:
        parts.append(f"responsible for {action}")
    if not parts:
        return ""
    return f"{name}: {', '.join(parts)}."


def _positive_identity_guard_clause(rules: Sequence[str], *, context_text: str) -> str:
    if not rules:
        return ""
    return ""


def _image_facing_style_surface(style_surface: str, *, base_prompt: str = "") -> str:
    text = f"{style_surface or ''} {base_prompt or ''}".lower()
    clauses: list[str] = []
    if any(
        token in text
        for token in (
            "flat monochrome",
            "monochrome",
            "black-and-white",
            "line art",
            "minimal line",
            "黑白",
            "单色",
            "灰",
            "线条",
            "扁平",
        )
    ):
        clauses.append("黑白灰扁平插画，线条简洁，二维无纹理，背景简洁")
    elif any(token in text for token in ("storybook", "hand-painted", "illustration", "插画", "绘本")):
        clauses.append("柔和插画风格，构图清晰")
    if any(token in text for token in ("minimal", "negative space", "minimalistic", "简洁", "留白")):
        clauses.append("画面保留留白，避免杂乱细节")
    return "；".join(_dedupe(clauses))


def _replace_internal_terms(text: str) -> str:
    cleaned = str(text or "")
    replacements = {
        "action responsibility": "role action",
        "non-IP world layer": "background",
        "non-IP animals": "background animals",
        "non-IP": "background",
        "visual role": "scene role",
        "IP character": "fixed character",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\brole_slot\b|\bsemantic_role\b|\bworld layer\b|\bcharacter layer\b", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _remove_clauses_with_internal_tokens(text: str) -> str:
    raw_parts = re.split(r"([;；。])", str(text or ""))
    kept: list[str] = []
    index = 0
    while index < len(raw_parts):
        clause = raw_parts[index]
        separator = raw_parts[index + 1] if index + 1 < len(raw_parts) else ""
        index += 2
        lowered = clause.lower()
        if any(token in lowered for token in _INTERNAL_MODE_TOKENS):
            continue
        kept.append(clause + separator)
    return "".join(kept).strip()


def _remove_identity_trait_only_clauses(text: str, required_traits: Sequence[str]) -> str:
    trait_keys = {
        _normalize_identity_text(trait)
        for trait in required_traits
        if str(trait or "").strip()
    }
    if not trait_keys:
        return str(text or "").strip()
    raw_parts = re.split(r"([;；。])", str(text or ""))
    kept: list[str] = []
    index = 0
    while index < len(raw_parts):
        clause = raw_parts[index]
        separator = raw_parts[index + 1] if index + 1 < len(raw_parts) else ""
        index += 2
        key = _normalize_identity_text(clause)
        key_without_leading_verb = key.removeprefix("让")
        if key in trait_keys or key_without_leading_verb in trait_keys:
            continue
        kept.append(clause + separator)
    return "".join(kept).strip()


def _identity_traits_without_name(name: str, traits: Sequence[str]) -> tuple[str, ...]:
    normalized_name = _normalize_identity_text(name)
    result: list[str] = []
    for trait in traits:
        text = str(trait or "").strip()
        if not text:
            continue
        key = _normalize_identity_text(text)
        if key and (
            key == normalized_name
            or key in normalized_name
            or _trait_redundant_with_name(normalized_name, key)
        ):
            continue
        result.append(text)
    return tuple(_drop_subsumed_traits(_dedupe(result)))


def _trait_redundant_with_name(normalized_name: str, normalized_trait: str) -> bool:
    if not normalized_name or not normalized_trait:
        return False
    if normalized_trait.endswith("子") and normalized_trait[:-1] in normalized_name:
        return True
    return False


def _drop_subsumed_traits(traits: Sequence[str]) -> list[str]:
    normalized = [(trait, _normalize_identity_text(trait)) for trait in traits]
    result: list[str] = []
    for trait, key in normalized:
        if any(key != other_key and key in other_key for _, other_key in normalized):
            continue
        result.append(trait)
    return result


def _normalize_identity_text(text: str) -> str:
    return re.sub(r"[\s,.;；。:：，、]+", "", str(text or "").lower())


def _join_list_for_prompt(values: Sequence[str]) -> str:
    return "、".join(_dedupe(str(value).strip() for value in values if str(value).strip()))


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def _dedupe_prompt_clauses(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    raw_parts = re.split(r"([;；。])", text)
    clauses: list[str] = []
    seen: set[str] = set()
    index = 0
    while index < len(raw_parts):
        clause = raw_parts[index].strip()
        separator = raw_parts[index + 1] if index + 1 < len(raw_parts) else ""
        index += 2
        if not clause:
            continue
        key = _normalize_clause_key(clause)
        if key in seen:
            continue
        seen.add(key)
        clauses.append(clause + (separator if separator in {"；", "。"} else "；"))
    return "".join(clauses).rstrip("；; ")


def _normalize_clause_key(text: str) -> str:
    lowered = str(text or "").lower()
    lowered = re.sub(r"\b(flat\s+)?monochrome\s+illustration\b", "monochrome illustration", lowered)
    lowered = re.sub(r"[\s,.;；。:：，、]+", "", lowered)
    return lowered


def _remove_empty_punctuation(text: str) -> str:
    cleaned = re.sub(r"\s*([;；。])\s*", r"\1", str(text or ""))
    cleaned = re.sub(r"[;；。]{2,}", "；", cleaned)
    cleaned = cleaned.strip(" ;；。")
    return cleaned


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
    *,
    identity_name: str = "",
) -> tuple[str, ...]:
    lowered = prompt.lower()
    prompt_key = _normalize_identity_text(prompt)
    name_key = _normalize_identity_text(identity_name)
    missing: list[str] = []
    for trait in required_identity_traits:
        text = str(trait or "").strip()
        if not text or text.lower() in lowered:
            continue
        trait_key = _normalize_identity_text(text)
        if (
            trait_key
            and name_key
            and name_key in prompt_key
            and _trait_redundant_with_name(name_key, trait_key)
        ):
            continue
        if text:
            missing.append(text)
    return tuple(missing)


def _is_positive_only(workflow: str | None, capabilities: Any) -> bool:
    if capabilities is not None and getattr(capabilities, "supports_negative_prompt", True) is False:
        return True
    text = str(workflow or "").lower()
    return "z_image" in text or "z-image" in text


__all__ = ["VisualRolePromptProjectionError", "VisualRolePromptProjector"]
