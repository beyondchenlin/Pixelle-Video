# Storyboard Preset Library Expansion And Default Enable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the built-in storyboard preset catalog, localize preset names/descriptions, and make storyboard planning default-on for the main quick-create video flow without forcing it on exploratory surfaces.

**Architecture:** Keep the existing storyboard-first architecture intact, but widen the preset library at the config/model layer, then thread localized preset metadata and caller-controlled default-on behavior through the shared Streamlit style UI. Finish by refactoring the storyboard guide into structured content backed by locale keys so the richer preset catalog and new default behavior remain maintainable.

**Tech Stack:** Python 3.12, Streamlit, Pydantic v2, dataclasses, JSON locale catalogs, pytest

---

Repository note: this repository's `AGENTS.md` forbids `git worktree`, so implement this plan on the current branch and stage only the files listed in each task before every atomic commit.

## File Structure

- Modify: `pixelle_video/models/storyboard_planning.py`
  Add optional built-in-preset localization metadata to the runtime dataclasses that already back storyboard preset dictionaries.
- Modify: `pixelle_video/config/schema.py`
  Persist and validate the new preset metadata fields in config-backed world/shot preset library items.
- Modify: `pixelle_video/config/storyboard_preset_library.py`
  Expand built-in world and shot preset definitions from `2 + 2` to `5 + 5`, including cross-referenced default shot choices and localization keys.
- Modify: `web/components/style_config.py`
  Accept an explicit `storyboard_default_enabled` contract from callers, resolve localized preset labels, and replace hard-coded storyboard guide HTML assembly with structured section data.
- Modify: `web/pipelines/standard.py`
  Make the quick-create pipeline opt into storyboard default-on explicitly.
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
  Add built-in preset names/descriptions plus updated guide copy for default-on behavior.
- Modify: `tests/test_storyboard_preset_library.py`
  Lock the expanded preset inventory, localization metadata, and world-to-shot preset references.
- Modify: `tests/test_style_config_storyboard_planning_ui.py`
  Lock localized label fallback, guide key usage, and toggle default precedence.
- Modify: `tests/test_i18n.py`
  Lock locale coverage for the newly shipped preset keys.

Intentionally untouched in this patch:

- `pixelle_video/services/storyboard_planner.py`
  Planner behavior already consumes preset dictionaries generically; this patch only enriches catalog data, not planner logic.
- `web/components/digital_tts_config.py`
  It exposes a separate style-config surface and should remain storyboard-default-off until product explicitly opts it in.
- `api/routers/content.py`, `api/routers/video.py`
  API behavior is unchanged because default-on is a UI-entrypoint decision, not a transport contract change.

### Task 1: Extend storyboard preset contracts with localization metadata

**Files:**
- Modify: `pixelle_video/models/storyboard_planning.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `tests/test_storyboard_preset_library.py`

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/test_storyboard_preset_library.py
def test_world_preset_schema_preserves_localization_metadata():
    config = PixelleVideoConfig()

    neutral = next(
        item for item in config.storyboard.world_preset_library.model_dump()["items"]
        if item["preset_id"] == "neutral_knowledge_storyboard"
    )

    assert neutral["display_name_key"] == "storyboard.preset.world.neutral_knowledge_storyboard.name"
    assert neutral["description_key"] == "storyboard.preset.world.neutral_knowledge_storyboard.description"


def test_shot_preset_schema_preserves_localization_metadata():
    config = PixelleVideoConfig()

    balanced = next(
        item for item in config.storyboard.shot_preset_library.model_dump()["items"]
        if item["preset_id"] == "balanced_explainer"
    )

    assert balanced["display_name_key"] == "storyboard.preset.shot.balanced_explainer.name"
    assert balanced["description_key"] == "storyboard.preset.shot.balanced_explainer.description"
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_storyboard_preset_library.py -k "localization_metadata" -v`

Expected: FAIL because `WorldPresetDefinition`, `ShotPresetDefinition`, and the config-backed preset item models do not expose `display_name_key` / `description_key` yet.

- [ ] **Step 3: Add the metadata fields to the runtime and config contracts**

```python
# pixelle_video/models/storyboard_planning.py
@dataclass(frozen=True)
class WorldPresetDefinition:
    preset_id: str
    display_name: str
    display_name_key: Optional[str] = None
    description_key: Optional[str] = None
    supported_modes: tuple[ContentMode, ...] = ()
    style_core: str = ""
    world_elements: tuple[str, ...] = ()
    knowledge_scene_rules: tuple[str, ...] = ()
    negative_rules: tuple[str, ...] = ()
    default_shot_preset_ids: tuple[str, ...] = ()
    cast_slots: tuple[dict[str, Any], ...] = ()
    cast_slots_by_mode: dict[ContentMode, tuple[dict[str, Any], ...]] = field(default_factory=dict)
    conservative_fallback_mode: ContentMode = "concept_explainer"
    safe_default: bool = False
    forced_mode: Optional[ContentMode] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "display_name_key": self.display_name_key,
            "description_key": self.description_key,
            "supported_modes": _to_list(self.supported_modes),
            "style_core": self.style_core,
            "world_elements": _to_list(self.world_elements),
            "knowledge_scene_rules": _to_list(self.knowledge_scene_rules),
            "negative_rules": _to_list(self.negative_rules),
            "default_shot_preset_ids": _to_list(self.default_shot_preset_ids),
            "cast_slots": [dict(slot) for slot in self.cast_slots],
            "cast_slots_by_mode": {
                mode: [dict(slot) for slot in slots]
                for mode, slots in self.cast_slots_by_mode.items()
            },
            "conservative_fallback_mode": self.conservative_fallback_mode,
            "safe_default": self.safe_default,
            "forced_mode": self.forced_mode,
        }


@dataclass(frozen=True)
class ShotPresetDefinition:
    preset_id: str
    display_name: str
    display_name_key: Optional[str] = None
    description_key: Optional[str] = None
    supported_scene_count: tuple[int, ...] = ()
    max_consecutive_same: int = 2
    shot_distribution_rules: tuple[str, ...] = ()
    opening_rules: tuple[str, ...] = ()
    closing_rules: tuple[str, ...] = ()
    transition_rules: tuple[str, ...] = ()
    purpose_bias: str = ""
    override_policy: ShotOverridePolicy = "adaptive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "display_name_key": self.display_name_key,
            "description_key": self.description_key,
            "supported_scene_count": _to_list(self.supported_scene_count),
            "max_consecutive_same": self.max_consecutive_same,
            "shot_distribution_rules": _to_list(self.shot_distribution_rules),
            "opening_rules": _to_list(self.opening_rules),
            "closing_rules": _to_list(self.closing_rules),
            "transition_rules": _to_list(self.transition_rules),
            "purpose_bias": self.purpose_bias,
            "override_policy": self.override_policy,
        }
```

```python
# pixelle_video/config/schema.py
class StoryboardWorldPresetItemConfig(BaseModel):
    preset_id: str
    display_name: str
    display_name_key: Optional[str] = Field(default=None)
    description_key: Optional[str] = Field(default=None)
    supported_modes: list[ContentMode] = Field(default_factory=list)
    style_core: str = Field(default="")
    world_elements: list[str] = Field(default_factory=list)
    knowledge_scene_rules: list[str] = Field(default_factory=list)
    negative_rules: list[str] = Field(default_factory=list)
    default_shot_preset_ids: list[str] = Field(default_factory=list)
    cast_slots: list[dict[str, Any]] = Field(default_factory=list)
    cast_slots_by_mode: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    conservative_fallback_mode: ContentMode = Field(default="concept_explainer")
    safe_default: bool = Field(default=False)
    forced_mode: Optional[ContentMode] = Field(default=None)


class StoryboardShotPresetItemConfig(BaseModel):
    preset_id: str
    display_name: str
    display_name_key: Optional[str] = Field(default=None)
    description_key: Optional[str] = Field(default=None)
    supported_scene_count: list[int] = Field(default_factory=list)
    max_consecutive_same: int = Field(default=2)
    shot_distribution_rules: list[str] = Field(default_factory=list)
    opening_rules: list[str] = Field(default_factory=list)
    closing_rules: list[str] = Field(default_factory=list)
    transition_rules: list[str] = Field(default_factory=list)
    purpose_bias: str = Field(default="")
    override_policy: ShotOverridePolicy = Field(default="adaptive")
```

- [ ] **Step 4: Re-run the targeted tests**

Run: `uv run pytest tests/test_storyboard_preset_library.py -k "localization_metadata" -v`

Expected: PASS for both new tests.

- [ ] **Step 5: Commit the contract change**

```bash
git add pixelle_video/models/storyboard_planning.py pixelle_video/config/schema.py tests/test_storyboard_preset_library.py
git commit -m "feat: add storyboard preset localization metadata"
```

### Task 2: Expand the built-in world and shot preset catalog

**Files:**
- Modify: `pixelle_video/config/storyboard_preset_library.py`
- Modify: `tests/test_storyboard_preset_library.py`

- [ ] **Step 1: Write the failing catalog and cross-reference tests**

```python
# tests/test_storyboard_preset_library.py
def test_builtin_world_preset_library_contains_expanded_catalog():
    library = build_builtin_world_preset_library_dict()
    preset_ids = [item["preset_id"] for item in library["items"]]

    assert preset_ids == [
        "neutral_knowledge_storyboard",
        "dual_mode_storyboard",
        "angry_birds_three_kingdoms",
        "angry_birds_knowledge_classroom",
        "angry_birds_history_classroom",
    ]


def test_builtin_shot_preset_library_contains_expanded_catalog():
    library = build_builtin_shot_preset_library_dict()
    preset_ids = [item["preset_id"] for item in library["items"]]

    assert preset_ids == [
        "balanced_explainer",
        "detail_focus",
        "opening_world_building",
        "character_relationship",
        "classroom_demo",
    ]


def test_angry_birds_three_kingdoms_references_character_and_world_building_shots():
    library = build_builtin_world_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "angry_birds_three_kingdoms")

    assert preset["supported_modes"] == ["theme_mapping"]
    assert preset["forced_mode"] == "theme_mapping"
    assert preset["default_shot_preset_ids"] == [
        "character_relationship",
        "opening_world_building",
        "balanced_explainer",
    ]
    assert [slot["slot_id"] for slot in preset["cast_slots"]] == [
        "shu_leader",
        "wei_leader",
        "strategist",
        "warrior_support",
        "learner_observer",
    ]


def test_classroom_demo_shot_preset_prefers_medium_teaching_rhythm():
    library = build_builtin_shot_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "classroom_demo")

    assert preset["supported_scene_count"] == [3, 4, 5, 6]
    assert preset["override_policy"] == "adaptive"
    assert any("medium" in rule for rule in preset["shot_distribution_rules"])
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_storyboard_preset_library.py -k "expanded_catalog or three_kingdoms or classroom_demo" -v`

Expected: FAIL because only `2 + 2` built-ins exist today.

- [ ] **Step 3: Add the new built-in world and shot presets**

```python
# pixelle_video/config/storyboard_preset_library.py
ANGRY_BIRDS_THREE_KINGDOMS_WORLD_PRESET = WorldPresetDefinition(
    preset_id="angry_birds_three_kingdoms",
    display_name="Angry Birds Three Kingdoms",
    display_name_key="storyboard.preset.world.angry_birds_three_kingdoms.name",
    description_key="storyboard.preset.world.angry_birds_three_kingdoms.description",
    supported_modes=("theme_mapping",),
    forced_mode="theme_mapping",
    conservative_fallback_mode="theme_mapping",
    style_core="Angry Birds-inspired silhouettes and playful material language fused with Three Kingdoms teaching motifs",
    world_elements=(
        "faction banners",
        "war maps",
        "scroll racks",
        "camp structures",
        "strategy board",
    ),
    knowledge_scene_rules=(
        "keep Three Kingdoms study intent readable first",
        "translate canon roles into stable bird-like teaching characters",
    ),
    negative_rules=(
        "avoid generic ancient-China realism",
        "avoid drifting into game screenshot composition",
    ),
    default_shot_preset_ids=("character_relationship", "opening_world_building", "balanced_explainer"),
    cast_slots=(
        {"slot_id": "shu_leader", "semantic_role": "shu_leader", "visual_anchor": "warm red leader bird", "prop_anchor": "scroll or faction banner", "personality_anchor": "benevolent and composed", "theme_mapping_rule": "map Liu Bei-like leadership roles here", "reuse_priority": 95},
        {"slot_id": "wei_leader", "semantic_role": "wei_leader", "visual_anchor": "cool dark leader bird", "prop_anchor": "command tablet or banner", "personality_anchor": "strategic and forceful", "theme_mapping_rule": "map Cao Cao-like leadership roles here", "reuse_priority": 95},
        {"slot_id": "strategist", "semantic_role": "strategist", "visual_anchor": "smart adviser bird", "prop_anchor": "war map or pointer", "personality_anchor": "calm and analytical", "theme_mapping_rule": "map strategist or planner roles here", "reuse_priority": 90},
        {"slot_id": "warrior_support", "semantic_role": "warrior_support", "visual_anchor": "large bold warrior bird", "prop_anchor": "weapon prop or stance marker", "personality_anchor": "loyal and energetic", "theme_mapping_rule": "map martial support roles here", "reuse_priority": 88},
        {"slot_id": "learner_observer", "semantic_role": "learner_observer", "visual_anchor": "smaller attentive learner bird", "prop_anchor": "notes or study card", "personality_anchor": "curious and focused", "theme_mapping_rule": "use for study-path or audience surrogate framing", "reuse_priority": 80},
    ),
)

ANGRY_BIRDS_KNOWLEDGE_CLASSROOM_WORLD_PRESET = WorldPresetDefinition(
    preset_id="angry_birds_knowledge_classroom",
    display_name="Angry Birds Knowledge Classroom",
    display_name_key="storyboard.preset.world.angry_birds_knowledge_classroom.name",
    description_key="storyboard.preset.world.angry_birds_knowledge_classroom.description",
    supported_modes=("concept_explainer",),
    forced_mode="concept_explainer",
    conservative_fallback_mode="concept_explainer",
    style_core="playful Angry Birds-like classroom world with readable teaching props and repeatable presenter staging",
    world_elements=(
        "whiteboard",
        "pointer",
        "labeled sample objects",
        "charts",
        "experiment table",
    ),
    knowledge_scene_rules=(
        "keep explainer identity stable across frames",
        "reserve close detail shots for the key learning object",
    ),
    negative_rules=(
        "avoid canon-history role mapping",
        "avoid noisy arcade action framing",
    ),
    default_shot_preset_ids=("classroom_demo", "balanced_explainer", "detail_focus"),
    cast_slots=(
        {"slot_id": "host_explainer", "semantic_role": "host_explainer", "visual_anchor": "confident presenter bird", "prop_anchor": "pointer or board", "personality_anchor": "clear and friendly", "theme_mapping_rule": "hold the explainer identity stable for concept topics", "reuse_priority": 96},
        {"slot_id": "learner_support", "semantic_role": "learner_support", "visual_anchor": "curious learner bird", "prop_anchor": "notebook or label card", "personality_anchor": "engaged and receptive", "theme_mapping_rule": "anchor audience viewpoint and clarifying reactions", "reuse_priority": 84},
        {"slot_id": "demo_assistant", "semantic_role": "demo_assistant", "visual_anchor": "helper bird near props", "prop_anchor": "sample object or experiment prop", "personality_anchor": "helpful and practical", "theme_mapping_rule": "support hands-on demonstrations and staged comparisons", "reuse_priority": 78},
    ),
)

ANGRY_BIRDS_HISTORY_CLASSROOM_WORLD_PRESET = WorldPresetDefinition(
    preset_id="angry_birds_history_classroom",
    display_name="Angry Birds History Classroom",
    display_name_key="storyboard.preset.world.angry_birds_history_classroom.name",
    description_key="storyboard.preset.world.angry_birds_history_classroom.description",
    supported_modes=("theme_mapping", "concept_explainer"),
    conservative_fallback_mode="concept_explainer",
    style_core="history-teaching world with archive-room motifs, timeline staging, and branded bird-like characters",
    world_elements=(
        "timeline wall",
        "archive shelves",
        "lecture podium",
        "history map",
        "artifact stand",
    ),
    knowledge_scene_rules=(
        "keep the history-teaching atmosphere consistent",
        "use recurring archive and lecture motifs across scenes",
    ),
    negative_rules=(
        "avoid generic neutral classroom flattening",
        "avoid comedic parody overwhelming the subject",
    ),
    default_shot_preset_ids=("opening_world_building", "balanced_explainer", "character_relationship"),
    cast_slots_by_mode={
        "theme_mapping": (
            {"slot_id": "history_figure_lead", "semantic_role": "history_figure_lead", "visual_anchor": "mapped history lead bird", "prop_anchor": "timeline marker or emblem", "personality_anchor": "recognizable and grounded", "theme_mapping_rule": "map named history figures into this lead slot", "reuse_priority": 90},
            {"slot_id": "era_context_support", "semantic_role": "era_context_support", "visual_anchor": "era context support bird", "prop_anchor": "map or era card", "personality_anchor": "contextual and explanatory", "theme_mapping_rule": "carry factions, periods, or comparison context", "reuse_priority": 82},
            {"slot_id": "narrator_moderator", "semantic_role": "narrator_moderator", "visual_anchor": "teaching moderator bird", "prop_anchor": "pointer or podium", "personality_anchor": "measured and helpful", "theme_mapping_rule": "stabilize narration through topic shifts", "reuse_priority": 85},
        ),
        "concept_explainer": (
            {"slot_id": "history_host", "semantic_role": "history_host", "visual_anchor": "history lecturer bird", "prop_anchor": "podium or archive card", "personality_anchor": "calm and instructive", "theme_mapping_rule": "keep a stable explainer for non-character-centric history topics", "reuse_priority": 92},
            {"slot_id": "timeline_support", "semantic_role": "timeline_support", "visual_anchor": "timeline assistant bird", "prop_anchor": "date marker or timeline ribbon", "personality_anchor": "orderly and clarifying", "theme_mapping_rule": "support chronology and comparison framing", "reuse_priority": 80},
        ),
    },
)

OPENING_WORLD_BUILDING_SHOT_PRESET = ShotPresetDefinition(
    preset_id="opening_world_building",
    display_name="Opening World Building",
    display_name_key="storyboard.preset.shot.opening_world_building.name",
    description_key="storyboard.preset.shot.opening_world_building.description",
    supported_scene_count=(4, 5, 6, 7),
    max_consecutive_same=2,
    shot_distribution_rules=(
        "require at least one long or full establishing frame in the opening portion",
        "bias the early rhythm toward world and cast staging before tighter inserts",
    ),
    opening_rules=("prioritize world and context establishment in the first frame",),
    closing_rules=("return to a readable knowledge takeaway after the wider setup",),
    transition_rules=("tighten gradually from wide frames into medium or detail emphasis",),
    purpose_bias="world-establishing openers for theme-heavy storytelling",
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
        "preserve relational readability over object-detail bias",
        "prefer full or medium groupings before isolated inserts",
    ),
    opening_rules=("establish the key pair or group before detail inserts",),
    closing_rules=("end on a relationship summary or comparison beat",),
    transition_rules=("prefer full and medium alternation over repeated extreme close-ups",),
    purpose_bias="paired and grouped compositions for relationship-heavy topics",
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
        "keep a stable teaching rhythm with medium shots as the backbone",
        "reserve close detail shots for key props or experiment moments",
    ),
    opening_rules=("establish the explainer or teaching setup quickly",),
    closing_rules=("end on the final demonstrated takeaway or key teaching prop",),
    transition_rules=("move from explainer framing to prop or detail framing in a controlled way",),
    purpose_bias="medium-shot teaching rhythm for explainer-led scenes",
    override_policy="adaptive",
)

BUILTIN_WORLD_PRESETS = (
    NEUTRAL_KNOWLEDGE_WORLD_PRESET,
    DUAL_MODE_WORLD_PRESET,
    ANGRY_BIRDS_THREE_KINGDOMS_WORLD_PRESET,
    ANGRY_BIRDS_KNOWLEDGE_CLASSROOM_WORLD_PRESET,
    ANGRY_BIRDS_HISTORY_CLASSROOM_WORLD_PRESET,
)

BUILTIN_SHOT_PRESETS = (
    BALANCED_EXPLAINER_SHOT_PRESET,
    DETAIL_FOCUS_SHOT_PRESET,
    OPENING_WORLD_BUILDING_SHOT_PRESET,
    CHARACTER_RELATIONSHIP_SHOT_PRESET,
    CLASSROOM_DEMO_SHOT_PRESET,
)
```

- [ ] **Step 4: Re-run the expanded library tests**

Run: `uv run pytest tests/test_storyboard_preset_library.py -k "expanded_catalog or three_kingdoms or classroom_demo" -v`

Expected: PASS for all new catalog and cross-reference tests.

- [ ] **Step 5: Commit the expanded preset library**

```bash
git add pixelle_video/config/storyboard_preset_library.py tests/test_storyboard_preset_library.py
git commit -m "feat: expand storyboard preset library"
```

### Task 3: Default storyboard planning on quick-create and localize preset labels

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/pipelines/standard.py`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`

- [ ] **Step 1: Write the failing UI-behavior tests**

```python
# tests/test_style_config_storyboard_planning_ui.py
def test_resolve_storyboard_toggle_default_prefers_user_state_then_preview_then_caller_default():
    assert style_config.resolve_storyboard_toggle_default(
        session_state={"storyboard_planning_enabled": False},
        storyboard_default_enabled=True,
        preview_snapshot={"frames": []},
    ) is False
    assert style_config.resolve_storyboard_toggle_default(
        session_state={},
        storyboard_default_enabled=False,
        preview_snapshot={"frames": []},
    ) is True
    assert style_config.resolve_storyboard_toggle_default(
        session_state={},
        storyboard_default_enabled=True,
        preview_snapshot=None,
    ) is True


def test_resolve_storyboard_preset_label_uses_translation_key_then_display_name(monkeypatch):
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: {
            "storyboard.preset.world.neutral_knowledge_storyboard.name": "Localized Neutral Storyboard"
        }.get(key, key),
    )

    translated = style_config.resolve_storyboard_preset_label(
        {
            "preset_id": "neutral_knowledge_storyboard",
            "display_name": "Neutral Knowledge Storyboard",
            "display_name_key": "storyboard.preset.world.neutral_knowledge_storyboard.name",
        }
    )
    fallback = style_config.resolve_storyboard_preset_label(
        {
            "preset_id": "custom_world",
            "display_name": "Custom World",
            "display_name_key": "storyboard.preset.world.custom_world.name",
        }
    )

    assert translated == "Localized Neutral Storyboard"
    assert fallback == "Custom World"


def test_standard_pipeline_enables_storyboard_default(monkeypatch):
    captured_kwargs = {}

    def fake_render_style_config(pixelle_video, **kwargs):
        captured_kwargs.update(kwargs)
        return {}

    monkeypatch.setattr("web.pipelines.standard.render_style_config", fake_render_style_config)
    monkeypatch.setattr("web.pipelines.standard.render_content_input", lambda: {})
    monkeypatch.setattr("web.pipelines.standard.render_bgm_section", lambda: {})
    monkeypatch.setattr("web.pipelines.standard.render_version_info", lambda: None)
    monkeypatch.setattr("web.pipelines.standard.render_output_preview", lambda pixelle_video, params: None)
    monkeypatch.setattr("web.pipelines.standard.st.columns", lambda spec: (_FakeContext(), _FakeContext(), _FakeContext()))

    StandardPipelineUI().render(pixelle_video=object())

    assert captured_kwargs["storyboard_default_enabled"] is True
```

- [ ] **Step 2: Run the targeted UI tests to verify they fail**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -k "toggle_default or preset_label or standard_pipeline" -v`

Expected: FAIL because the helper functions and caller-provided default flag do not exist yet.

- [ ] **Step 3: Implement caller-controlled default-on and localized label resolution**

```python
# web/components/style_config.py
def resolve_storyboard_toggle_default(
    *,
    session_state: dict,
    storyboard_default_enabled: bool,
    preview_snapshot: dict | None,
) -> bool:
    if "storyboard_planning_enabled" in session_state:
        return bool(session_state["storyboard_planning_enabled"])
    if preview_snapshot:
        return True
    return bool(storyboard_default_enabled)


def resolve_storyboard_preset_label(item: dict[str, Any]) -> str:
    label_key = item.get("display_name_key")
    if isinstance(label_key, str) and label_key.strip():
        translated = tr(label_key)
        if translated != label_key:
            return translated

    display_name = item.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name
    return item.get("preset_id", "")


def render_style_config(pixelle_video, storyboard_default_enabled: bool = False):
    preview_snapshot = st.session_state.get("storyboard_preview_snapshot")
    storyboard_enabled = st.checkbox(
        tr("storyboard.enabled"),
        value=resolve_storyboard_toggle_default(
            session_state=st.session_state,
            storyboard_default_enabled=storyboard_default_enabled,
            preview_snapshot=preview_snapshot,
        ),
        key="storyboard_planning_enabled",
        help=tr("storyboard.enabled_help"),
    )

    if storyboard_enabled:
        world_label_map = {
            item["preset_id"]: resolve_storyboard_preset_label(item)
            for item in world_items
        }
        shot_label_map = {
            item["preset_id"]: resolve_storyboard_preset_label(item)
            for item in shot_items
        }
```

```python
# web/pipelines/standard.py
with middle_col:
    style_params = render_style_config(
        pixelle_video,
        storyboard_default_enabled=True,
    )
```

- [ ] **Step 4: Re-run the targeted UI tests**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -k "toggle_default or preset_label or standard_pipeline" -v`

Expected: PASS for the new helper and quick-create default-on tests.

- [ ] **Step 5: Commit the UI default-on wiring**

```bash
git add web/components/style_config.py web/pipelines/standard.py tests/test_style_config_storyboard_planning_ui.py
git commit -m "feat: default storyboard planning on quick create"
```

### Task 4: Refactor storyboard guide content and ship locale coverage for the expanded catalog

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`
- Modify: `tests/test_i18n.py`

- [ ] **Step 1: Write the failing guide and locale coverage tests**

```python
# tests/test_style_config_storyboard_planning_ui.py
def test_storyboard_planning_guide_renders_default_on_copy_and_structured_sections(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    style_config.render_storyboard_planning_guide()

    rendered_html = "\n".join(body for body, _kwargs in fake_st.markdowns)
    assert "storyboard.guide.default_on_title" in rendered_html
    assert "storyboard.guide.default_on_body" in rendered_html
    assert "storyboard.guide.when_to_turn_off.title" in rendered_html
    assert "storyboard.guide.when_to_turn_off.body" in rendered_html
    assert "storyboard.guide.combo.theme_mapping.title" in rendered_html
    assert "storyboard.guide.field.world_preset" in rendered_html


def test_storyboard_builtin_preset_translation_keys_exist_in_supported_locales():
    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    required_keys = [
        "storyboard.preset.world.neutral_knowledge_storyboard.name",
        "storyboard.preset.world.neutral_knowledge_storyboard.description",
        "storyboard.preset.world.dual_mode_storyboard.name",
        "storyboard.preset.world.dual_mode_storyboard.description",
        "storyboard.preset.world.angry_birds_three_kingdoms.name",
        "storyboard.preset.world.angry_birds_three_kingdoms.description",
        "storyboard.preset.world.angry_birds_knowledge_classroom.name",
        "storyboard.preset.world.angry_birds_knowledge_classroom.description",
        "storyboard.preset.world.angry_birds_history_classroom.name",
        "storyboard.preset.world.angry_birds_history_classroom.description",
        "storyboard.preset.shot.balanced_explainer.name",
        "storyboard.preset.shot.balanced_explainer.description",
        "storyboard.preset.shot.detail_focus.name",
        "storyboard.preset.shot.detail_focus.description",
        "storyboard.preset.shot.opening_world_building.name",
        "storyboard.preset.shot.opening_world_building.description",
        "storyboard.preset.shot.character_relationship.name",
        "storyboard.preset.shot.character_relationship.description",
        "storyboard.preset.shot.classroom_demo.name",
        "storyboard.preset.shot.classroom_demo.description",
        "storyboard.guide.default_on_title",
        "storyboard.guide.default_on_body",
        "storyboard.guide.when_to_turn_off.title",
        "storyboard.guide.when_to_turn_off.body",
    ]

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []
```

```python
# tests/test_i18n.py
def test_storyboard_builtin_preset_names_translate_in_supported_locales():
    original_language = get_language()
    try:
        for language in ("zh_CN", "en_US"):
            set_language(language)
            assert tr("storyboard.preset.world.angry_birds_three_kingdoms.name") != "storyboard.preset.world.angry_birds_three_kingdoms.name"
            assert tr("storyboard.preset.shot.classroom_demo.name") != "storyboard.preset.shot.classroom_demo.name"
    finally:
        set_language(original_language)
```

- [ ] **Step 2: Run the targeted guide and locale tests to verify they fail**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -k "default_on_copy or builtin_preset_translation_keys" -v`

Run: `uv run pytest tests/test_i18n.py -k "storyboard_builtin_preset_names_translate" -v`

Expected: FAIL because the new guide keys and built-in preset translation keys do not exist yet.

- [ ] **Step 3: Refactor the guide into structured content data and add locale keys**

```python
# web/components/style_config.py
STORYBOARD_GUIDE_NOTE_SPECS = (
    ("storyboard.guide.default_on_title", "storyboard.guide.default_on_body"),
    ("storyboard.guide.when_to_turn_off.title", "storyboard.guide.when_to_turn_off.body"),
)

STORYBOARD_GUIDE_COMBO_SPECS = (
    ("storyboard.guide.combo.explainer.title", "storyboard.guide.combo.explainer.body", "#92400e", "rgba(254, 243, 199, 0.62)"),
    ("storyboard.guide.combo.theme_mapping.title", "storyboard.guide.combo.theme_mapping.body", "#1d4ed8", "rgba(239, 246, 255, 0.92)"),
    ("storyboard.guide.combo.iteration.title", "storyboard.guide.combo.iteration.body", "#0f766e", "rgba(240, 253, 250, 0.92)"),
)

STORYBOARD_GUIDE_FIELD_SPECS = (
    ("storyboard.world_preset", "storyboard.guide.field.world_preset"),
    ("storyboard.shot_preset", "storyboard.guide.field.shot_preset"),
    ("storyboard.consistency_strength", "storyboard.guide.field.consistency_strength"),
    ("storyboard.content_mode", "storyboard.guide.field.content_mode"),
    ("storyboard.role_strategy", "storyboard.guide.field.role_strategy"),
    ("storyboard.role_locking_strength", "storyboard.guide.field.role_locking_strength"),
    ("storyboard.shot_strategy", "storyboard.guide.field.shot_strategy"),
)


def render_storyboard_planning_guide():
    quick_html = "".join(
        _build_storyboard_guide_note_html(title_key, body_key)
        for title_key, body_key in STORYBOARD_GUIDE_NOTE_SPECS
    )
    combo_html = "".join(
        _build_storyboard_guide_combo_html(title_key, body_key, accent, background)
        for title_key, body_key, accent, background in STORYBOARD_GUIDE_COMBO_SPECS
    )
    field_html = "".join(
        f"""
        <li style="margin-bottom: 10px;">
            <span style="font-weight: 700; color: #1f2937;">{escape(tr(label_key))}</span><br/>
            <span style="color: #475569;">{escape(tr(description_key))}</span>
        </li>
        """
        for label_key, description_key in STORYBOARD_GUIDE_FIELD_SPECS
    )

    with st.expander(tr("storyboard.guide.title"), expanded=False):
        st.markdown(
            f"""
            <div>{quick_html}</div>
            <div style="margin-top: 12px;">{combo_html}</div>
            <ul style="margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.65;">
                {field_html}
            </ul>
            <div style="margin-top: 12px;">
                <div style="font-size: 13px; font-weight: 700; color: #1d4ed8;">{escape(tr("storyboard.guide.override_title"))}</div>
                <div style="font-size: 13px; line-height: 1.65; color: #334155;">{escape(tr("storyboard.guide.override_body"))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
```

```json
// web/i18n/locales/zh_CN.json
{
  "t": {
    "storyboard.guide.default_on_title": "默认已经开启",
    "storyboard.guide.default_on_body": "在主视频生成流程里，分镜规划默认就是打开的。把它理解成知识讲解和多图连续性的常规路径，而不是高级附加功能。",
    "storyboard.guide.when_to_turn_off.title": "什么时候可以先关掉",
    "storyboard.guide.when_to_turn_off.body": "如果你正在快速试风格、验证原始 prompt 方向，或者内容提纲还不稳定，可以暂时关闭它来减少约束、加快探索。",
    "storyboard.preset.world.neutral_knowledge_storyboard.name": "中性知识分镜",
    "storyboard.preset.world.neutral_knowledge_storyboard.description": "中性、清晰、以知识表达为先的默认世界，适合通用讲解内容。",
    "storyboard.preset.world.dual_mode_storyboard.name": "双模式分镜世界",
    "storyboard.preset.world.dual_mode_storyboard.description": "同时兼容主题映射和概念讲解的通用世界，适合做安全过渡与兼容回退。",
    "storyboard.preset.world.angry_birds_three_kingdoms.name": "愤怒小鸟版三国",
    "storyboard.preset.world.angry_birds_three_kingdoms.description": "把三国人物、阵营和学习母题映射进愤怒小鸟世界，适合历史角色关系与主题讲解。",
    "storyboard.preset.world.angry_birds_knowledge_classroom.name": "愤怒小鸟知识课堂",
    "storyboard.preset.world.angry_birds_knowledge_classroom.description": "以稳定讲解角色、课堂和实验母题承载一般知识概念，适合科学与通识讲解。",
    "storyboard.preset.world.angry_birds_history_classroom.name": "愤怒小鸟历史课堂",
    "storyboard.preset.world.angry_birds_history_classroom.description": "比中性课堂更有历史教学氛围，适合朝代、人物、事件和历史关系讲解。",
    "storyboard.preset.shot.balanced_explainer.name": "均衡讲解型",
    "storyboard.preset.shot.balanced_explainer.description": "在世界交代、讲解动作和重点细节之间保持平衡，是默认镜头节奏。",
    "storyboard.preset.shot.detail_focus.name": "重点细节型",
    "storyboard.preset.shot.detail_focus.description": "更强调近景和特写，用于关键知识对象、结构细节和重要道具。",
    "storyboard.preset.shot.opening_world_building.name": "开场铺陈型",
    "storyboard.preset.shot.opening_world_building.description": "前段优先建立世界、角色与空间关系，随后再逐步推进到知识重点。",
    "storyboard.preset.shot.character_relationship.name": "角色关系型",
    "storyboard.preset.shot.character_relationship.description": "优先保证人物、阵营和对照关系的可读性，适合角色关系和主题映射内容。",
    "storyboard.preset.shot.classroom_demo.name": "课堂演示型",
    "storyboard.preset.shot.classroom_demo.description": "以中景讲解为骨架，近景和特写用于关键道具、实验现象和知识重点。"
  }
}
```

```json
// web/i18n/locales/en_US.json
{
  "t": {
    "storyboard.guide.default_on_title": "Storyboard is already on by default",
    "storyboard.guide.default_on_body": "In the main video-generation flow, storyboard planning starts enabled. Treat it as the normal path for continuity and explainers, not as an advanced extra.",
    "storyboard.guide.when_to_turn_off.title": "When to turn it off first",
    "storyboard.guide.when_to_turn_off.body": "Turn it off temporarily when you are rapidly exploring rough style direction, testing raw prompts, or working from an unstable outline.",
    "storyboard.preset.world.neutral_knowledge_storyboard.name": "Neutral Knowledge Storyboard",
    "storyboard.preset.world.neutral_knowledge_storyboard.description": "A neutral, readable knowledge-first world that works as the safe default for general explainers.",
    "storyboard.preset.world.dual_mode_storyboard.name": "Dual Mode Storyboard",
    "storyboard.preset.world.dual_mode_storyboard.description": "A general-purpose world that supports both theme mapping and concept explainers for safe fallback and compatibility.",
    "storyboard.preset.world.angry_birds_three_kingdoms.name": "Angry Birds Three Kingdoms",
    "storyboard.preset.world.angry_birds_three_kingdoms.description": "Maps Three Kingdoms roles, factions, and study motifs into an Angry Birds-style teaching world.",
    "storyboard.preset.world.angry_birds_knowledge_classroom.name": "Angry Birds Knowledge Classroom",
    "storyboard.preset.world.angry_birds_knowledge_classroom.description": "Uses a stable explainer cast, classroom motifs, and repeatable props for general knowledge topics.",
    "storyboard.preset.world.angry_birds_history_classroom.name": "Angry Birds History Classroom",
    "storyboard.preset.world.angry_birds_history_classroom.description": "Adds archive and timeline motifs for history teaching topics that need more atmosphere than the neutral classroom.",
    "storyboard.preset.shot.balanced_explainer.name": "Balanced Explainer",
    "storyboard.preset.shot.balanced_explainer.description": "Balances context, teaching action, and detail emphasis for the default explainer rhythm.",
    "storyboard.preset.shot.detail_focus.name": "Detail Focus",
    "storyboard.preset.shot.detail_focus.description": "Pushes closer detail and insert shots for key knowledge objects, structures, and props.",
    "storyboard.preset.shot.opening_world_building.name": "Opening World Building",
    "storyboard.preset.shot.opening_world_building.description": "Biases the opening toward world and cast establishment before tightening into knowledge beats.",
    "storyboard.preset.shot.character_relationship.name": "Character Relationship",
    "storyboard.preset.shot.character_relationship.description": "Keeps paired and grouped subjects readable for role, faction, and comparison-heavy topics.",
    "storyboard.preset.shot.classroom_demo.name": "Classroom Demo",
    "storyboard.preset.shot.classroom_demo.description": "Uses medium-shot teaching rhythm as the backbone, with close detail reserved for key props and demonstrations."
  }
}
```

- [ ] **Step 4: Re-run the guide, locale, and i18n regressions**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -v`

Run: `uv run pytest tests/test_i18n.py -v`

Expected: PASS for the updated guide rendering and locale coverage tests.

- [ ] **Step 5: Commit the guide and locale work**

```bash
git add web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_storyboard_planning_ui.py tests/test_i18n.py
git commit -m "feat: localize storyboard preset catalog and guide"
```

## Final Verification

- [ ] **Step 1: Run the focused regression suite**

Run: `uv run pytest tests/test_storyboard_preset_library.py tests/test_style_config_storyboard_planning_ui.py tests/test_i18n.py -v`

Expected: PASS with the expanded preset inventory, default-on UI behavior, and locale coverage locked.

- [ ] **Step 2: Run the quick-create pipeline smoke regressions**

Run: `uv run pytest tests/test_output_preview.py tests/test_video_api.py tests/test_content_image_prompt_api.py -k "storyboard or preset or style_config" -v`

Expected: PASS or SKIPPED-only output; no new storyboard-control regressions should appear.

- [ ] **Step 3: Confirm the working tree only contains intended files, then push**

Run: `git status --short`

Expected: only the files listed in this plan, or a clean working tree after the last implementation commit.

Run: `git push origin dev`

Expected: push succeeds; if networking or remote policy blocks it, capture the exact failure and stop instead of claiming completion.
