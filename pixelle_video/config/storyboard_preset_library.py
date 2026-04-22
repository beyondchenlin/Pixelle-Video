"""Built-in storyboard world and shot preset libraries."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from pixelle_video.models.storyboard_planning import (
    ShotPresetDefinition,
    WorldPresetDefinition,
)


def _read_value(container: Any, key: str, default: Any = None) -> Any:
    if isinstance(container, Mapping):
        return container.get(key, default)
    return getattr(container, key, default)


NEUTRAL_KNOWLEDGE_WORLD_PRESET = WorldPresetDefinition(
    preset_id="neutral_knowledge_storyboard",
    display_name="Neutral Knowledge Storyboard",
    display_name_key="storyboard.preset.world.neutral_knowledge_storyboard.name",
    description_key="storyboard.preset.world.neutral_knowledge_storyboard.description",
    supported_modes=("theme_mapping", "concept_explainer"),
    style_core="neutral educational world language with calm framing and readable structure",
    world_elements=(
        "clean teaching board",
        "stable reference props",
        "simple classroom or lab staging",
    ),
    knowledge_scene_rules=(
        "keep knowledge meaning first",
        "prefer clear teaching props over decorative clutter",
    ),
    negative_rules=(
        "avoid strong branded world cues",
        "avoid aggressive cinematic over-styling",
    ),
    default_shot_preset_ids=("balanced_explainer", "detail_focus"),
    cast_slots_by_mode={
        "theme_mapping": (
            {
                "slot_id": "mapped_subject_lead",
                "semantic_role": "mapped_subject_lead",
                "visual_anchor": "central figure with clear subject focus",
                "prop_anchor": "reference board or canon prop",
                "personality_anchor": "steady, readable, grounded",
                "theme_mapping_rule": "map canonical entities into the lead knowledge role",
                "reuse_priority": 90,
            },
            {
                "slot_id": "mapped_context_support",
                "semantic_role": "mapped_context_support",
                "visual_anchor": "secondary guide or comparison element",
                "prop_anchor": "supporting chart or context prop",
                "personality_anchor": "calm and explanatory",
                "theme_mapping_rule": "map context, comparison, or faction support roles",
                "reuse_priority": 70,
            },
        ),
        "concept_explainer": (
            {
                "slot_id": "host_explainer",
                "semantic_role": "host_explainer",
                "visual_anchor": "stable presenter with clear gesture language",
                "prop_anchor": "pointer, board, or teaching prop",
                "personality_anchor": "friendly, precise, and reassuring",
                "theme_mapping_rule": "keep the explainer identity stable across concept topics",
                "reuse_priority": 95,
            },
            {
                "slot_id": "learner_support",
                "semantic_role": "learner_support",
                "visual_anchor": "listener, helper, or demonstrator",
                "prop_anchor": "notebook, sample object, or comparison card",
                "personality_anchor": "curious and receptive",
                "theme_mapping_rule": "anchor the concept with a supporting learning role",
                "reuse_priority": 75,
            },
        ),
    },
    conservative_fallback_mode="concept_explainer",
    safe_default=True,
)


DUAL_MODE_WORLD_PRESET = WorldPresetDefinition(
    preset_id="dual_mode_storyboard",
    display_name="Dual Mode Storyboard",
    display_name_key="storyboard.preset.world.dual_mode_storyboard.name",
    description_key="storyboard.preset.world.dual_mode_storyboard.description",
    supported_modes=("theme_mapping", "concept_explainer"),
    style_core="adaptable storyboard world with stable teaching grammar",
    world_elements=(
        "comparison board",
        "repeatable teaching props",
        "clear world landmarks",
    ),
    knowledge_scene_rules=(
        "preserve the educational subject",
        "keep the world language stable across scenes",
    ),
    negative_rules=(
        "avoid noisy universe shifts",
        "avoid decorative elements that compete with the subject",
    ),
    default_shot_preset_ids=("balanced_explainer", "detail_focus"),
    cast_slots_by_mode={
        "theme_mapping": (
            {
                "slot_id": "theme_lead",
                "semantic_role": "theme_lead",
                "visual_anchor": "mapped protagonist or source entity",
                "prop_anchor": "theme-specific anchor prop",
                "personality_anchor": "confident and clear",
                "theme_mapping_rule": "map the main canonical entity into the lead slot",
                "reuse_priority": 88,
            },
        ),
        "concept_explainer": (
            {
                "slot_id": "explain_lead",
                "semantic_role": "explain_lead",
                "visual_anchor": "stable explainer host",
                "prop_anchor": "diagram board or demo object",
                "personality_anchor": "patient and didactic",
                "theme_mapping_rule": "keep a stable explainer lead for concept-only topics",
                "reuse_priority": 92,
            },
        ),
    },
    conservative_fallback_mode="concept_explainer",
)


BUILTIN_WORLD_PRESETS = (
    NEUTRAL_KNOWLEDGE_WORLD_PRESET,
    DUAL_MODE_WORLD_PRESET,
)


BALANCED_EXPLAINER_SHOT_PRESET = ShotPresetDefinition(
    preset_id="balanced_explainer",
    display_name="Balanced Explainer",
    display_name_key="storyboard.preset.shot.balanced_explainer.name",
    description_key="storyboard.preset.shot.balanced_explainer.description",
    supported_scene_count=(3, 4, 5, 6, 7),
    max_consecutive_same=2,
    shot_distribution_rules=(
        "keep at least three distinct shot distances when scene count allows it",
        "avoid more than two consecutive frames of the same shot type",
    ),
    opening_rules=(
        "establish the subject or world clearly in the opening frame",
    ),
    closing_rules=(
        "close on a clear knowledge takeaway or summary beat",
    ),
    transition_rules=(
        "alternate wider and tighter frames when the flow supports it",
    ),
    purpose_bias="balanced educational pacing with both context and detail support",
    override_policy="adaptive",
)


DETAIL_FOCUS_SHOT_PRESET = ShotPresetDefinition(
    preset_id="detail_focus",
    display_name="Detail Focus",
    display_name_key="storyboard.preset.shot.detail_focus.name",
    description_key="storyboard.preset.shot.detail_focus.description",
    supported_scene_count=(3, 4, 5, 6),
    max_consecutive_same=1,
    shot_distribution_rules=(
        "prioritize detail clarity and close reading of key elements",
    ),
    opening_rules=(
        "open with a clear subject or contextual close framing",
    ),
    closing_rules=(
        "end with the most important detail or takeaway element",
    ),
    transition_rules=(
        "move from context to detail with controlled shot tightening",
    ),
    purpose_bias="knowledge detail emphasis and visual emphasis on important cues",
    override_policy="strict",
)


BUILTIN_SHOT_PRESETS = (
    BALANCED_EXPLAINER_SHOT_PRESET,
    DETAIL_FOCUS_SHOT_PRESET,
)


def build_builtin_world_preset_library_dict() -> dict[str, Any]:
    return {
        "default_world_preset_id": NEUTRAL_KNOWLEDGE_WORLD_PRESET.preset_id,
        "items": [preset.to_dict() for preset in BUILTIN_WORLD_PRESETS],
    }


def build_builtin_shot_preset_library_dict() -> dict[str, Any]:
    return {
        "default_shot_preset_id": BALANCED_EXPLAINER_SHOT_PRESET.preset_id,
        "items": [preset.to_dict() for preset in BUILTIN_SHOT_PRESETS],
    }


def lookup_world_preset(library: Any, preset_id: Optional[str] = None) -> dict[str, Any]:
    items = _read_value(library, "items", [])
    default_preset_id = _read_value(library, "default_world_preset_id", None)
    target_preset_id = (preset_id or default_preset_id or "").strip() or None

    if target_preset_id is None:
        raise ValueError("world preset library does not define a default preset id")

    for item in items:
        item_preset_id = _read_value(item, "preset_id", None)
        if item_preset_id == target_preset_id:
            return item if isinstance(item, dict) else item.model_dump()

    raise ValueError(f"unknown world preset id: {target_preset_id}")


def load_shot_preset_map(library: Any) -> dict[str, dict[str, Any]]:
    items = _read_value(library, "items", [])
    shot_map: dict[str, dict[str, Any]] = {}
    for item in items:
        preset_id = _read_value(item, "preset_id", None)
        if not isinstance(preset_id, str) or not preset_id.strip():
            raise ValueError("malformed storyboard shot preset item: missing preset_id")
        shot_map[preset_id] = item if isinstance(item, dict) else item.model_dump()
    return shot_map


__all__ = [
    "BALANCED_EXPLAINER_SHOT_PRESET",
    "BUILTIN_SHOT_PRESETS",
    "BUILTIN_WORLD_PRESETS",
    "DETAIL_FOCUS_SHOT_PRESET",
    "NEUTRAL_KNOWLEDGE_WORLD_PRESET",
    "build_builtin_shot_preset_library_dict",
    "build_builtin_world_preset_library_dict",
    "load_shot_preset_map",
    "lookup_world_preset",
]
