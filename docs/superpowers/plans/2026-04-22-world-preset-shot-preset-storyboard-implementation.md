# World Preset / Shot Preset Storyboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the storyboard-first `world preset + shot preset + cast bible + snapshot persistence` rollout so standard/custom image-generation paths produce structured frame plans, stable prompt assembly, and replayable task history without breaking the existing prompt-prefix fallback path.

**Architecture:** Add project-level preset libraries and runtime storyboard-planning models, resolve `content mode / world preset / shot preset / role strategy` before prompt generation, then let a shared planner produce frame plans that drive final prompt assembly and task snapshots. Standard/custom pipelines, content APIs, web preview, and history all read the same resolved planning state, while legacy styled-prefix entry points remain available when storyboard-first controls are not used.

**Tech Stack:** Python 3.12, FastAPI, Streamlit, Pydantic, dataclasses, Loguru, pytest, existing Pixelle LLM/media services

---

Repository note: this repository's `AGENTS.md` forbids `git worktree`, so execute this plan on the current branch and stage exact files for each atomic commit.

## File Structure

- Create: `pixelle_video/models/storyboard_planning.py`
  Runtime dataclasses for world presets, shot presets, routing decisions, frame plans, planning snapshots, and validation errors.
- Create: `pixelle_video/config/storyboard_preset_library.py`
  Built-in neutral/default world preset, built-in shot presets, project-level library builders, and lookup helpers.
- Modify: `pixelle_video/config/schema.py`
  Adds storyboard preset-library config models and defaults.
- Modify: `pixelle_video/config/manager.py`
  Adds getters/setters for world/shot preset libraries and active defaults.
- Create: `pixelle_video/prompts/storyboard_planning.py`
  LLM prompt builders for mode routing and frame-plan generation.
- Create: `pixelle_video/services/storyboard_consistency.py`
  Pre-planning validation, frame-override merge, shot repair, and prompt-input validation helpers.
- Create: `pixelle_video/services/storyboard_planner.py`
  Resolves mode, world preset, role strategy, shot preset, frame overrides, normalized style precedence, and frame-plan snapshots.
- Modify: `pixelle_video/models/style_resolution.py`
  Extends styled batch return shape with optional storyboard-planning metadata.
- Modify: `pixelle_video/utils/style_resolution.py`
  Adds world-preset compatibility normalization for resolved style overrides.
- Modify: `pixelle_video/utils/prompt_helper.py`
  Adds frame-plan-aware final prompt assembly while preserving existing legacy helpers.
- Modify: `pixelle_video/utils/content_generators.py`
  Upgrades the shared styled-batch helper to run the storyboard planner before final prompt assembly.
- Modify: `pixelle_video/models/storyboard.py`
  Persists resolved storyboard-control settings on `StoryboardConfig`, frame-level planning metadata on `StoryboardFrame`, and task snapshots on `Storyboard`.
- Modify: `pixelle_video/pipelines/linear.py`
  Extends `PipelineContext` with storyboard-planning fields.
- Modify: `pixelle_video/pipelines/standard.py`
  Uses the shared planner/batch helper and stores planning snapshots on generated storyboards.
- Modify: `pixelle_video/pipelines/custom.py`
  Reuses the same planning-aware batch helper for media-requiring custom templates.
- Modify: `pixelle_video/services/persistence.py`
  Serializes/deserializes the storyboard planning snapshot and resolved control fields.
- Modify: `pixelle_video/services/history_manager.py`
  Keeps snapshot-rich storyboard/history detail available to the UI.
- Modify: `api/schemas/video.py`
  Adds storyboard-planning request fields for synchronous and async video generation.
- Modify: `api/routers/video.py`
  Threads the new planning controls into `pixelle_video.generate_video`.
- Modify: `api/schemas/content.py`
  Adds optional storyboard-planning controls for image-prompt generation.
- Modify: `api/routers/content.py`
  Sends image-prompt requests through the same planning-aware styled batch helper.
- Modify: `web/components/style_config.py`
  Adds world preset, shot preset, consistency strength, and advanced storyboard controls plus preview metadata.
- Create: `web/components/storyboard_preview.py`
  Renders editable frame-plan cards, locked-field controls, and normalized override payloads before generation.
- Modify: `web/components/output_preview.py`
  Includes the new control fields and frame overrides in generate-video requests.
- Modify: `web/pages/2_📚_History.py`
  Shows resolved preset/selection-source/snapshot summary in history detail.
- Modify: `web/i18n/en_US.json`
- Modify: `web/i18n/zh_CN.json`
  Adds labels/help text for the new controls and history fields.
- Create: `tests/test_storyboard_preset_library.py`
  Validates preset-library defaults, schema invariants, and safe-default behavior.
- Create: `tests/test_storyboard_planner.py`
  Covers mode resolution, role-strategy conflicts, shot-preset resolution, repair, and default selection.
- Create: `tests/test_storyboard_prompt_builder.py`
  Covers normalized style precedence and frame-plan-driven prompt assembly.
- Create: `tests/test_storyboard_snapshot_persistence.py`
  Covers snapshot serialization, replay-safe hashes, and frame metadata round-tripping.
- Create: `tests/test_style_config_storyboard_planning_ui.py`
  Covers style-config helper behavior for storyboard controls and preview metadata.
- Create: `tests/test_storyboard_preview_ui.py`
  Covers preview-card rendering data, lock semantics, and frame-override payload normalization.
- Modify: `tests/test_styled_image_prompt_batch.py`
  Keeps shared batch regression coverage while asserting planning metadata flows through.
- Modify: `tests/test_standard_pipeline_prompt_prefix.py`
  Expands standard-pipeline assertions to include snapshot/control persistence.
- Modify: `tests/test_custom_pipeline_styled_batch.py`
  Expands custom-pipeline regression coverage for planning-aware prompts.
- Modify: `tests/test_content_image_prompt_api.py`
- Modify: `tests/test_video_api.py`
- Modify: `tests/test_output_preview.py`
  Verifies API/web request contracts now carry storyboard-planning fields.

Intentionally untouched in V1:

- `pixelle_video/pipelines/asset_based.py`
  Asset-based scenes already come with user-selected media and do not need world/shot prompt planning in this rollout.
- `web/components/content_input.py`
  Scene-count and text-input UX remain where they are; storyboard controls live in the style/config column for V1.

### Task 1: Add preset libraries and storyboard-planning data contracts

**Files:**
- Create: `pixelle_video/models/storyboard_planning.py`
- Create: `pixelle_video/config/storyboard_preset_library.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/manager.py`
- Test: `tests/test_storyboard_preset_library.py`

- [ ] **Step 1: Write the failing preset-library tests**

```python
# tests/test_storyboard_preset_library.py
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.storyboard_preset_library import (
    build_builtin_shot_preset_library_dict,
    build_builtin_world_preset_library_dict,
)


def test_builtin_world_preset_library_contains_neutral_safe_default():
    library = build_builtin_world_preset_library_dict()

    assert library["default_world_preset_id"] == "neutral_knowledge_storyboard"
    neutral = next(item for item in library["items"] if item["preset_id"] == "neutral_knowledge_storyboard")
    assert neutral["safe_default"] is True
    assert neutral["supported_modes"] == ["theme_mapping", "concept_explainer"]


def test_dual_mode_world_preset_requires_mode_specific_cast_map():
    library = build_builtin_world_preset_library_dict()
    dual_mode = next(item for item in library["items"] if item["preset_id"] == "neutral_knowledge_storyboard")

    assert set(dual_mode["cast_slots_by_mode"].keys()) == set(dual_mode["supported_modes"])
    assert dual_mode["conservative_fallback_mode"] in dual_mode["supported_modes"]


def test_builtin_shot_preset_library_contains_balanced_explainer_default():
    library = build_builtin_shot_preset_library_dict()

    assert library["default_shot_preset_id"] == "balanced_explainer"
    balanced = next(item for item in library["items"] if item["preset_id"] == "balanced_explainer")
    assert balanced["override_policy"] == "adaptive"
    assert 5 in balanced["supported_scene_count"]


def test_pixelle_config_bootstraps_storyboard_libraries():
    config = PixelleVideoConfig()
    dumped = config.model_dump()

    assert dumped["storyboard"]["world_preset_library"]["default_world_preset_id"] == "neutral_knowledge_storyboard"
    assert dumped["storyboard"]["shot_preset_library"]["default_shot_preset_id"] == "balanced_explainer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storyboard_preset_library.py -v`

Expected: FAIL with import errors because `pixelle_video.config.storyboard_preset_library` and the new `storyboard` config section do not exist yet.

- [ ] **Step 3: Add the preset-library and config contracts**

```python
# pixelle_video/models/storyboard_planning.py
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

ContentMode = Literal["theme_mapping", "concept_explainer"]
ConsistencyStrength = Literal["standard", "strong"]
RoleStrategy = Literal["auto", "theme_mapping", "stable_explainer_cast"]
ShotOverridePolicy = Literal["adaptive", "strict"]
FrameSource = Literal["planner_generated", "repair_adjusted", "user_locked"]


@dataclass(frozen=True)
class WorldPresetDefinition:
    preset_id: str
    display_name: str
    supported_modes: list[ContentMode]
    forced_mode: Optional[ContentMode]
    conservative_fallback_mode: ContentMode
    style_core: str
    world_elements: list[str] = field(default_factory=list)
    knowledge_scene_rules: list[str] = field(default_factory=list)
    negative_rules: list[str] = field(default_factory=list)
    default_shot_preset_ids: list[str] = field(default_factory=list)
    cast_slots: dict[str, dict[str, Any]] = field(default_factory=dict)
    cast_slots_by_mode: dict[ContentMode, dict[str, dict[str, Any]]] = field(default_factory=dict)
    safe_default: bool = False


@dataclass(frozen=True)
class ShotPresetDefinition:
    preset_id: str
    display_name: str
    supported_scene_count: list[int]
    override_policy: ShotOverridePolicy
    shot_distribution_rules: dict[str, Any]
    opening_rules: list[str] = field(default_factory=list)
    closing_rules: list[str] = field(default_factory=list)
    transition_rules: list[str] = field(default_factory=list)
    purpose_bias: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedContentMode:
    mode: ContentMode
    selection_source: Literal["forced_mode", "user_selected", "classifier", "fallback_mode"]


@dataclass(frozen=True)
class ResolvedShotPreset:
    preset_id: str
    selection_source: Literal["user_selected", "auto_selected", "fallback_substituted"]


@dataclass(frozen=True)
class FramePlan:
    scene_id: str
    knowledge_goal: str = ""
    shot_type: str = ""
    shot_purpose: str = ""
    primary_subject: str = ""
    secondary_subjects: list[str] = field(default_factory=list)
    world_elements: list[str] = field(default_factory=list)
    focus_detail: str = ""
    prompt_intent: str = ""
    frame_source: FrameSource = "planner_generated"
    locked_fields: list[str] = field(default_factory=list)
    override_source: Optional[str] = None

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "knowledge_goal": self.knowledge_goal,
            "shot_type": self.shot_type,
            "shot_purpose": self.shot_purpose,
            "primary_subject": self.primary_subject,
            "secondary_subjects": self.secondary_subjects,
            "world_elements": self.world_elements,
            "focus_detail": self.focus_detail,
            "prompt_intent": self.prompt_intent,
            "frame_source": self.frame_source,
            "locked_fields": self.locked_fields,
            "override_source": self.override_source,
        }


@dataclass(frozen=True)
class StoryboardPlanningResult:
    world_preset: WorldPresetDefinition
    shot_preset: ShotPresetDefinition
    resolved_mode: ResolvedContentMode
    frame_plans: list[FramePlan]
    normalized_style: Optional[dict[str, Any]]
    snapshot: dict[str, Any]
```

```python
# pixelle_video/config/storyboard_preset_library.py
def build_builtin_world_preset_library_dict() -> dict[str, Any]:
    return {
        "default_world_preset_id": "neutral_knowledge_storyboard",
        "items": [
            {
                "preset_id": "neutral_knowledge_storyboard",
                "display_name": "Neutral Knowledge Storyboard",
                "supported_modes": ["theme_mapping", "concept_explainer"],
                "forced_mode": None,
                "conservative_fallback_mode": "concept_explainer",
                "safe_default": True,
                "style_core": "clear educational illustration language",
                "world_elements": ["map boards", "scrolls", "knowledge props"],
                "default_shot_preset_ids": ["balanced_explainer", "detail_focus"],
                "cast_slots_by_mode": {
                    "theme_mapping": {"subject_lead": {"semantic_role": "mapped canonical lead"}},
                    "concept_explainer": {"host_explainer": {"semantic_role": "stable explainer"}},
                },
            },
        ],
    }


def build_builtin_shot_preset_library_dict() -> dict[str, Any]:
    return {
        "default_shot_preset_id": "balanced_explainer",
        "items": [
            {
                "preset_id": "balanced_explainer",
                "display_name": "Balanced Explainer",
                "supported_scene_count": [3, 4, 5, 6, 7, 8],
                "override_policy": "adaptive",
                "shot_distribution_rules": {"min_distinct_shots": 3, "max_consecutive_same": 2},
                "opening_rules": ["start_with_world_or_subject_context"],
                "closing_rules": ["end_with_summary_or_emphasis"],
            },
        ],
    }


def lookup_world_preset(*, requested_world_preset_id: str | None) -> dict[str, Any]:
    library = build_builtin_world_preset_library_dict()
    target_id = requested_world_preset_id or library["default_world_preset_id"]
    return next(item for item in library["items"] if item["preset_id"] == target_id)


def load_shot_preset_map() -> dict[str, dict[str, Any]]:
    library = build_builtin_shot_preset_library_dict()
    return {item["preset_id"]: item for item in library["items"]}
```

```python
# pixelle_video/config/schema.py
class StoryboardWorldPresetLibraryConfig(BaseModel):
    default_world_preset_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class StoryboardShotPresetLibraryConfig(BaseModel):
    default_shot_preset_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class StoryboardSubConfig(BaseModel):
    world_preset_library: StoryboardWorldPresetLibraryConfig = Field(
        default_factory=lambda: StoryboardWorldPresetLibraryConfig.model_validate(
            build_builtin_world_preset_library_dict()
        )
    )
    shot_preset_library: StoryboardShotPresetLibraryConfig = Field(
        default_factory=lambda: StoryboardShotPresetLibraryConfig.model_validate(
            build_builtin_shot_preset_library_dict()
        )
    )


class PixelleVideoConfig(BaseModel):
    project_name: str = Field(default="Pixelle-Video", description="Project name")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    template: TemplateConfig = Field(default_factory=TemplateConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    storyboard: StoryboardSubConfig = Field(default_factory=StoryboardSubConfig)
```

```python
# pixelle_video/config/manager.py
def get_storyboard_world_preset_library(self) -> dict:
    return self.config.storyboard.world_preset_library.model_dump()


def get_storyboard_shot_preset_library(self) -> dict:
    return self.config.storyboard.shot_preset_library.model_dump()
```

- [ ] **Step 4: Run tests to verify the contracts pass**

Run: `uv run pytest tests/test_storyboard_preset_library.py -v`

Expected: PASS with the neutral safe-default world preset and balanced-explainer shot preset available through config defaults.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/storyboard_planning.py pixelle_video/config/storyboard_preset_library.py pixelle_video/config/schema.py pixelle_video/config/manager.py tests/test_storyboard_preset_library.py
git commit -m "feat: add storyboard preset library contracts"
```

### Task 2: Implement routing, default resolution, and consistency repair

**Files:**
- Create: `pixelle_video/prompts/storyboard_planning.py`
- Create: `pixelle_video/services/storyboard_consistency.py`
- Create: `pixelle_video/services/storyboard_planner.py`
- Test: `tests/test_storyboard_planner.py`

- [ ] **Step 1: Write the failing planner tests**

```python
# tests/test_storyboard_planner.py
import pytest

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.services.storyboard_planner import (
    resolve_content_mode,
    resolve_role_strategy,
    resolve_shot_preset,
)
from pixelle_video.services.storyboard_consistency import apply_frame_overrides, repair_frame_plan_shots


def _neutral_world():
    return {
        "preset_id": "neutral_knowledge_storyboard",
        "supported_modes": ("theme_mapping", "concept_explainer"),
        "forced_mode": None,
        "conservative_fallback_mode": "concept_explainer",
        "default_shot_preset_ids": ("balanced_explainer",),
    }


def test_resolve_content_mode_prefers_forced_mode_before_classifier():
    resolved = resolve_content_mode(
        user_mode=None,
        classifier_result={"mode": "theme_mapping", "confidence": 0.95},
        world_preset={**_neutral_world(), "forced_mode": "concept_explainer"},
        default_threshold=0.70,
    )

    assert resolved.mode == "concept_explainer"
    assert resolved.selection_source == "forced_mode"


def test_conflicting_role_strategy_raises_configuration_error():
    with pytest.raises(ValueError, match="role strategy"):
        resolve_role_strategy(
            resolved_mode="theme_mapping",
            role_strategy="stable_explainer_cast",
        )


def test_resolve_shot_preset_uses_first_scene_count_match():
    resolved = resolve_shot_preset(
        requested_preset_id=None,
        scene_count=5,
        world_preset_default_ids=("detail_focus", "balanced_explainer"),
        available_presets={
            "detail_focus": {"supported_scene_count": (3,)},
            "balanced_explainer": {"supported_scene_count": (5, 6)},
        },
    )

    assert resolved.preset_id == "balanced_explainer"
    assert resolved.selection_source == "auto_selected"


def test_repair_frame_plan_shots_breaks_three_consecutive_medium_shots():
    plans = [
        FramePlan(scene_id="1", shot_type="medium_shot", shot_purpose="context", prompt_intent="a"),
        FramePlan(scene_id="2", shot_type="medium_shot", shot_purpose="explain", prompt_intent="b"),
        FramePlan(scene_id="3", shot_type="medium_shot", shot_purpose="detail", prompt_intent="c"),
    ]

    repaired = repair_frame_plan_shots(
        frame_plans=plans,
        shot_rules={"max_consecutive_same": 2, "min_distinct_shots": 2},
    )

    assert [plan.shot_type for plan in repaired] != ["medium_shot", "medium_shot", "medium_shot"]


def test_apply_frame_overrides_locks_requested_fields_on_one_frame():
    plans = [
        FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening"),
        FramePlan(scene_id="2", shot_type="medium_shot", prompt_intent="explain"),
    ]

    overridden = apply_frame_overrides(
        frame_plans=plans,
        frame_overrides=[
            {
                "scene_id": "2",
                "locked_fields": ["shot_type"],
                "shot_type": "close_up",
                "override_source": "user_preview",
            }
        ],
    )

    assert overridden[1].shot_type == "close_up"
    assert overridden[1].locked_fields == ["shot_type"]
    assert overridden[1].override_source == "user_preview"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storyboard_planner.py -v`

Expected: FAIL with import errors because the planner/consistency services and `FramePlan` model do not exist yet.

- [ ] **Step 3: Implement the planner contracts**

```python
# pixelle_video/prompts/storyboard_planning.py
import json

from pixelle_video.models.storyboard_planning import FramePlan


def build_storyboard_planning_prompt(
    narrations: list[str],
    *,
    world_preset: dict[str, Any],
    shot_preset: dict[str, Any],
    resolved_mode: str,
    consistency_strength: str,
) -> str:
    return json.dumps(
        {
            "task": "plan_storyboard_frames",
            "resolved_mode": resolved_mode,
            "consistency_strength": consistency_strength,
            "world_preset": world_preset,
            "shot_preset": shot_preset,
            "narrations": narrations,
            "required_output": {
                "frames": [
                    "scene_id",
                    "knowledge_goal",
                    "shot_type",
                    "shot_purpose",
                    "primary_subject",
                    "world_elements",
                    "focus_detail",
                    "prompt_intent",
                ]
            },
        },
        ensure_ascii=False,
    )


def parse_storyboard_frames(raw_response: str) -> list[FramePlan]:
    payload = json.loads(raw_response)
    return [
        FramePlan(
            scene_id=str(frame["scene_id"]),
            knowledge_goal=frame.get("knowledge_goal", ""),
            shot_type=frame.get("shot_type", ""),
            shot_purpose=frame.get("shot_purpose", ""),
            primary_subject=frame.get("primary_subject", ""),
            secondary_subjects=frame.get("secondary_subjects", []),
            world_elements=frame.get("world_elements", []),
            focus_detail=frame.get("focus_detail", ""),
            prompt_intent=frame.get("prompt_intent", ""),
        )
        for frame in payload.get("frames", [])
    ]
```

```python
# pixelle_video/services/storyboard_planner.py
from pixelle_video.models.storyboard_planning import ResolvedContentMode, ResolvedShotPreset


def resolve_content_mode(*, user_mode, classifier_result, world_preset, default_threshold):
    if world_preset.get("forced_mode"):
        return ResolvedContentMode(mode=world_preset["forced_mode"], selection_source="forced_mode")
    if user_mode:
        return ResolvedContentMode(mode=user_mode, selection_source="user_selected")
    confidence = float(classifier_result.get("confidence", 0.0))
    if confidence >= default_threshold:
        return ResolvedContentMode(mode=classifier_result["mode"], selection_source="classifier")
    return ResolvedContentMode(
        mode=world_preset["conservative_fallback_mode"],
        selection_source="fallback_mode",
    )


def resolve_role_strategy(*, resolved_mode: str, role_strategy: str | None) -> str:
    strategy = role_strategy or "auto"
    if strategy == "auto":
        return "theme_mapping" if resolved_mode == "theme_mapping" else "stable_explainer_cast"
    if strategy == "theme_mapping" and resolved_mode != "theme_mapping":
        raise ValueError("role strategy conflicts with resolved content mode")
    if strategy == "stable_explainer_cast" and resolved_mode != "concept_explainer":
        raise ValueError("role strategy conflicts with resolved content mode")
    return strategy


def resolve_shot_preset(*, requested_preset_id, scene_count, world_preset_default_ids, available_presets):
    if requested_preset_id:
        return ResolvedShotPreset(preset_id=requested_preset_id, selection_source="user_selected")
    for preset_id in world_preset_default_ids:
        supported = tuple(available_presets[preset_id]["supported_scene_count"])
        if scene_count in supported:
            return ResolvedShotPreset(preset_id=preset_id, selection_source="auto_selected")
    return ResolvedShotPreset(preset_id="balanced_explainer", selection_source="fallback_substituted")


async def plan_storyboard_batch(
    *,
    llm_service,
    narrations,
    image_config,
    prompt_prefix,
    world_preset_id,
    shot_preset_id,
    workflow,
    media_service,
    media_type,
    consistency_strength,
    content_mode,
    role_strategy,
    role_locking_strength,
    shot_strategy,
    frame_overrides=None,
):
    world_preset = lookup_world_preset(requested_world_preset_id=world_preset_id)
    resolved_mode = resolve_content_mode(
        user_mode=content_mode,
        classifier_result={"mode": "concept_explainer", "confidence": 0.0},
        world_preset=world_preset,
        default_threshold=0.70,
    )
    resolved_shot_preset = resolve_shot_preset(
        requested_preset_id=shot_preset_id,
        scene_count=len(narrations),
        world_preset_default_ids=world_preset["default_shot_preset_ids"],
        available_presets=load_shot_preset_map(),
    )
    planner_prompt = build_storyboard_planning_prompt(
        narrations=narrations,
        world_preset=world_preset,
        shot_preset=load_shot_preset_map()[resolved_shot_preset.preset_id],
        resolved_mode=resolved_mode.mode,
        consistency_strength=consistency_strength,
    )
    llm_response = await llm_service(prompt=planner_prompt, temperature=0.2, max_tokens=2400)
    frame_plans = parse_storyboard_frames(llm_response)
    frame_plans = apply_frame_overrides(
        frame_plans=frame_plans,
        frame_overrides=frame_overrides or [],
    )
    repaired_frame_plans = repair_frame_plan_shots(
        frame_plans=frame_plans,
        shot_rules=load_shot_preset_map()[resolved_shot_preset.preset_id]["shot_distribution_rules"],
    )
    return StoryboardPlanningResult(
        world_preset=WorldPresetDefinition(**world_preset),
        shot_preset=ShotPresetDefinition(**load_shot_preset_map()[resolved_shot_preset.preset_id]),
        resolved_mode=resolved_mode,
        frame_plans=repaired_frame_plans,
        normalized_style=None,
        snapshot={
            "world_preset_id": world_preset["preset_id"],
            "world_preset_selection_source": "user_selected" if world_preset_id else "safe_default",
            "requested_shot_preset_id": shot_preset_id,
            "effective_final_shot_preset": resolved_shot_preset.preset_id,
            "resolved_content_mode": resolved_mode.mode,
            "resolved_mode_selection_source": resolved_mode.selection_source,
            "selected_consistency_strength": consistency_strength,
            "resolved_role_strategy": resolve_role_strategy(
                resolved_mode=resolved_mode.mode,
                role_strategy=role_strategy,
            ),
            "selected_role_locking_strength": role_locking_strength,
            "selected_shot_strategy": shot_strategy,
            "frame_overrides": frame_overrides or [],
        },
    )
```

```python
# pixelle_video/services/storyboard_consistency.py
from dataclasses import replace


def apply_frame_overrides(*, frame_plans, frame_overrides):
    plan_by_scene_id = {plan.scene_id: plan for plan in frame_plans}
    for override in frame_overrides:
        original = plan_by_scene_id[override["scene_id"]]
        replacement_values = {
            field_name: override[field_name]
            for field_name in override.get("locked_fields", [])
            if field_name in override
        }
        replacement_values["locked_fields"] = override.get("locked_fields", [])
        replacement_values["override_source"] = override.get("override_source", "user_preview")
        replacement_values["frame_source"] = "user_locked"
        plan_by_scene_id[override["scene_id"]] = replace(original, **replacement_values)
    return [plan_by_scene_id[plan.scene_id] for plan in frame_plans]


def repair_frame_plan_shots(*, frame_plans, shot_rules):
    repaired = list(frame_plans)
    max_consecutive_same = int(shot_rules["max_consecutive_same"])
    for index in range(max_consecutive_same, len(repaired)):
        window = repaired[index - max_consecutive_same:index + 1]
        if len({plan.shot_type for plan in window}) == 1:
            repaired[index] = replace(repaired[index], shot_type="close_up", frame_source="repair_adjusted")
    return repaired
```

- [ ] **Step 4: Run tests to verify the planner rules pass**

Run: `uv run pytest tests/test_storyboard_planner.py -v`

Expected: PASS with deterministic mode resolution, conflict reporting, shot defaulting, and repair behavior.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/prompts/storyboard_planning.py pixelle_video/services/storyboard_consistency.py pixelle_video/services/storyboard_planner.py tests/test_storyboard_planner.py
git commit -m "feat: add storyboard planner and consistency repair"
```

### Task 3: Assemble prompts from frame plans with normalized style precedence

**Files:**
- Modify: `pixelle_video/models/style_resolution.py`
- Modify: `pixelle_video/utils/style_resolution.py`
- Modify: `pixelle_video/utils/prompt_helper.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Test: `tests/test_storyboard_prompt_builder.py`
- Modify: `tests/test_styled_image_prompt_batch.py`

- [ ] **Step 1: Write the failing prompt-assembly tests**

```python
# tests/test_storyboard_prompt_builder.py
from pixelle_video.utils.prompt_helper import assemble_storyboard_prompt


def test_assemble_storyboard_prompt_prefers_world_identity_over_conflicting_ip_prefix():
    prompt = assemble_storyboard_prompt(
        base_prompt="Liu Bei studies a strategy scroll",
        frame_plan={
            "shot_type": "medium_shot",
            "shot_purpose": "character_relationship",
            "world_elements": ["camp flag", "strategy board"],
        },
        world_preset={
            "display_name": "Angry Birds Three Kingdoms",
            "style_core": "playful bird-world history illustration",
        },
        normalized_style={
            "classification": "conflicting_world_override",
            "visual_suffix": "dramatic rim light only",
        },
    )

    assert "Angry Birds Three Kingdoms" in prompt
    assert "dramatic rim light only" in prompt
    assert "different ip world" not in prompt


def test_assemble_storyboard_prompt_includes_shot_language_and_world_elements():
    prompt = assemble_storyboard_prompt(
        base_prompt="host explainer introduces penicillin",
        frame_plan={
            "shot_type": "close_up",
            "shot_purpose": "detail_focus",
            "world_elements": ["lab bench", "culture dish"],
        },
        world_preset={"display_name": "Neutral Knowledge Storyboard", "style_core": "clean educational illustration"},
        normalized_style=None,
    )

    assert "close_up" in prompt
    assert "lab bench" in prompt
    assert "culture dish" in prompt
```

```python
# tests/test_styled_image_prompt_batch.py
from pixelle_video.models.storyboard_planning import FramePlan


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_returns_planning_snapshot(monkeypatch):
    async def fake_generate_image_prompts(**kwargs):
        return ["base scene prompt"]

    monkeypatch.setattr("pixelle_video.utils.content_generators.generate_image_prompts", fake_generate_image_prompts)
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        lambda **kwargs: type(
            "PlanResult",
            (),
            {
                "frame_plans": [
                    FramePlan(
                        scene_id="scene-1",
                        shot_type="medium_shot",
                        shot_purpose="context",
                        world_elements=["strategy board"],
                        prompt_intent="teach the first relationship",
                    )
                ],
                "world_preset": type(
                    "WorldPresetObj",
                    (),
                    {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                )(),
                "snapshot": {"world_preset_id": "neutral_knowledge_storyboard"},
                "normalized_style": None,
            },
        )(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
    )

    assert result.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert result.prompts[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storyboard_prompt_builder.py tests/test_styled_image_prompt_batch.py -v`

Expected: FAIL because `assemble_storyboard_prompt`, `plan_storyboard_batch`, and `planning_snapshot` are not implemented yet.

- [ ] **Step 3: Implement planning-aware prompt assembly**

```python
# pixelle_video/models/style_resolution.py
@dataclass(frozen=True)
class StyledImagePromptBatch:
    prompts: list[str]
    negative_prompt: Optional[str]
    resolved_style: Optional[ResolvedStyleSpec]
    planning_snapshot: Optional[dict[str, Any]] = None
```

```python
# pixelle_video/utils/style_resolution.py
def normalize_style_for_world_preset(resolved_style, world_preset):
    if resolved_style is None:
        return None
    if resolved_style.style_kind == "ip_world" and world_preset:
        return {
            "classification": "conflicting_world_override",
            "visual_suffix": resolved_style.style_profile.get("lighting", ""),
        }
    return {
        "classification": "compatible_refinement",
        "visual_suffix": resolved_style.style_profile.get("consistency_anchor", ""),
    }
```

```python
# pixelle_video/utils/prompt_helper.py
def assemble_storyboard_prompt(*, base_prompt, frame_plan, world_preset, normalized_style):
    parts = [
        world_preset["display_name"],
        world_preset["style_core"],
        frame_plan["shot_type"],
        frame_plan["shot_purpose"],
        ", ".join(frame_plan.get("world_elements", [])),
        base_prompt,
    ]
    if normalized_style and normalized_style.get("visual_suffix"):
        parts.append(normalized_style["visual_suffix"])
    return ", ".join(part for part in parts if part)
```

```python
# pixelle_video/utils/content_generators.py
async def generate_styled_image_prompt_batch(
    llm_service,
    narrations: List[str],
    image_config,
    prompt_prefix: Optional[str] = None,
    world_preset_id: Optional[str] = None,
    shot_preset_id: Optional[str] = None,
    workflow: Optional[str] = None,
    media_service=None,
    media_type: Literal["image", "video"] = "image",
    min_words: int = 30,
    max_words: int = 60,
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
    consistency_strength: str = "standard",
    content_mode: Optional[str] = None,
    role_strategy: Optional[str] = None,
    role_locking_strength: str = "standard",
    shot_strategy: str = "adaptive",
    frame_overrides: Optional[list[dict[str, Any]]] = None,
) -> StyledImagePromptBatch:
    source = resolve_style_source(image_config, prompt_prefix_override=prompt_prefix)
    resolved_style = None
    style_profile = None

    if source is not None:
        try:
            resolved_style = await resolve_style_spec(llm_service, source)
            style_profile = resolved_style.style_profile
        except Exception:
            logger.exception("Style resolution failed, falling back to legacy prefix concatenation")

    planning = await plan_storyboard_batch(
        llm_service=llm_service,
        narrations=narrations,
        image_config=image_config,
        prompt_prefix=prompt_prefix,
        world_preset_id=world_preset_id,
        shot_preset_id=shot_preset_id,
        workflow=workflow,
        media_service=media_service,
        media_type=media_type,
        consistency_strength=consistency_strength,
        content_mode=content_mode,
        role_strategy=role_strategy,
        role_locking_strength=role_locking_strength,
        shot_strategy=shot_strategy,
        frame_overrides=frame_overrides,
    )

    prompt_generator = generate_video_prompts if media_type == "video" else generate_image_prompts
    base_prompts = await prompt_generator(
        llm_service=llm_service,
        narrations=narrations,
        min_words=min_words,
        max_words=max_words,
        batch_size=batch_size,
        max_retries=max_retries,
        progress_callback=progress_callback,
        style_profile=style_profile,
    )

    capabilities = WorkflowCapabilities()
    if media_service is not None:
        capabilities = get_media_workflow_capabilities(
            media_service,
            workflow=workflow,
            media_type=media_type,
        )

    final_prompts = [
        assemble_storyboard_prompt(
            base_prompt=base_prompt,
            frame_plan=planning.frame_plans[index].to_prompt_dict(),
            world_preset={
                "display_name": planning.world_preset.display_name,
                "style_core": planning.world_preset.style_core,
            },
            normalized_style=planning.normalized_style,
        )
        for index, base_prompt in enumerate(base_prompts)
    ]
    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=capabilities.supports_negative_prompt,
    )
    return StyledImagePromptBatch(
        prompts=final_prompts,
        negative_prompt=negative_prompt,
        resolved_style=resolved_style,
        planning_snapshot=planning.snapshot,
    )
```

- [ ] **Step 4: Run tests to verify the shared batch helper now respects planning**

Run: `uv run pytest tests/test_storyboard_prompt_builder.py tests/test_styled_image_prompt_batch.py -v`

Expected: PASS with prompt assembly driven by resolved world identity, frame shot language, and replayable planning snapshot data.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/style_resolution.py pixelle_video/utils/style_resolution.py pixelle_video/utils/prompt_helper.py pixelle_video/utils/content_generators.py tests/test_storyboard_prompt_builder.py tests/test_styled_image_prompt_batch.py
git commit -m "feat: assemble prompts from storyboard plans"
```

### Task 4: Persist planning snapshots through storyboards and pipelines

**Files:**
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `pixelle_video/services/history_manager.py`
- Create: `tests/test_storyboard_snapshot_persistence.py`
- Modify: `tests/test_standard_pipeline_prompt_prefix.py`
- Modify: `tests/test_custom_pipeline_styled_batch.py`

- [ ] **Step 1: Write the failing snapshot/pipeline tests**

```python
# tests/test_storyboard_snapshot_persistence.py
from datetime import datetime

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.persistence import PersistenceService


def test_persistence_round_trips_storyboard_planning_snapshot(tmp_path):
    service = PersistenceService(output_dir=str(tmp_path))
    storyboard = Storyboard(
        title="demo",
        config=StoryboardConfig(
            task_id="task-1",
            media_width=1080,
            media_height=1920,
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            content_mode="concept_explainer",
            consistency_strength="strong",
        ),
        frames=[
            StoryboardFrame(
                index=0,
                narration="scene one",
                image_prompt="prompt one",
                shot_type="medium_shot",
                shot_purpose="context",
                frame_source="planner_generated",
                created_at=datetime.now(),
            )
        ],
        planning_snapshot={
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "resolved_content_mode": "concept_explainer",
        },
    )

    import asyncio
    asyncio.run(service.save_storyboard("task-1", storyboard))
    loaded = asyncio.run(service.load_storyboard("task-1"))

    assert loaded.config.world_preset_id == "neutral_knowledge_storyboard"
    assert loaded.frames[0].frame_source == "planner_generated"
    assert loaded.planning_snapshot["shot_preset_id"] == "balanced_explainer"
```

```python
# tests/test_standard_pipeline_prompt_prefix.py
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class _DummyCore:
    def __init__(self, config: dict):
        self.config = config
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_stores_planning_snapshot(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return StyledImagePromptBatch(
            prompts=["planned prompt"],
            negative_prompt="photo realism",
            resolved_style=None,
            planning_snapshot={
                "world_preset_id": "neutral_knowledge_storyboard",
                "shot_preset_id": "balanced_explainer",
            },
        )

    monkeypatch.setattr("pixelle_video.pipelines.standard.generate_styled_image_prompt_batch", fake_generate_styled_image_prompt_batch)
    pipeline = StandardPipeline(_DummyCore({"comfyui": {"image": {"prompt_prefix": "legacy"}}}))
    ctx = PipelineContext(
        input_text="topic",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert ctx.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
```

```python
# tests/test_custom_pipeline_styled_batch.py
from pathlib import Path

from pixelle_video.pipelines.custom import CustomPipeline


@pytest.mark.asyncio
async def test_custom_pipeline_threads_planning_snapshot(monkeypatch, tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    final_path = tmp_path / "final.mp4"

    class _FakeHTMLFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1024, 1024

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            Path(output).write_bytes(b"video")
            return output

    class _FakePersistence:
        async def save_task_metadata(self, task_id, metadata):
            return None

        async def save_storyboard(self, task_id, storyboard):
            return None

    class _FakeFrameProcessor:
        async def __call__(self, frame, storyboard, config, total_frames, progress_callback=None):
            frame.duration = 1.0
            segment_path = tmp_path / f"segment_{frame.index}.mp4"
            segment_path.write_bytes(b"segment")
            frame.video_segment_path = str(segment_path)
            return frame

    class _FakeCore:
        def __init__(self):
            self.config = {"template": {"default_template": "1080x1920/image_default.html"}}
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()
            self.frame_processor = _FakeFrameProcessor()
            self.persistence = _FakePersistence()

    async def fake_generate_title(*args, **kwargs):
        return "Custom Title"

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt="avoid realism",
            resolved_style=None,
            planning_snapshot={
                "world_preset_id": "neutral_knowledge_storyboard",
                "effective_final_shot_preset": "balanced_explainer",
            },
        )

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )
    monkeypatch.setattr("pixelle_video.utils.os_util.create_task_output_dir", lambda: (str(task_dir), "task-1"))
    monkeypatch.setattr("pixelle_video.utils.os_util.get_task_final_video_path", lambda task_id: str(final_path))
    monkeypatch.setattr("pixelle_video.utils.content_generators.generate_title", fake_generate_title)
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeHTMLFrameGenerator)
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda template_name: "image")
    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)

    pipeline = CustomPipeline(_FakeCore())
    result = await pipeline(text="scene one", tts_inference_mode="local")

    assert result.storyboard.planning_snapshot["effective_final_shot_preset"] == "balanced_explainer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_storyboard_snapshot_persistence.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py -v`

Expected: FAIL because storyboard/pipeline models do not yet expose planning fields or snapshot persistence.

- [ ] **Step 3: Thread planning metadata through storyboards and pipelines**

```python
# pixelle_video/models/storyboard.py
@dataclass
class StoryboardConfig:
    media_width: int
    media_height: int
    task_id: Optional[str] = None
    n_storyboard: int = 5
    min_narration_words: int = 5
    max_narration_words: int = 20
    min_image_prompt_words: int = 30
    max_image_prompt_words: int = 60
    video_fps: int = 30
    tts_inference_mode: str = "local"
    voice_id: Optional[str] = None
    tts_workflow: Optional[str] = None
    tts_speed: Optional[float] = None
    ref_audio: Optional[str] = None
    tts_batching_mode: str = "paragraph"
    tts_batch_max_sentences: int = 8
    tts_batch_max_chars: int = 220
    subtitle_alignment_engine: str = "qwen_forced_aligner"
    silence_trim_tool: Optional[str] = None
    silence_trim_margin_ms: int = 120
    render_backend: str = DEFAULT_RENDER_BACKEND
    media_workflow: Optional[str] = None
    media_negative_prompt: Optional[str] = None
    frame_template: str = "1080x1920/default.html"
    template_params: Optional[Dict[str, Any]] = None
    world_preset_id: Optional[str] = None
    shot_preset_id: Optional[str] = None
    content_mode: Optional[str] = None
    consistency_strength: Optional[str] = None
    role_strategy: Optional[str] = None
    role_locking_strength: Optional[str] = None
    shot_strategy: Optional[str] = None


@dataclass
class StoryboardFrame:
    index: int
    narration: str
    image_prompt: str
    audio_path: Optional[str] = None
    media_type: Optional[str] = None
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    composed_image_path: Optional[str] = None
    video_segment_path: Optional[str] = None
    duration: float = 0.0
    created_at: Optional[datetime] = None
    shot_type: Optional[str] = None
    shot_purpose: Optional[str] = None
    frame_source: Optional[str] = None


@dataclass
class Storyboard:
    title: str
    config: StoryboardConfig
    frames: List[StoryboardFrame] = field(default_factory=list)
    planning_snapshot: Optional[Dict[str, Any]] = None
```

```python
# pixelle_video/pipelines/linear.py
@dataclass
class PipelineContext:
    input_text: str
    params: Dict[str, Any]
    progress_callback: Optional[Callable[[ProgressEvent], None]] = None
    task_id: Optional[str] = None
    task_dir: Optional[str] = None
    title: Optional[str] = None
    narrations: List[str] = field(default_factory=list)
    image_prompts: List[Optional[str]] = field(default_factory=list)
    resolved_style: Optional[ResolvedStyleSpec] = None
    media_negative_prompt: Optional[str] = None
    timing_plan: Optional[TimingPlan] = None
    planning_snapshot: Optional[Dict[str, Any]] = None
    config: Optional[StoryboardConfig] = None
    storyboard: Optional[Storyboard] = None
    final_video_path: Optional[str] = None
    result: Optional[VideoGenerationResult] = None
```

```python
# pixelle_video/pipelines/standard.py
ctx.image_prompts = styled_batch.prompts
ctx.media_negative_prompt = styled_batch.negative_prompt
ctx.planning_snapshot = styled_batch.planning_snapshot
ctx.config = StoryboardConfig(
    task_id=ctx.task_id,
    n_storyboard=len(ctx.narrations),
    min_narration_words=ctx.params.get("min_narration_words", 5),
    max_narration_words=ctx.params.get("max_narration_words", 20),
    min_image_prompt_words=ctx.params.get("min_image_prompt_words", 30),
    max_image_prompt_words=ctx.params.get("max_image_prompt_words", 60),
    video_fps=ctx.params.get("video_fps", 30),
    tts_inference_mode=tts_inference_mode or "local",
    voice_id=final_voice_id,
    tts_workflow=final_tts_workflow,
    tts_speed=ctx.params.get("tts_speed", 1.2),
    ref_audio=ctx.params.get("ref_audio"),
    media_width=ctx.params.get("media_width"),
    media_height=ctx.params.get("media_height"),
    media_workflow=ctx.params.get("media_workflow"),
    media_negative_prompt=ctx.media_negative_prompt,
    frame_template=ctx.params.get("frame_template") or "1080x1920/default.html",
    template_params=ctx.params.get("template_params"),
    world_preset_id=(ctx.planning_snapshot or {}).get("world_preset_id"),
    shot_preset_id=(ctx.planning_snapshot or {}).get("effective_final_shot_preset"),
    content_mode=(ctx.planning_snapshot or {}).get("resolved_content_mode"),
    consistency_strength=(ctx.planning_snapshot or {}).get("selected_consistency_strength"),
    role_strategy=(ctx.planning_snapshot or {}).get("resolved_role_strategy"),
    role_locking_strength=(ctx.planning_snapshot or {}).get("selected_role_locking_strength"),
    shot_strategy=(ctx.planning_snapshot or {}).get("selected_shot_strategy"),
)
frame = StoryboardFrame(
    index=index,
    narration=narration,
    image_prompt=image_prompt,
    shot_type=frame_plan.get("shot_type"),
    shot_purpose=frame_plan.get("shot_purpose"),
    frame_source=frame_plan.get("frame_source"),
)
ctx.storyboard.planning_snapshot = ctx.planning_snapshot
```

```python
# pixelle_video/pipelines/custom.py
styled_batch = await generate_styled_image_prompt_batch(
    llm_service=self.llm,
    narrations=narrations,
    image_config=image_config,
    prompt_prefix=prompt_prefix,
    workflow=media_workflow,
    media_service=self.core.media,
    media_type=media_type,
    min_words=min_image_prompt_words,
    max_words=max_image_prompt_words,
)
image_prompts = styled_batch.prompts
media_negative_prompt = styled_batch.negative_prompt
planning_snapshot = styled_batch.planning_snapshot
storyboard.planning_snapshot = planning_snapshot
storyboard.config.world_preset_id = (planning_snapshot or {}).get("world_preset_id")
storyboard.config.shot_preset_id = (planning_snapshot or {}).get("effective_final_shot_preset")
```

```python
# pixelle_video/services/persistence.py
def _storyboard_to_dict(self, storyboard: Storyboard) -> Dict[str, Any]:
    return {
        "title": storyboard.title,
        "config": self._config_to_dict(storyboard.config),
        "frames": [self._frame_to_dict(frame) for frame in storyboard.frames],
        "content_metadata": self._content_metadata_to_dict(storyboard.content_metadata) if storyboard.content_metadata else None,
        "final_video_path": storyboard.final_video_path,
        "total_duration": storyboard.total_duration,
        "created_at": storyboard.created_at.isoformat() if storyboard.created_at else None,
        "completed_at": storyboard.completed_at.isoformat() if storyboard.completed_at else None,
        "planning_snapshot": storyboard.planning_snapshot,
    }


def _dict_to_storyboard(self, data: Dict[str, Any]) -> Storyboard:
    return Storyboard(
        title=data["title"],
        config=self._dict_to_config(data["config"]),
        frames=[self._dict_to_frame(frame_data) for frame_data in data["frames"]],
        content_metadata=self._dict_to_content_metadata(data["content_metadata"]) if data.get("content_metadata") else None,
        final_video_path=data.get("final_video_path"),
        total_duration=data.get("total_duration", 0.0),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        planning_snapshot=data.get("planning_snapshot"),
    )
```

```python
# pixelle_video/services/history_manager.py
async def get_task_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
    metadata = await self.persistence.load_task_metadata(task_id)
    if not metadata:
        return None

    storyboard = await self.persistence.load_storyboard(task_id)
    return {
        "metadata": metadata,
        "storyboard": storyboard,
        "planning_snapshot": getattr(storyboard, "planning_snapshot", None),
    }
```

- [ ] **Step 4: Run tests to verify snapshot persistence and pipeline threading pass**

Run: `uv run pytest tests/test_storyboard_snapshot_persistence.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py -v`

Expected: PASS with planning snapshot data surviving standard/custom pipeline execution and storyboard persistence.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/storyboard.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/custom.py pixelle_video/services/persistence.py pixelle_video/services/history_manager.py tests/test_storyboard_snapshot_persistence.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py
git commit -m "feat: persist storyboard planning snapshots"
```

### Task 5: Expose storyboard-planning controls across API, web preview, and history

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Modify: `api/schemas/content.py`
- Modify: `api/routers/content.py`
- Modify: `web/components/style_config.py`
- Create: `web/components/storyboard_preview.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/pages/2_📚_History.py`
- Modify: `web/i18n/en_US.json`
- Modify: `web/i18n/zh_CN.json`
- Modify: `tests/test_video_api.py`
- Modify: `tests/test_content_image_prompt_api.py`
- Modify: `tests/test_output_preview.py`
- Create: `tests/test_style_config_storyboard_planning_ui.py`
- Create: `tests/test_storyboard_preview_ui.py`

- [ ] **Step 1: Write the failing API/web/history tests**

```python
# tests/test_video_api.py
from types import SimpleNamespace

from api.routers.video import generate_video_sync
from api.schemas.video import VideoGenerateRequest


class _FakePixelleVideo:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate_video(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(video_path=__file__, duration=2.5)


@pytest.mark.asyncio
async def test_generate_video_sync_passes_storyboard_planning_fields(monkeypatch, tmp_path):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    fake_pixelle_video = _FakePixelleVideo()
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda template_path: template_path)

    await generate_video_sync(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            consistency_strength="strong",
            content_mode="concept_explainer",
            role_strategy="stable_explainer_cast",
            role_locking_strength="strong",
            shot_strategy="strict",
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    assert fake_pixelle_video.calls[0]["world_preset_id"] == "neutral_knowledge_storyboard"
    assert fake_pixelle_video.calls[0]["role_locking_strength"] == "strong"
    assert fake_pixelle_video.calls[0]["shot_strategy"] == "strict"
```

```python
# tests/test_output_preview.py
def test_build_single_generation_request_includes_storyboard_controls():
    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/image_default.html",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "stable_explainer_cast",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "frame_overrides": [{"scene_id": "1", "locked_fields": ["shot_type"], "shot_type": "close_up"}],
        },
        progress_callback=lambda event: None,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["world_preset_id"] == "neutral_knowledge_storyboard"
    assert request["shot_preset_id"] == "balanced_explainer"
    assert request["consistency_strength"] == "strong"
    assert request["role_locking_strength"] == "strong"
    assert request["frame_overrides"][0]["shot_type"] == "close_up"
```

```python
# tests/test_content_image_prompt_api.py
@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_passes_storyboard_controls(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["world_preset_id"] == "neutral_knowledge_storyboard"
        assert kwargs["shot_preset_id"] == "balanced_explainer"
        assert kwargs["content_mode"] == "concept_explainer"
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt="photo realism",
            resolved_style=None,
            planning_snapshot={"world_preset_id": "neutral_knowledge_storyboard"},
        )

    monkeypatch.setattr(
        "api.routers.content.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            content_mode="concept_explainer",
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
```

```python
# tests/test_style_config_storyboard_planning_ui.py
from pathlib import Path

from web.components import style_config


def test_build_storyboard_control_payload_marks_auto_selected_defaults():
    payload = style_config._build_storyboard_control_payload(
        selected_world_preset_id=None,
        selected_shot_preset_id=None,
        consistency_strength="standard",
    )

    assert payload["world_preset_id"] is None
    assert payload["shot_preset_id"] is None
    assert payload["consistency_strength"] == "standard"
    assert payload["role_locking_strength"] == "standard"


def test_history_page_references_storyboard_snapshot_fields():
    source = Path("web/pages/2_📚_History.py").read_text(encoding="utf-8")
    assert "world_preset_id" in source
    assert "shot_preset_id" in source
```

```python
# tests/test_storyboard_preview_ui.py
from web.components.storyboard_preview import build_frame_override_payload


def test_build_frame_override_payload_keeps_only_locked_fields():
    payload = build_frame_override_payload(
        scene_id="2",
        edited_fields={"shot_type": "close_up", "prompt_intent": "ignored"},
        locked_fields=["shot_type"],
        override_source="user_preview",
    )

    assert payload == {
        "scene_id": "2",
        "locked_fields": ["shot_type"],
        "shot_type": "close_up",
        "override_source": "user_preview",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_video_api.py tests/test_content_image_prompt_api.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py tests/test_storyboard_preview_ui.py -v`

Expected: FAIL because the new request fields and UI/history helpers do not exist yet.

- [ ] **Step 3: Add API, Streamlit, and history wiring**

```python
# api/schemas/video.py
# Add these fields directly below `prompt_prefix` inside `VideoGenerateRequest`.
world_preset_id: Optional[str] = Field(None, description="Storyboard world preset id")
shot_preset_id: Optional[str] = Field(None, description="Storyboard shot preset id")
consistency_strength: Optional[Literal["standard", "strong"]] = Field(None)
content_mode: Optional[Literal["theme_mapping", "concept_explainer"]] = Field(None)
role_strategy: Optional[Literal["auto", "theme_mapping", "stable_explainer_cast"]] = Field(None)
role_locking_strength: Optional[Literal["standard", "strong"]] = Field(None)
shot_strategy: Optional[Literal["adaptive", "strict"]] = Field(None)
frame_overrides: Optional[list[dict[str, Any]]] = Field(None, description="Optional storyboard frame overrides from preview UI")
```

```python
# api/routers/video.py
video_params.update(
    {
        "world_preset_id": request_body.world_preset_id,
        "shot_preset_id": request_body.shot_preset_id,
        "consistency_strength": request_body.consistency_strength,
        "content_mode": request_body.content_mode,
        "role_strategy": request_body.role_strategy,
        "role_locking_strength": request_body.role_locking_strength,
        "shot_strategy": request_body.shot_strategy,
        "frame_overrides": request_body.frame_overrides,
    }
)
```

```python
# api/schemas/content.py
# Add these fields under `workflow` inside `ImagePromptGenerateRequest`.
world_preset_id: Optional[str] = Field(None, description="Storyboard world preset id")
shot_preset_id: Optional[str] = Field(None, description="Storyboard shot preset id")
consistency_strength: Optional[Literal["standard", "strong"]] = Field(None)
content_mode: Optional[Literal["theme_mapping", "concept_explainer"]] = Field(None)
role_strategy: Optional[Literal["auto", "theme_mapping", "stable_explainer_cast"]] = Field(None)
role_locking_strength: Optional[Literal["standard", "strong"]] = Field(None)
shot_strategy: Optional[Literal["adaptive", "strict"]] = Field(None)
frame_overrides: Optional[list[dict[str, Any]]] = Field(None, description="Optional storyboard frame overrides from preview UI")
```

```python
# api/routers/content.py
batch = await generate_styled_image_prompt_batch(
    llm_service=pixelle_video.llm,
    narrations=request.narrations,
    image_config=image_config,
    prompt_prefix=request.prompt_prefix,
    workflow=request.workflow,
    media_service=pixelle_video.media,
    min_words=request.min_words,
    max_words=request.max_words,
    world_preset_id=request.world_preset_id,
    shot_preset_id=request.shot_preset_id,
    consistency_strength=request.consistency_strength,
    content_mode=request.content_mode,
    role_strategy=request.role_strategy,
    role_locking_strength=request.role_locking_strength,
    shot_strategy=request.shot_strategy,
    frame_overrides=request.frame_overrides,
)
```

```python
# web/components/style_config.py
def _build_storyboard_control_payload(*, selected_world_preset_id, selected_shot_preset_id, consistency_strength, content_mode=None, role_strategy="auto", role_locking_strength="standard", shot_strategy=None):
    return {
        "world_preset_id": selected_world_preset_id,
        "shot_preset_id": selected_shot_preset_id,
        "consistency_strength": consistency_strength,
        "content_mode": content_mode,
        "role_strategy": role_strategy,
        "role_locking_strength": role_locking_strength,
        "shot_strategy": shot_strategy,
    }


def render_style_config(pixelle_video):
    frame_overrides = render_storyboard_preview(
        narrations=st.session_state.get("generated_narrations", []),
        selected_world_preset_id=selected_world_preset_id,
        selected_shot_preset_id=selected_shot_preset_id,
        content_mode=content_mode,
    )
    storyboard_controls = _build_storyboard_control_payload(
        selected_world_preset_id=selected_world_preset_id,
        selected_shot_preset_id=selected_shot_preset_id,
        consistency_strength=consistency_strength,
        content_mode=content_mode,
        role_strategy=role_strategy,
        role_locking_strength=role_locking_strength,
        shot_strategy=shot_strategy,
    )
    return {
        "tts_inference_mode": tts_mode,
        "tts_voice": selected_voice if tts_mode == "local" else None,
        "tts_speed": tts_speed if tts_mode == "local" else None,
        "tts_workflow": tts_workflow_key if tts_mode == "comfyui" else None,
        "ref_audio": str(ref_audio_path) if ref_audio_path else None,
        "render_backend": render_backend,
        "frame_template": frame_template,
        "template_params": custom_values_for_video if custom_values_for_video else None,
        "media_workflow": workflow_key,
        "prompt_prefix": prompt_prefix if prompt_prefix else "",
        "media_width": media_width,
        "media_height": media_height,
        "frame_overrides": frame_overrides,
        **storyboard_controls,
    }
```

```python
# web/components/storyboard_preview.py
import streamlit as st


def render_storyboard_preview(*, narrations, selected_world_preset_id, selected_shot_preset_id, content_mode):
    if not narrations:
        return []

    overrides = []
    for index, narration in enumerate(narrations, start=1):
        with st.container(border=True):
            st.caption(f"Scene {index}: {narration}")
            shot_type = st.selectbox(
                f"Shot type {index}",
                options=["wide_shot", "medium_shot", "close_up", "detail_close_up"],
                index=1,
                key=f"storyboard_preview_shot_type_{index}",
            )
            locked_fields = st.multiselect(
                f"Locked fields {index}",
                options=["shot_type"],
                default=[],
                key=f"storyboard_preview_locked_fields_{index}",
            )
            if locked_fields:
                overrides.append(
                    build_frame_override_payload(
                        scene_id=str(index),
                        edited_fields={"shot_type": shot_type},
                        locked_fields=locked_fields,
                        override_source="user_preview",
                    )
                )
    return overrides


def build_frame_override_payload(*, scene_id, edited_fields, locked_fields, override_source):
    payload = {
        "scene_id": scene_id,
        "locked_fields": locked_fields,
        "override_source": override_source,
    }
    for field_name in locked_fields:
        payload[field_name] = edited_fields[field_name]
    return payload
```

```python
# web/components/output_preview.py
request.update(
    {
        "world_preset_id": video_params.get("world_preset_id"),
        "shot_preset_id": video_params.get("shot_preset_id"),
        "consistency_strength": video_params.get("consistency_strength"),
        "content_mode": video_params.get("content_mode"),
        "role_strategy": video_params.get("role_strategy"),
        "role_locking_strength": video_params.get("role_locking_strength"),
        "shot_strategy": video_params.get("shot_strategy"),
        "frame_overrides": video_params.get("frame_overrides"),
    }
)
```

```python
# web/pages/2_📚_History.py
snapshot = getattr(storyboard, "planning_snapshot", {}) or {}
st.markdown(f"**World preset:** {snapshot.get('world_preset_id', 'N/A')}")
st.markdown(f"**Shot preset:** {snapshot.get('effective_final_shot_preset', 'N/A')}")
st.markdown(f"**Mode:** {snapshot.get('resolved_content_mode', 'N/A')}")
st.markdown(f"**World selection:** {snapshot.get('world_preset_selection_source', 'N/A')}")
```

```json
// web/i18n/en_US.json
{
  "storyboard.world_preset": "World preset",
  "storyboard.shot_preset": "Shot rhythm template",
  "storyboard.role_locking_strength": "Role locking strength",
  "history.storyboard_snapshot": "Storyboard planning"
}
```

```json
// web/i18n/zh_CN.json
{
  "storyboard.world_preset": "世界预设",
  "storyboard.shot_preset": "镜头节奏模板",
  "storyboard.role_locking_strength": "角色锁定强度",
  "history.storyboard_snapshot": "分镜规划"
}
```

- [ ] **Step 4: Run tests to verify API/web/history wiring passes**

Run: `uv run pytest tests/test_video_api.py tests/test_content_image_prompt_api.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py tests/test_storyboard_preview_ui.py -v`

Expected: PASS with the new storyboard controls present in API requests, web generation payloads, and history UI source.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/video.py api/routers/video.py api/schemas/content.py api/routers/content.py web/components/style_config.py web/components/storyboard_preview.py web/components/output_preview.py web/pages/2_📚_History.py web/i18n/en_US.json web/i18n/zh_CN.json tests/test_video_api.py tests/test_content_image_prompt_api.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py tests/test_storyboard_preview_ui.py
git commit -m "feat: expose storyboard planning controls across api and web"
```

### Task 6: Run the focused regression sweep for the rollout

**Files:**
- Modify: none
- Test: `tests/test_storyboard_preset_library.py`
- Test: `tests/test_storyboard_planner.py`
- Test: `tests/test_storyboard_prompt_builder.py`
- Test: `tests/test_styled_image_prompt_batch.py`
- Test: `tests/test_storyboard_snapshot_persistence.py`
- Test: `tests/test_standard_pipeline_prompt_prefix.py`
- Test: `tests/test_custom_pipeline_styled_batch.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_content_image_prompt_api.py`
- Test: `tests/test_output_preview.py`
- Test: `tests/test_style_config_storyboard_planning_ui.py`
- Test: `tests/test_storyboard_preview_ui.py`

- [ ] **Step 1: Run the backend regression suite**

Run:

```bash
uv run pytest tests/test_storyboard_preset_library.py tests/test_storyboard_planner.py tests/test_storyboard_prompt_builder.py tests/test_styled_image_prompt_batch.py tests/test_storyboard_snapshot_persistence.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py tests/test_storyboard_preview_ui.py -v
```

Expected: PASS with all planner, prompt, persistence, and pipeline regressions green.

- [ ] **Step 2: Run the API/web regression suite**

Run:

```bash
uv run pytest tests/test_video_api.py tests/test_content_image_prompt_api.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py tests/test_storyboard_preview_ui.py -v
```

Expected: PASS with API contract, request-builder, and UI helper coverage green.

- [ ] **Step 3: Manual smoke-check the web flow**

Run:

```bash
uv run streamlit run app.py
```

Expected:

- the middle column shows world preset, shot preset, and consistency controls
- leaving both presets empty still shows the neutral safe default in preview after auto-selection
- the preview can show auto-selected world/shot metadata before generation
- a generated task appears in History with the resolved world preset, shot preset, mode, and selection-source fields

- [ ] **Step 4: Final commit if the regression sweep required follow-up fixes**

```bash
git status --short
```

Expected: no changes; if follow-up fixes were required during the sweep, create one final atomic commit describing those regression fixes.
