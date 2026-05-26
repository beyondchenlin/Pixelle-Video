from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle, IPStyleScope
from pixelle_video.models.final_visual_prompt_contract import FinalVisualPromptContract
from pixelle_video.models.visual_style_contract import (
    VisualLayerTarget,
    VisualRenderingStyle,
    VisualStyleLayer,
    VisualStyleLayerContract,
    default_mixed_style_world_contract,
)
from pixelle_video.services.source_subject_identity import source_subject_identity_prompt


@dataclass(frozen=True)
class FinalVisualPromptContractBuilder:
    def build(
        self,
        *,
        base_prompt: str,
        frame_context: Mapping[str, Any] | None = None,
        frame_plan: Any = None,
        ip_profile: IPProfile | None = None,
        ip_adaptation: Mapping[str, Any] | None = None,
        visual_style_contract: VisualStyleLayerContract | None = None,
        generation_world_profile: Any = None,
        world_preset: Mapping[str, Any] | None = None,
        extra_negative_rules: Sequence[str] | None = None,
    ) -> FinalVisualPromptContract:
        frame_context = frame_context or {}
        visual_style_contract = _effective_visual_style_contract(
            visual_style_contract,
            ip_profile=ip_profile,
        )
        ip_present = _ip_present(ip_adaptation)
        source_identity_hints = source_subject_identity_prompt(
            base_prompt=base_prompt,
            frame_context=frame_context,
            frame_plan=frame_plan,
            generation_world_profile=generation_world_profile,
        )

        scene = _sentence(
            base_prompt,
            _read_value(frame_context, "visual_goal"),
            _read_nested_value(frame_context, ("metadata", "focus_detail")),
            source_identity_hints,
        )
        composition = _sentence(
            _read_value(frame_context, "shot_type") or _read_value(frame_plan, "shot_type"),
            _read_value(frame_context, "shot_purpose") or _read_value(frame_plan, "shot_purpose"),
            "single unified image",
            "not a split-screen",
            "not a collage",
        )
        style_assignment = _style_assignment(
            visual_style_contract,
            ip_profile=ip_profile,
            ip_present=ip_present,
            frame_context=frame_context,
            frame_plan=frame_plan,
            source_identity_hints=source_identity_hints,
        )
        character_layer_style = _character_layer_style(
            visual_style_contract,
            ip_profile=ip_profile,
            ip_adaptation=ip_adaptation,
            ip_present=ip_present,
        )
        world_layer_style = _world_layer_style(
            visual_style_contract,
            frame_context=frame_context,
            generation_world_profile=generation_world_profile,
            world_preset=world_preset,
        )
        integration_priority = _integration_priority(visual_style_contract, ip_present=ip_present)
        negative_rules = _dedupe(
            [
                *visual_style_contract.negative_rules,
                *_read_sequence(ip_adaptation, "negative_constraints"),
                *(extra_negative_rules or ()),
            ]
        )
        return FinalVisualPromptContract(
            scene=scene or "visual scene matching the storyboard frame",
            composition=composition or "single unified image, readable composition",
            style_assignment=style_assignment,
            character_layer_style=character_layer_style,
            world_layer_style=world_layer_style,
            integration_priority=integration_priority,
            negative_rules=tuple(negative_rules),
            metadata={
                "ip_present": ip_present,
                "ip_profile_id": getattr(ip_profile, "ip_profile_id", None),
                "visual_style_contract_version": visual_style_contract.version,
            },
        )


def _effective_visual_style_contract(
    visual_style_contract: VisualStyleLayerContract | None,
    *,
    ip_profile: IPProfile | None,
) -> VisualStyleLayerContract:
    base = visual_style_contract or default_mixed_style_world_contract()
    if ip_profile is None:
        return base
    ip_contract = _ip_visual_style_contract(ip_profile)
    return base.merge(ip_contract)


def _ip_visual_style_contract(ip_profile: IPProfile) -> VisualStyleLayerContract:
    if ip_profile.rendering_style == IPRenderingStyle.STYLE_INHERITED:
        return VisualStyleLayerContract()
    rendering_style = VisualRenderingStyle(ip_profile.rendering_style.value)
    positive_rules = _dedupe(
        [
            ip_profile.visual_summary,
            *ip_profile.identity_lock,
            *ip_profile.minimal_traits,
            *ip_profile.identity_anchors,
            ip_profile.style_hint,
        ]
    )
    if rendering_style == VisualRenderingStyle.PHOTOREALISTIC_HUMAN:
        positive_rules.extend(
            [
                "realistic real human",
                "natural facial features",
                "realistic skin",
                "accurate anatomy",
                "realistic hands",
                "natural posture",
                "subtle clothing folds",
                "soft real-world lighting",
            ]
        )
    boundary_rules = list(ip_profile.style_boundary_rules)
    if ip_profile.exclusive_visual_layer:
        boundary_rules.append("only the IP character layer may use this rendering style")
    return VisualStyleLayerContract(
        layers=(
            VisualStyleLayer(
                layer_id=f"ip_{ip_profile.ip_profile_id}_style_layer",
                targets=(VisualLayerTarget.IP_CHARACTER, VisualLayerTarget.HUMAN_CHARACTER),
                rendering_style=rendering_style,
                positive_rules=tuple(_dedupe(positive_rules)),
                boundary_rules=tuple(_dedupe(boundary_rules)),
                exclusive=ip_profile.exclusive_visual_layer,
                priority=10,
                metadata={"style_scope": ip_profile.style_scope.value},
            ),
        ),
        negative_rules=tuple(_dedupe([*ip_profile.semantic_boundary, *ip_profile.negative_constraints])),
        metadata={"source": "ip_profile", "ip_profile_id": ip_profile.ip_profile_id},
    )


def _style_assignment(
    contract: VisualStyleLayerContract,
    *,
    ip_profile: IPProfile | None,
    ip_present: bool,
    frame_context: Mapping[str, Any] | None = None,
    frame_plan: Any = None,
    source_identity_hints: str = "",
) -> str:
    exclusive_photoreal_layers = [
        layer
        for layer in contract.layers
        if layer.exclusive and layer.rendering_style == VisualRenderingStyle.PHOTOREALISTIC_HUMAN
    ]
    source_subjects = _source_subjects_clause(frame_context or {}, frame_plan)
    source_subject_rule = (
        f"Source subjects remain the narrative focus: {source_subjects}. "
        "The IP character must not replace, merge with, cosplay, or transform into these source subjects. "
        if source_subjects
        else ""
    )
    source_identity_rule = (
        f"Keep source subjects visually distinct: {source_identity_hints}. "
        if source_identity_hints
        else ""
    )
    if ip_profile is not None and ip_present and exclusive_photoreal_layers:
        return (
            f"{source_subject_rule}"
            f"{source_identity_rule}"
            "The IP character belongs only to the character layer and is the only photorealistic element when its rendering style is photorealistic. "
            "All non-IP world elements, including source subjects, animals, teaching boards, books, tools, furniture, props, and background, must remain in their assigned world/source style."
        )
    return (
        f"{source_subject_rule}"
        f"{source_identity_rule}"
        "Apply visual styles by layer and target. The IP character may be a scene-integrated supporting role, but the source subjects remain the main content. "
        "Preserve clear boundaries between IP character layer, source subjects, world layer, props, and background."
    )


def _character_layer_style(
    contract: VisualStyleLayerContract,
    *,
    ip_profile: IPProfile | None,
    ip_adaptation: Mapping[str, Any] | None,
    ip_present: bool,
) -> str:
    if ip_profile is None or not ip_present:
        return "No dedicated IP character layer is present; preserve any characters from the scene without adding a new IP character."
    ip_layer_clause = contract.prompt_layer_clause(VisualLayerTarget.IP_CHARACTER, VisualLayerTarget.HUMAN_CHARACTER)
    appearance = _read_value(ip_adaptation, "appearance_description") or _read_value(ip_adaptation, "visual_identity")
    return _sentence(
        ip_layer_clause,
        appearance,
        "scene-integrated supporting character",
        "shares the same ground plane, scale, perspective, lighting, and atmosphere as the source scene",
        "has a concrete physical placement anchor in the scene, such as standing on the ground, sitting beside a screen, standing on a rooftop, leaning near a board, or staying at the edge of a crowd",
        "the IP body or feet visibly contact a ground plane, surface, object, rooftop, table edge, signboard, or another physical support",
        "if the source subject is flying, the IP remains grounded on a visible support unless the script explicitly says the IP is flying",
        "not isolated, not floating, not a sticker, not pasted on top",
        "coexists with the source subjects without replacing them",
    )


def _world_layer_style(
    contract: VisualStyleLayerContract,
    *,
    frame_context: Mapping[str, Any],
    generation_world_profile: Any,
    world_preset: Mapping[str, Any] | None,
) -> str:
    world_clause = contract.prompt_layer_clause(
        VisualLayerTarget.NON_IP_WORLD,
        VisualLayerTarget.ALL_NON_HUMAN,
        VisualLayerTarget.ANIMAL,
        VisualLayerTarget.PROP,
        VisualLayerTarget.ENVIRONMENT,
        VisualLayerTarget.TEXT_BOARD,
        VisualLayerTarget.BACKGROUND,
    )
    context_world_elements = ", ".join(_read_sequence(frame_context, "world_elements"))
    return _sentence(
        world_clause,
        _read_value(world_preset or {}, "style_core"),
        _read_value(generation_world_profile, "summary"),
        context_world_elements,
    ) or "Preserve the non-character environment as a coherent readable world layer."


def _integration_priority(contract: VisualStyleLayerContract, *, ip_present: bool) -> str:
    base = [
        *contract.integration_rules,
        "keep one coherent scene",
        "preserve style separation",
        "maintain calm, elegant, readable composition",
    ]
    if ip_present:
        base.extend(
            [
                "Priority 1: keep the character layer style intact",
                "Priority 2: keep all non-character elements in the world layer style",
                "Priority 3: make the mixed-style treatment feel intentional and harmonious",
            ]
        )
    return _sentence(*base)


def _ip_present(ip_adaptation: Mapping[str, Any] | None) -> bool:
    if not isinstance(ip_adaptation, Mapping):
        return False
    presence = str(ip_adaptation.get("ip_presence_type") or "").strip()
    role_slot = str(ip_adaptation.get("role_slot") or "").strip()
    return presence not in {"", "absent"} and role_slot != "absent"


def _read_value(container: Any, key: str, default: Any = "") -> Any:
    if container is None:
        return default
    if isinstance(container, Mapping):
        return container.get(key, default)
    return getattr(container, key, default)


def _read_nested_value(container: Any, path: Sequence[str]) -> Any:
    current = container
    for key in path:
        current = _read_value(current, key, None)
        if current is None:
            return None
    return current


def _read_sequence(container: Any, key: str) -> tuple[str, ...]:
    value = _read_value(container, key, ())
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _source_subjects_clause(frame_context: Mapping[str, Any], frame_plan: Any = None) -> str:
    values: list[str] = []
    for key in ("primary_subject", "secondary_subjects", "continuity_anchors"):
        values.extend(_read_sequence(frame_context, key))
    if not values:
        for key in ("primary_subject", "secondary_subjects", "continuity_anchors"):
            values.extend(_read_sequence(frame_plan, key))
    # Keep this concise for downstream image models. Do not use source_text here; it is often a full sentence.
    return "、".join(_dedupe(values[:4]))


def _sentence(*values: Any) -> str:
    return ", ".join(_dedupe(str(value).strip() for value in values if str(value or "").strip()))


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


__all__ = ["FinalVisualPromptContractBuilder"]
