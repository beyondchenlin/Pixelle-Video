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
    display_name="Clean Classroom",
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
    display_name="Flexible Narrative Space",
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


ANGRY_BIRDS_THREE_KINGDOMS_WORLD_PRESET = WorldPresetDefinition(
    preset_id="angry_birds_three_kingdoms",
    display_name="Three Kingdoms · Faction Theater",
    display_name_key="storyboard.preset.world.angry_birds_three_kingdoms.name",
    description_key="storyboard.preset.world.angry_birds_three_kingdoms.description",
    supported_modes=("theme_mapping",),
    style_core="Angry Birds-inspired teaching world with Three Kingdoms faction cues and stable role silhouettes",
    world_elements=(
        "faction banners",
        "strategy board",
        "war maps",
        "camp structures",
        "study scrolls",
    ),
    knowledge_scene_rules=(
        "keep role mapping and relationship readability ahead of spectacle",
        "preserve a playful classroom-like teaching tone for historical themes",
    ),
    negative_rules=(
        "avoid realistic war violence",
        "avoid drifting into game screenshot framing",
    ),
    default_shot_preset_ids=("character_relationship", "opening_world_building", "balanced_explainer"),
    cast_slots=(
        {
            "slot_id": "shu_leader",
            "semantic_role": "shu_leader",
            "visual_anchor": "warm-toned leader bird",
            "prop_anchor": "banner or oath scroll",
            "personality_anchor": "benevolent and steady",
            "theme_mapping_rule": "map Shu leadership figures into this slot",
            "reuse_priority": 95,
        },
        {
            "slot_id": "wei_leader",
            "semantic_role": "wei_leader",
            "visual_anchor": "cool-toned command bird",
            "prop_anchor": "command tablet or banner",
            "personality_anchor": "strategic and forceful",
            "theme_mapping_rule": "map Wei leadership figures into this slot",
            "reuse_priority": 94,
        },
        {
            "slot_id": "strategist",
            "semantic_role": "strategist",
            "visual_anchor": "clever adviser bird",
            "prop_anchor": "war map or fan",
            "personality_anchor": "calm and analytical",
            "theme_mapping_rule": "map tacticians and planners into this slot",
            "reuse_priority": 92,
        },
        {
            "slot_id": "warrior_support",
            "semantic_role": "warrior_support",
            "visual_anchor": "strong support bird",
            "prop_anchor": "weapon prop or shield marker",
            "personality_anchor": "loyal and energetic",
            "theme_mapping_rule": "map martial support roles into this slot",
            "reuse_priority": 88,
        },
        {
            "slot_id": "learner_observer",
            "semantic_role": "learner_observer",
            "visual_anchor": "curious observer bird",
            "prop_anchor": "notes or study card",
            "personality_anchor": "curious and attentive",
            "theme_mapping_rule": "use as the audience-surrogate learner slot",
            "reuse_priority": 80,
        },
    ),
    conservative_fallback_mode="theme_mapping",
    forced_mode="theme_mapping",
)


ANGRY_BIRDS_KNOWLEDGE_CLASSROOM_WORLD_PRESET = WorldPresetDefinition(
    preset_id="angry_birds_knowledge_classroom",
    display_name="Playful Classroom",
    display_name_key="storyboard.preset.world.angry_birds_knowledge_classroom.name",
    description_key="storyboard.preset.world.angry_birds_knowledge_classroom.description",
    supported_modes=("concept_explainer",),
    style_core="playful bird classroom with readable teaching props and repeatable presenter staging",
    world_elements=(
        "teaching board",
        "pointer",
        "labeled sample objects",
        "charts",
        "demo table",
    ),
    knowledge_scene_rules=(
        "keep the explainer identity stable across the lesson",
        "reserve detail emphasis for key props and examples",
    ),
    negative_rules=(
        "avoid high-chaos action composition",
        "avoid historical faction staging in general knowledge topics",
    ),
    default_shot_preset_ids=("classroom_demo", "balanced_explainer", "detail_focus"),
    cast_slots=(
        {
            "slot_id": "host_explainer",
            "semantic_role": "host_explainer",
            "visual_anchor": "confident presenter bird",
            "prop_anchor": "board pointer or diagram card",
            "personality_anchor": "clear and friendly",
            "theme_mapping_rule": "keep the main explainer stable across concept topics",
            "reuse_priority": 96,
        },
        {
            "slot_id": "learner_support",
            "semantic_role": "learner_support",
            "visual_anchor": "engaged learner bird",
            "prop_anchor": "notebook or label card",
            "personality_anchor": "curious and receptive",
            "theme_mapping_rule": "support teaching beats with reaction and comparison framing",
            "reuse_priority": 84,
        },
        {
            "slot_id": "demo_assistant",
            "semantic_role": "demo_assistant",
            "visual_anchor": "helper bird near props",
            "prop_anchor": "sample object or experiment prop",
            "personality_anchor": "helpful and practical",
            "theme_mapping_rule": "support demonstrations and staged comparisons",
            "reuse_priority": 78,
        },
    ),
    conservative_fallback_mode="concept_explainer",
    forced_mode="concept_explainer",
)


ANGRY_BIRDS_HISTORY_CLASSROOM_WORLD_PRESET = WorldPresetDefinition(
    preset_id="angry_birds_history_classroom",
    display_name="History Gallery",
    display_name_key="storyboard.preset.world.angry_birds_history_classroom.name",
    description_key="storyboard.preset.world.angry_birds_history_classroom.description",
    supported_modes=("theme_mapping", "concept_explainer"),
    style_core="history-teaching bird classroom with archive motifs, timelines, and lecture staging",
    world_elements=(
        "timeline wall",
        "archive shelves",
        "lecture podium",
        "history map",
        "artifact stand",
    ),
    knowledge_scene_rules=(
        "keep the history-teaching atmosphere consistent across scenes",
        "reuse archive, lecture, and timeline motifs to support continuity",
    ),
    negative_rules=(
        "avoid flattening into a generic neutral classroom",
        "avoid parody overwhelming historical readability",
    ),
    default_shot_preset_ids=("opening_world_building", "balanced_explainer", "character_relationship"),
    cast_slots_by_mode={
        "theme_mapping": (
            {
                "slot_id": "history_figure_lead",
                "semantic_role": "history_figure_lead",
                "visual_anchor": "mapped history lead bird",
                "prop_anchor": "timeline marker or emblem",
                "personality_anchor": "grounded and recognizable",
                "theme_mapping_rule": "map named historical figures into this lead slot",
                "reuse_priority": 90,
            },
            {
                "slot_id": "era_context_support",
                "semantic_role": "era_context_support",
                "visual_anchor": "era context support bird",
                "prop_anchor": "map or era card",
                "personality_anchor": "contextual and explanatory",
                "theme_mapping_rule": "carry factions, periods, or comparison context",
                "reuse_priority": 82,
            },
            {
                "slot_id": "narrator_moderator",
                "semantic_role": "narrator_moderator",
                "visual_anchor": "teaching moderator bird",
                "prop_anchor": "pointer or podium",
                "personality_anchor": "measured and helpful",
                "theme_mapping_rule": "stabilize narration through topic shifts",
                "reuse_priority": 85,
            },
        ),
        "concept_explainer": (
            {
                "slot_id": "history_host",
                "semantic_role": "history_host",
                "visual_anchor": "history lecturer bird",
                "prop_anchor": "timeline board or podium",
                "personality_anchor": "clear and welcoming",
                "theme_mapping_rule": "anchor history explainer lessons with a stable host",
                "reuse_priority": 92,
            },
            {
                "slot_id": "timeline_support",
                "semantic_role": "timeline_support",
                "visual_anchor": "timeline guide bird",
                "prop_anchor": "timeline marker or era card",
                "personality_anchor": "organized and contextual",
                "theme_mapping_rule": "support chronology, sequence, and era transitions in history lessons",
                "reuse_priority": 80,
            },
            {
                "slot_id": "student_observer",
                "semantic_role": "student_observer",
                "visual_anchor": "learner observer bird",
                "prop_anchor": "notes or question card",
                "personality_anchor": "curious and focused",
                "theme_mapping_rule": "provide audience viewpoint for history concept beats",
                "reuse_priority": 76,
            },
        ),
    },
    conservative_fallback_mode="concept_explainer",
)


BUILTIN_WORLD_PRESETS = (
    NEUTRAL_KNOWLEDGE_WORLD_PRESET,
    DUAL_MODE_WORLD_PRESET,
    ANGRY_BIRDS_THREE_KINGDOMS_WORLD_PRESET,
    ANGRY_BIRDS_KNOWLEDGE_CLASSROOM_WORLD_PRESET,
    ANGRY_BIRDS_HISTORY_CLASSROOM_WORLD_PRESET,
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


OPENING_WORLD_BUILDING_SHOT_PRESET = ShotPresetDefinition(
    preset_id="opening_world_building",
    display_name="Opening World Building",
    display_name_key="storyboard.preset.shot.opening_world_building.name",
    description_key="storyboard.preset.shot.opening_world_building.description",
    supported_scene_count=(4, 5, 6, 7),
    max_consecutive_same=2,
    shot_distribution_rules=(
        "favor wider establishing coverage early before tightening into teaching beats",
        "require at least one long/full establishing frame in the opening portion",
        "adapt shot distance based on scene count while keeping the world readable",
    ),
    opening_rules=(
        "open with a long/full establishing frame that makes world, cast, and spatial context immediately readable",
    ),
    closing_rules=(
        "close on a clear knowledge takeaway after the world has been established",
    ),
    transition_rules=(
        "tighten coverage gradually with a wide -> medium -> detail progression as the lesson focus sharpens",
    ),
    purpose_bias="world-establishing opening bias for teaching-first story setups",
    override_policy="adaptive",
)


CHARACTER_RELATIONSHIP_SHOT_PRESET = ShotPresetDefinition(
    preset_id="character_relationship",
    display_name="Character Relationship",
    display_name_key="storyboard.preset.shot.character_relationship.name",
    description_key="storyboard.preset.shot.character_relationship.description",
    supported_scene_count=(3, 4, 5, 6, 7),
    max_consecutive_same=2,
    shot_distribution_rules=(
        "favor two-shots and readable groupings when relationships matter",
        "prefer full/medium alternation so relationship beats stay legible across scenes",
        "adapt framing to preserve comparison clarity across scene counts",
    ),
    opening_rules=(
        "open with relationship context that makes the key subjects readable together",
    ),
    closing_rules=(
        "end on the clearest relationship takeaway or contrast beat",
    ),
    transition_rules=(
        "prefer full/medium alternation over frequent/repeated extreme close-ups to preserve relationship readability",
    ),
    purpose_bias="relationship readability bias for role, faction, and comparison-heavy topics",
    override_policy="adaptive",
)


CLASSROOM_DEMO_SHOT_PRESET = ShotPresetDefinition(
    preset_id="classroom_demo",
    display_name="Classroom Demo",
    display_name_key="storyboard.preset.shot.classroom_demo.name",
    description_key="storyboard.preset.shot.classroom_demo.description",
    supported_scene_count=(3, 4, 5, 6),
    max_consecutive_same=2,
    shot_distribution_rules=(
        "favor medium teaching frames as the backbone of the lesson rhythm",
        "adapt close detail inserts around the core teaching cadence when needed",
    ),
    opening_rules=(
        "start with a readable teacher-and-demo setup",
    ),
    closing_rules=(
        "end on the clearest demonstrated takeaway or recap beat",
    ),
    transition_rules=(
        "cycle between medium teaching coverage and selective detail emphasis",
    ),
    purpose_bias="medium-shot teaching rhythm bias for classroom demonstrations",
    override_policy="adaptive",
)


BUILTIN_SHOT_PRESETS = (
    BALANCED_EXPLAINER_SHOT_PRESET,
    DETAIL_FOCUS_SHOT_PRESET,
    OPENING_WORLD_BUILDING_SHOT_PRESET,
    CHARACTER_RELATIONSHIP_SHOT_PRESET,
    CLASSROOM_DEMO_SHOT_PRESET,
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
    "ANGRY_BIRDS_HISTORY_CLASSROOM_WORLD_PRESET",
    "ANGRY_BIRDS_KNOWLEDGE_CLASSROOM_WORLD_PRESET",
    "ANGRY_BIRDS_THREE_KINGDOMS_WORLD_PRESET",
    "BALANCED_EXPLAINER_SHOT_PRESET",
    "BUILTIN_SHOT_PRESETS",
    "BUILTIN_WORLD_PRESETS",
    "CHARACTER_RELATIONSHIP_SHOT_PRESET",
    "CLASSROOM_DEMO_SHOT_PRESET",
    "DETAIL_FOCUS_SHOT_PRESET",
    "NEUTRAL_KNOWLEDGE_WORLD_PRESET",
    "OPENING_WORLD_BUILDING_SHOT_PRESET",
    "build_builtin_shot_preset_library_dict",
    "build_builtin_world_preset_library_dict",
    "load_shot_preset_map",
    "lookup_world_preset",
]
