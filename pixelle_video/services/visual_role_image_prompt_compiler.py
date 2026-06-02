from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_role_planning import VisualRoleIntegratedPromptPlan
from pixelle_video.models.visual_role_profile import VisualRoleProfile

_INTERNAL_PROMPT_TOKENS = (
    "Fixed IP identity",
    "required identity traits",
    "Identity kernel",
    "Scene responsibility",
    "Identity protection rules",
    "action responsibility",
    "identity_contract",
    "identity contract",
    "non-IP world layer",
    "non-IP animals",
    "non-IP",
    "forbidden_identity_loss_rules",
)


@dataclass(frozen=True)
class CompiledVisualRoleImagePrompt:
    prompt: str
    prompt_parts: Mapping[str, str]
    required_identity_traits: tuple[str, ...]


def compile_visual_role_image_prompt(
    *,
    base_visual_brief: BaseVisualBrief,
    visual_role_plan: VisualRoleIntegratedPromptPlan,
    visual_role_profile: VisualRoleProfile,
    visual_role_enabled: bool,
    positive_only: bool,
) -> CompiledVisualRoleImagePrompt:
    scene_clause = _scene_clause(
        base_visual_brief=base_visual_brief,
        visual_role_plan=visual_role_plan,
        visual_role_enabled=visual_role_enabled,
    )
    role_clause = (
        _role_clause(
            visual_role_plan=visual_role_plan,
            visual_role_profile=visual_role_profile,
            existing_scene_text=scene_clause,
            positive_only=positive_only,
        )
        if visual_role_enabled
        else ""
    )
    style_clause = _image_facing_style_surface(
        base_visual_brief.style_surface,
        base_prompt=base_visual_brief.base_image_prompt,
    )
    readability_clause = _join_non_empty(*base_visual_brief.readability_constraints)
    prompt_parts = {
        "scene_clause": scene_clause,
        "role_clause": role_clause,
        "style_clause": style_clause,
        "readability_clause": readability_clause,
    }
    prompt = _sanitize_prompt(_join_non_empty(*prompt_parts.values()))
    return CompiledVisualRoleImagePrompt(
        prompt=prompt,
        prompt_parts=prompt_parts,
        required_identity_traits=_required_traits_for_validation(visual_role_profile),
    )


def _scene_clause(
    *,
    base_visual_brief: BaseVisualBrief,
    visual_role_plan: VisualRoleIntegratedPromptPlan,
    visual_role_enabled: bool,
) -> str:
    candidates = (
        visual_role_plan.integrated_scene_prompt if visual_role_enabled else "",
        base_visual_brief.base_image_prompt,
        visual_role_plan.original_intent_summary,
        base_visual_brief.visual_moment,
        base_visual_brief.core_message,
    )
    for candidate in candidates:
        cleaned = _remove_internal_contract_fragments(candidate)
        if cleaned:
            return cleaned
    return ""


def _role_clause(
    *,
    visual_role_plan: VisualRoleIntegratedPromptPlan,
    visual_role_profile: VisualRoleProfile,
    existing_scene_text: str,
    positive_only: bool,
) -> str:
    name = _identity_name(visual_role_profile)
    identity_traits = _identity_traits_for_prompt(visual_role_profile)
    missing_traits = _missing_terms(existing_scene_text, identity_traits)
    appearance = _join_non_empty(*missing_traits)
    role_details = _join_non_empty(
        visual_role_plan.role_manifestation,
        visual_role_plan.role_location,
        visual_role_plan.role_action,
    )
    if appearance:
        role_text = f"{name} appears as a real in-scene participant with {appearance}; {role_details}"
    else:
        role_text = f"{name} appears as a real in-scene participant; {role_details}"
    if positive_only:
        role_text = _join_non_empty(
            role_text,
            "the visual role is physically integrated into the scene with its identity traits visible",
        )
    return _sanitize_prompt(role_text)


def _identity_name(profile: VisualRoleProfile) -> str:
    return profile.display_name or profile.identity_contract.canonical_identity_name


def _identity_traits_for_prompt(profile: VisualRoleProfile) -> tuple[str, ...]:
    name = _identity_name(profile).lower()
    traits = _dedupe(
        [
            *profile.identity_contract.required_identity_traits,
            *profile.identity_contract.important_identity_traits,
        ]
    )
    filtered: list[str] = []
    for trait in traits:
        text = str(trait or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered == name or lowered in name:
            continue
        if any(lowered in kept.lower() for kept in filtered):
            continue
        filtered = [kept for kept in filtered if kept.lower() not in lowered]
        filtered.append(text)
    return tuple(filtered)


def _required_traits_for_validation(profile: VisualRoleProfile) -> tuple[str, ...]:
    name = _identity_name(profile).lower()
    required = _dedupe(profile.identity_contract.required_identity_traits)
    validation_terms: list[str] = []
    for trait in required:
        text = str(trait or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered == name or lowered in name:
            continue
        if any(lowered in kept.lower() for kept in validation_terms):
            continue
        validation_terms = [kept for kept in validation_terms if kept.lower() not in lowered]
        validation_terms.append(text)
    return tuple(validation_terms)


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
            "线条",
            "扁平",
        )
    ):
        clauses.append(
            "flat monochrome illustration with clean line art, simple background, subtle tonal contrast"
        )
    elif any(token in text for token in ("storybook", "hand-painted", "插画", "绘本")):
        clauses.append("soft illustration style with natural light and clear composition")

    if any(token in text for token in ("minimal", "negative space", "简洁", "留白")):
        clauses.append("generous negative space and low-detail background")

    if clauses:
        return _join_non_empty(*clauses)

    cleaned = _remove_internal_contract_fragments(style_surface)
    return cleaned if cleaned != style_surface or cleaned else ""


def _remove_internal_contract_fragments(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not _contains_internal_token(text):
        return text

    segments = re.split(r"([。；;.!?！？])", text)
    kept: list[str] = []
    index = 0
    while index < len(segments):
        segment = segments[index]
        punct = segments[index + 1] if index + 1 < len(segments) else ""
        combined = segment + punct
        if combined.strip() and not _contains_internal_token(combined):
            kept.append(combined)
        index += 2
    cleaned = "".join(kept).strip()
    if cleaned:
        return cleaned

    cleaned = text
    for token in _INTERNAL_PROMPT_TOKENS:
        cleaned = re.sub(re.escape(token), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ;,，。")
    return cleaned


def _contains_internal_token(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(token.lower() in lowered for token in _INTERNAL_PROMPT_TOKENS)


def _missing_terms(text: str, terms: Sequence[str]) -> tuple[str, ...]:
    lowered = str(text or "").lower()
    missing: list[str] = []
    for term in terms:
        value = str(term or "").strip()
        if value and value.lower() not in lowered:
            missing.append(value)
    return tuple(missing)


def _sanitize_prompt(prompt: str) -> str:
    return " ".join(str(prompt or "").split()).strip()


def _join_non_empty(*values: str) -> str:
    return "; ".join(_dedupe(str(value).strip() for value in values if str(value or "").strip()))


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


__all__ = ["CompiledVisualRoleImagePrompt", "compile_visual_role_image_prompt"]
