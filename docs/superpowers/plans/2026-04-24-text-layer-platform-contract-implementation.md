# Text Layer Platform Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the phase-0 platform contract for Pixelle's text layer so `CreationPackage`, `TextRenderingPolicy`, `TextTrack`, `TextCue`, `RenderManifest`, and `TemplateRenderContext` can carry text-layer data without adding renderer behavior yet.

**Architecture:** Keep semantic planning artifacts in `pixelle_video.models.text_overlay` and `pixelle_video.models.creation_package`, and keep final render facts in `pixelle_video.models.render_package`. `RenderManifest` remains backward-compatible with `caption_cues`, while `TextTrack/TextCue` become the canonical text-layer contract that `TemplateRenderContext` can expose to HyperFrames in later phases.

**Tech Stack:** Python 3.12, dataclasses, immutable mapping wrappers, pytest, existing HyperFrames project service tests

---

Repository note: `AGENTS.md` forbids `git worktree`, so execute this plan on the current branch. For every task, stage only the files listed in that task, create an atomic commit, and push after the commit.

## File Structure

- Create: `pixelle_video/models/text_overlay.py`
  Owns `JSONValue`, immutable JSON helpers, `TextOverlayCandidate`, `TextOverlayPlan`, `TextRenderingPolicy`, and `build_text_rendering_policy(...)`.
- Create: `pixelle_video/models/creation_package.py`
  Owns the minimal phase-0 `CreationPackage` contract and serialization.
- Modify: `pixelle_video/models/render_package.py`
  Adds `TextTrack`, `TextCue`, and `RenderManifest.text_tracks/text_cues` while preserving `CaptionCue`.
- Modify: `pixelle_video/models/template_render_context.py`
  Adds `text_tracks` and `text_cues` to the compiled HyperFrames context.
- Modify: `pixelle_video/services/hyperframes_project_service.py`
  Carries text tracks/cues through `build_template_render_context(...)` and writes `text_tracks.json` diagnostics from the same manifest.
- Create: `tests/test_text_overlay_models.py`
  Tests policy normalization, immutable JSON helper behavior, and text overlay plan round trips.
- Create: `tests/test_creation_package.py`
  Tests `CreationPackage` round trips and empty `text_overlay_plan` compatibility.
- Modify: `tests/test_render_package_models.py`
  Tests `TextTrack/TextCue` serialization and old manifest compatibility.
- Modify: `tests/test_template_render_context.py`
  Tests context field exposure and text-layer values.
- Modify: `tests/test_hyperframes_project_service.py`
  Tests diagnostic `text_tracks.json` and context propagation through project service.

This plan intentionally stops before planner/compiler, UI, ASS burn-in, native prompt injection, and renderer adapters. Those are separate sub-projects from the approved spec.

### Task 1: Add text overlay policy and immutable JSON helpers

**Files:**
- Create: `pixelle_video/models/text_overlay.py`
- Create: `tests/test_text_overlay_models.py`

- [ ] **Step 1: Write the failing text overlay model tests**

Create `tests/test_text_overlay_models.py`:

```python
import pytest

from pixelle_video.models.text_overlay import (
    TextOverlayCandidate,
    TextOverlayPlan,
    TextRenderingPolicy,
    build_text_rendering_policy,
    freeze_json_value,
    thaw_json_value,
)


def test_text_rendering_policy_rejects_native_prompt_for_programmatic_only():
    with pytest.raises(ValueError, match="native_prompt"):
        TextRenderingPolicy(
            image_text_mode="programmatic_only",
            enabled_targets=("native_prompt",),
            density="medium",
            max_items_per_frame=2,
            allow_native_text_in_image=False,
            suppress_unplanned_embedded_text=True,
        )


def test_build_text_rendering_policy_normalizes_legacy_no_text_default():
    policy = build_text_rendering_policy(None, forbid_embedded_text_in_image=True)

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ()
    assert policy.allow_native_text_in_image is False
    assert policy.suppress_unplanned_embedded_text is True


def test_build_text_rendering_policy_maps_legacy_text_allowed_to_native_hint():
    policy = build_text_rendering_policy(None, forbid_embedded_text_in_image=False)

    assert policy.image_text_mode == "native_hint"
    assert policy.enabled_targets == ("native_prompt",)
    assert policy.allow_native_text_in_image is True
    assert policy.suppress_unplanned_embedded_text is True


def test_build_text_rendering_policy_uses_nested_request_and_adds_native_target():
    policy = build_text_rendering_policy(
        {
            "enabled": True,
            "mode": "hybrid",
            "renderer_targets": ["hyperframes"],
            "density": "high",
            "max_items_per_frame": 3,
        },
        forbid_embedded_text_in_image=True,
    )

    assert policy.image_text_mode == "hybrid"
    assert policy.enabled_targets == ("hyperframes", "native_prompt")
    assert policy.density == "high"
    assert policy.max_items_per_frame == 3
    assert policy.allow_native_text_in_image is True


def test_freeze_json_value_blocks_nested_mutation_and_thaws_to_plain_json():
    frozen = freeze_json_value({"layout": {"x": 10}, "items": ["a", {"b": True}]})

    with pytest.raises(TypeError):
        frozen["layout"]["x"] = 20

    assert thaw_json_value(frozen) == {"layout": {"x": 10}, "items": ["a", {"b": True}]}


def test_text_overlay_plan_round_trips_candidates_with_source_span():
    candidate = TextOverlayCandidate(
        id="candidate-1",
        text="重点词",
        role="keyword",
        suggested_slot="center",
        renderer_targets=("hyperframes",),
        importance=0.9,
        confidence=0.8,
        source={"kind": "narration", "frame_index": 0, "span": [0, 3]},
    )
    plan = TextOverlayPlan(
        candidates=(candidate,),
        source_summary={"narration_count": 1},
    )

    restored = TextOverlayPlan.from_dict(plan.to_dict())

    assert restored.version == "text_overlay_plan.v1"
    assert restored.candidates[0].text == "重点词"
    assert restored.candidates[0].renderer_targets == ("hyperframes",)
    assert restored.candidates[0].source["span"] == (0, 3)
    assert restored.to_dict()["candidates"][0]["source"]["span"] == [0, 3]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/test_text_overlay_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.models.text_overlay'`.

- [ ] **Step 3: Implement `pixelle_video/models/text_overlay.py`**

Create `pixelle_video/models/text_overlay.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
FrozenJSONValue = JSONPrimitive | tuple["FrozenJSONValue", ...] | Mapping[str, "FrozenJSONValue"]

_TEXT_MODES = {"suppress", "programmatic_only", "native_hint", "hybrid"}
_TARGETS = {"hyperframes", "html", "ass", "native_prompt", "python"}
_DENSITIES = {"low", "medium", "high"}


def freeze_json_value(value: Any) -> FrozenJSONValue:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def thaw_json_value(value: Any) -> JSONValue:
    if isinstance(value, Mapping):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]
    if isinstance(value, list):
        return [thaw_json_value(item) for item in value]
    return value


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    return freeze_json_value(dict(value or {}))


@dataclass(frozen=True)
class TextRenderingPolicy:
    version: str = "text_rendering_policy.v1"
    image_text_mode: str = "programmatic_only"
    enabled_targets: tuple[str, ...] = ()
    density: str = "medium"
    max_items_per_frame: int = 2
    allow_native_text_in_image: bool = False
    suppress_unplanned_embedded_text: bool = True

    def __post_init__(self) -> None:
        if self.image_text_mode not in _TEXT_MODES:
            raise ValueError(f"Unsupported image_text_mode: {self.image_text_mode}")
        if self.density not in _DENSITIES:
            raise ValueError(f"Unsupported text density: {self.density}")
        if self.max_items_per_frame < 0:
            raise ValueError("max_items_per_frame must be non-negative")
        unknown_targets = set(self.enabled_targets) - _TARGETS
        if unknown_targets:
            raise ValueError(f"Unsupported renderer targets: {sorted(unknown_targets)}")
        if self.image_text_mode in {"suppress", "programmatic_only"}:
            if "native_prompt" in self.enabled_targets:
                raise ValueError("native_prompt target is not allowed for suppress/programmatic_only")
            if self.allow_native_text_in_image:
                raise ValueError("allow_native_text_in_image must be false unless native hints are enabled")
        if not self.suppress_unplanned_embedded_text:
            raise ValueError("suppress_unplanned_embedded_text must remain true for phase-0 policy")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "image_text_mode": self.image_text_mode,
            "enabled_targets": list(self.enabled_targets),
            "density": self.density,
            "max_items_per_frame": self.max_items_per_frame,
            "allow_native_text_in_image": self.allow_native_text_in_image,
            "suppress_unplanned_embedded_text": self.suppress_unplanned_embedded_text,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextRenderingPolicy":
        return cls(
            version=str(data.get("version", "text_rendering_policy.v1")),
            image_text_mode=str(data.get("image_text_mode", "programmatic_only")),
            enabled_targets=tuple(data.get("enabled_targets", ())),
            density=str(data.get("density", "medium")),
            max_items_per_frame=int(data.get("max_items_per_frame", 2)),
            allow_native_text_in_image=bool(data.get("allow_native_text_in_image", False)),
            suppress_unplanned_embedded_text=bool(data.get("suppress_unplanned_embedded_text", True)),
        )


def build_text_rendering_policy(
    text_layer_request: Mapping[str, Any] | None,
    *,
    forbid_embedded_text_in_image: bool | None,
) -> TextRenderingPolicy:
    request = dict(text_layer_request or {})
    if not request:
        if forbid_embedded_text_in_image is False:
            return TextRenderingPolicy(
                image_text_mode="native_hint",
                enabled_targets=("native_prompt",),
                density="medium",
                max_items_per_frame=2,
                allow_native_text_in_image=True,
                suppress_unplanned_embedded_text=True,
            )
        return TextRenderingPolicy()

    mode = str(request.get("mode", "programmatic_only"))
    targets = tuple(str(target) for target in request.get("renderer_targets", ()))
    if mode in {"native_hint", "hybrid"} and "native_prompt" not in targets:
        targets = (*targets, "native_prompt")
    return TextRenderingPolicy(
        image_text_mode=mode,
        enabled_targets=targets,
        density=str(request.get("density", "medium")),
        max_items_per_frame=int(request.get("max_items_per_frame", 2)),
        allow_native_text_in_image=mode in {"native_hint", "hybrid"},
        suppress_unplanned_embedded_text=True,
    )


@dataclass(frozen=True)
class TextOverlayCandidate:
    id: str
    text: str
    role: str
    suggested_slot: str | None = None
    renderer_targets: tuple[str, ...] = ()
    importance: float = 0.0
    confidence: float = 0.0
    source: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "renderer_targets", tuple(self.renderer_targets))
        object.__setattr__(self, "source", _freeze_mapping(self.source))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "text": self.text,
            "role": self.role,
            "suggested_slot": self.suggested_slot,
            "renderer_targets": list(self.renderer_targets),
            "importance": self.importance,
            "confidence": self.confidence,
            "source": thaw_json_value(self.source),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextOverlayCandidate":
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            role=str(data["role"]),
            suggested_slot=data.get("suggested_slot"),
            renderer_targets=tuple(data.get("renderer_targets", ())),
            importance=float(data.get("importance", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            source=data.get("source", {}),
        )


@dataclass(frozen=True)
class TextOverlayPlan:
    version: str = "text_overlay_plan.v1"
    candidates: tuple[TextOverlayCandidate, ...] = ()
    source_summary: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "source_summary", _freeze_mapping(self.source_summary))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "source_summary": thaw_json_value(self.source_summary),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextOverlayPlan":
        return cls(
            version=str(data.get("version", "text_overlay_plan.v1")),
            candidates=tuple(
                TextOverlayCandidate.from_dict(item)
                for item in data.get("candidates", ())
            ),
            source_summary=data.get("source_summary", {}),
        )
```

- [ ] **Step 4: Run the text overlay tests and verify they pass**

Run: `uv run pytest tests/test_text_overlay_models.py -v`

Expected: PASS with 6 tests.

- [ ] **Step 5: Commit and push the text overlay contract**

```bash
git add pixelle_video/models/text_overlay.py tests/test_text_overlay_models.py
git commit -m "feat: add text overlay policy models"
git push origin dev
```

### Task 2: Add the minimal CreationPackage contract

**Files:**
- Create: `pixelle_video/models/creation_package.py`
- Create: `tests/test_creation_package.py`

- [ ] **Step 1: Write the failing CreationPackage tests**

Create `tests/test_creation_package.py`:

```python
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan


def test_creation_package_round_trips_empty_text_overlay_plan():
    package = CreationPackage(task_id="task-1")

    data = package.to_dict()
    restored = CreationPackage.from_dict(data)

    assert data["version"] == "creation_package.v1"
    assert data["text_overlay_plan"] is None
    assert restored.task_id == "task-1"
    assert restored.text_overlay_plan is None


def test_creation_package_round_trips_text_overlay_plan_and_freezes_maps():
    plan = TextOverlayPlan(
        candidates=(
            TextOverlayCandidate(
                id="candidate-1",
                text="标题",
                role="headline",
                suggested_slot="top_left",
                renderer_targets=("hyperframes",),
                source={"frame_index": 0},
            ),
        ),
        source_summary={"narration_count": 1},
    )
    package = CreationPackage(
        task_id="task-1",
        content_plan={"title": "demo"},
        text_overlay_plan=plan,
        render_plan={"template_id": "image_default"},
    )

    restored = CreationPackage.from_dict(package.to_dict())

    assert restored.content_plan["title"] == "demo"
    assert restored.text_overlay_plan.candidates[0].role == "headline"
    assert restored.render_plan["template_id"] == "image_default"
```

- [ ] **Step 2: Run the CreationPackage tests and verify they fail**

Run: `uv run pytest tests/test_creation_package.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'pixelle_video.models.creation_package'`.

- [ ] **Step 3: Implement `pixelle_video/models/creation_package.py`**

Create `pixelle_video/models/creation_package.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    JSONValue,
    TextOverlayPlan,
    freeze_json_value,
    thaw_json_value,
)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    return freeze_json_value(dict(value or {}))


@dataclass(frozen=True)
class CreationPackage:
    task_id: str
    version: str = "creation_package.v1"
    content_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    storyboard_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    style_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    prompt_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    audio_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    text_overlay_plan: TextOverlayPlan | None = None
    asset_manifest: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    render_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    observability_refs: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "content_plan",
            "storyboard_plan",
            "style_plan",
            "prompt_plan",
            "audio_plan",
            "asset_manifest",
            "render_plan",
            "observability_refs",
        ):
            object.__setattr__(self, field_name, _freeze_mapping(getattr(self, field_name)))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "task_id": self.task_id,
            "content_plan": thaw_json_value(self.content_plan),
            "storyboard_plan": thaw_json_value(self.storyboard_plan),
            "style_plan": thaw_json_value(self.style_plan),
            "prompt_plan": thaw_json_value(self.prompt_plan),
            "audio_plan": thaw_json_value(self.audio_plan),
            "text_overlay_plan": (
                self.text_overlay_plan.to_dict()
                if self.text_overlay_plan is not None
                else None
            ),
            "asset_manifest": thaw_json_value(self.asset_manifest),
            "render_plan": thaw_json_value(self.render_plan),
            "observability_refs": thaw_json_value(self.observability_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CreationPackage":
        raw_plan = data.get("text_overlay_plan")
        return cls(
            version=str(data.get("version", "creation_package.v1")),
            task_id=str(data["task_id"]),
            content_plan=data.get("content_plan", {}),
            storyboard_plan=data.get("storyboard_plan", {}),
            style_plan=data.get("style_plan", {}),
            prompt_plan=data.get("prompt_plan", {}),
            audio_plan=data.get("audio_plan", {}),
            text_overlay_plan=(
                TextOverlayPlan.from_dict(raw_plan)
                if isinstance(raw_plan, Mapping)
                else None
            ),
            asset_manifest=data.get("asset_manifest", {}),
            render_plan=data.get("render_plan", {}),
            observability_refs=data.get("observability_refs", {}),
        )
```

- [ ] **Step 4: Run the CreationPackage tests and verify they pass**

Run: `uv run pytest tests/test_creation_package.py tests/test_text_overlay_models.py -v`

Expected: PASS for all CreationPackage and text overlay tests.

- [ ] **Step 5: Commit and push the CreationPackage contract**

```bash
git add pixelle_video/models/creation_package.py tests/test_creation_package.py
git commit -m "feat: add creation package contract"
git push origin dev
```

### Task 3: Add TextTrack and TextCue to RenderManifest

**Files:**
- Modify: `pixelle_video/models/render_package.py`
- Modify: `tests/test_render_package_models.py`

- [ ] **Step 1: Write the failing RenderManifest text-layer tests**

Append these tests to `tests/test_render_package_models.py`:

```python
from pixelle_video.models.render_package import TextCue, TextTrack


def test_text_track_and_text_cue_round_trip_with_immutable_layout_and_source():
    cue = TextCue(
        id="cue-1",
        track_id="track-overlay",
        text="重点词",
        start=0.2,
        end=1.4,
        role="keyword",
        frame_indices=(0,),
        slot="center",
        layout={"x": 0.5, "y": 0.35, "tokens": ["重点词"]},
        style_profile="default",
        layer=5,
        priority=10,
        language="zh-CN",
        source={"kind": "text_overlay_plan", "candidate_id": "candidate-1"},
    )

    restored = TextCue.from_dict(cue.to_dict())

    assert restored.version == "text_cue.v1"
    assert restored.frame_indices == (0,)
    assert restored.layout["tokens"] == ("重点词",)
    assert restored.to_dict()["layout"]["tokens"] == ["重点词"]
    assert restored.source["candidate_id"] == "candidate-1"


def test_render_manifest_round_trips_text_tracks_and_text_cues_while_preserving_captions():
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_tracks=[
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="重点词轨",
                renderer_targets=("hyperframes",),
                style_profile="default",
                layer=5,
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="重点词",
                start=0.2,
                end=1.4,
                role="keyword",
                frame_indices=(0,),
                slot="center",
            )
        ],
        caption_cues=[
            CaptionCue(
                id="caption-1",
                text="字幕",
                start=0.0,
                end=1.0,
                frame_indices=[0],
            )
        ],
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.text_tracks[0].kind == "overlay"
    assert restored.text_cues[0].role == "keyword"
    assert restored.caption_cues[0].text == "字幕"


def test_render_manifest_from_old_payload_defaults_text_layer_to_empty_lists():
    payload = {
        "task_id": "task-old",
        "title": "demo",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "template_id": "image_default",
        "caption_cues": [],
    }

    restored = RenderManifest.from_dict(payload)

    assert restored.text_tracks == []
    assert restored.text_cues == []
```

- [ ] **Step 2: Run the RenderManifest tests and verify they fail**

Run: `uv run pytest tests/test_render_package_models.py -k "text_track or text_cue or old_payload" -v`

Expected: FAIL because `TextTrack`, `TextCue`, and `RenderManifest.text_tracks/text_cues` are not defined yet.

- [ ] **Step 3: Add `TextTrack` and `TextCue` to `render_package.py`**

In `pixelle_video/models/render_package.py`, update imports:

```python
from typing import Any, Dict, List, Mapping, Optional

from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    JSONValue,
    freeze_json_value,
    thaw_json_value,
)
```

Insert these dataclasses after `CaptionCue`:

```python
@dataclass(frozen=True)
class TextTrack:
    id: str
    kind: str
    name: str
    version: str = "text_track.v1"
    enabled: bool = True
    renderer_targets: tuple[str, ...] = ()
    style_profile: Optional[str] = None
    layer: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "renderer_targets", tuple(self.renderer_targets))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "enabled": self.enabled,
            "renderer_targets": list(self.renderer_targets),
            "style_profile": self.style_profile,
            "layer": self.layer,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextTrack":
        return cls(
            version=data.get("version", "text_track.v1"),
            id=data["id"],
            kind=data["kind"],
            name=data["name"],
            enabled=data.get("enabled", True),
            renderer_targets=tuple(data.get("renderer_targets", ())),
            style_profile=data.get("style_profile"),
            layer=data.get("layer", 0),
        )


@dataclass(frozen=True)
class TextCue:
    id: str
    track_id: str
    text: str
    start: float
    end: float
    role: str
    version: str = "text_cue.v1"
    frame_indices: tuple[int, ...] = ()
    slot: Optional[str] = None
    layout: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    style_profile: Optional[str] = None
    layer: int = 0
    priority: int = 0
    language: Optional[str] = None
    source: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("TextCue end must be greater than or equal to start")
        object.__setattr__(self, "frame_indices", tuple(self.frame_indices))
        object.__setattr__(self, "layout", freeze_json_value(dict(self.layout or {})))
        object.__setattr__(self, "source", freeze_json_value(dict(self.source or {})))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "track_id": self.track_id,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "role": self.role,
            "frame_indices": list(self.frame_indices),
            "slot": self.slot,
            "layout": thaw_json_value(self.layout),
            "style_profile": self.style_profile,
            "layer": self.layer,
            "priority": self.priority,
            "language": self.language,
            "source": thaw_json_value(self.source),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextCue":
        return cls(
            version=data.get("version", "text_cue.v1"),
            id=data["id"],
            track_id=data["track_id"],
            text=data["text"],
            start=data["start"],
            end=data["end"],
            role=data["role"],
            frame_indices=tuple(data.get("frame_indices", ())),
            slot=data.get("slot"),
            layout=data.get("layout", {}),
            style_profile=data.get("style_profile"),
            layer=data.get("layer", 0),
            priority=data.get("priority", 0),
            language=data.get("language"),
            source=data.get("source", {}),
        )
```

Extend `RenderManifest.__init__` with `text_tracks` and `text_cues`:

```python
        text_tracks: Optional[List[TextTrack]] = None,
        text_cues: Optional[List[TextCue]] = None,
```

Set the fields after `caption_cues`:

```python
        self.text_tracks = list(text_tracks or [])
        self.text_cues = list(text_cues or [])
```

Add these keys to `to_dict()` after `caption_cues`:

```python
            "text_tracks": [track.to_dict() for track in self.text_tracks],
            "text_cues": [cue.to_dict() for cue in self.text_cues],
```

Add these arguments to `from_dict(...)`:

```python
            text_tracks=[TextTrack.from_dict(item) for item in data.get("text_tracks", [])],
            text_cues=[TextCue.from_dict(item) for item in data.get("text_cues", [])],
```

- [ ] **Step 4: Run the render package tests and verify they pass**

Run: `uv run pytest tests/test_render_package_models.py tests/test_text_overlay_models.py -v`

Expected: PASS and existing `caption_cues` behavior remains unchanged.

- [ ] **Step 5: Commit and push the render manifest contract**

```bash
git add pixelle_video/models/render_package.py tests/test_render_package_models.py
git commit -m "feat: add text tracks to render manifest"
git push origin dev
```

### Task 4: Expose text tracks and cues through TemplateRenderContext

**Files:**
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `tests/test_template_render_context.py`
- Modify: `tests/test_hyperframes_project_service.py`

- [ ] **Step 1: Write failing TemplateRenderContext and HyperFrames project tests**

Append this test to `tests/test_template_render_context.py`:

```python
from pixelle_video.models.render_package import TextCue, TextTrack


def test_template_render_context_exposes_text_layer_fields():
    track = TextTrack(
        id="track-overlay",
        kind="overlay",
        name="重点词轨",
        renderer_targets=("hyperframes",),
    )
    cue = TextCue(
        id="cue-1",
        track_id="track-overlay",
        text="重点词",
        start=0.2,
        end=1.4,
        role="keyword",
        slot="center",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_tracks=[track],
        text_cues=[cue],
    )

    assert context.text_tracks[0].kind == "overlay"
    assert context.text_cues[0].text == "重点词"
```

Append this test to `tests/test_hyperframes_project_service.py`:

```python
from pixelle_video.models.render_package import TextCue, TextTrack


def test_write_project_data_writes_text_tracks_diagnostic_payload(tmp_path):
    manifest = RenderManifest(
        task_id="task-text",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_tracks=[
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="重点词轨",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="重点词",
                start=0.2,
                end=1.4,
                role="keyword",
                slot="center",
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project_data(manifest)

    text_tracks_path = project_paths.data_dir / "text_tracks.json"
    text_tracks_data = json.loads(text_tracks_path.read_text(encoding="utf-8"))
    manifest_data = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))

    assert text_tracks_path.exists()
    assert text_tracks_data["task_id"] == "task-text"
    assert text_tracks_data["text_tracks"][0]["kind"] == "overlay"
    assert text_tracks_data["text_cues"][0]["role"] == "keyword"
    assert manifest_data["text_tracks"][0]["id"] == "track-overlay"


def test_build_template_render_context_carries_text_layer_from_manifest():
    manifest = RenderManifest(
        task_id="task-context",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_tracks=[
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="重点词轨",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="重点词",
                start=0.2,
                end=1.4,
                role="keyword",
                slot="center",
            )
        ],
    )

    context = build_template_render_context(manifest, template_params={})

    assert context.text_tracks[0].id == "track-overlay"
    assert context.text_cues[0].slot == "center"
```

- [ ] **Step 2: Run the context/project tests and verify they fail**

Run: `uv run pytest tests/test_template_render_context.py tests/test_hyperframes_project_service.py -k "text_layer or text_tracks" -v`

Expected: FAIL because `TemplateRenderContext` and `HyperFramesProjectPaths` do not expose text-layer fields or diagnostics yet.

- [ ] **Step 3: Extend `TemplateRenderContext`**

Update `pixelle_video/models/template_render_context.py` imports:

```python
from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack, VisualClip
```

Add fields after `captions`:

```python
    text_tracks: List[TextTrack] = field(default_factory=list)
    text_cues: List[TextCue] = field(default_factory=list)
```

- [ ] **Step 4: Extend HyperFrames project service payloads**

Update `HyperFramesProjectPaths` in `pixelle_video/services/hyperframes_project_service.py` to include:

```python
    text_tracks_path: Path
```

Update `_build_project_paths(...)`:

```python
            text_tracks_path=data_dir / "text_tracks.json",
```

Update `build_template_render_context(...)` return:

```python
        text_tracks=list(manifest.text_tracks),
        text_cues=list(manifest.text_cues),
```

Add this helper near `_build_captions_payload(...)`:

```python
    def _build_text_tracks_payload(self, manifest: RenderManifest) -> dict:
        return {
            "task_id": manifest.task_id,
            "text_tracks": [track.to_dict() for track in manifest.text_tracks],
            "text_cues": [cue.to_dict() for cue in manifest.text_cues],
        }
```

Update `_write_diagnostic_payloads(...)`:

```python
        self._write_json(
            project_paths.text_tracks_path,
            self._build_text_tracks_payload(manifest),
        )
```

- [ ] **Step 5: Run focused context/project tests**

Run: `uv run pytest tests/test_template_render_context.py tests/test_hyperframes_project_service.py -k "text_layer or text_tracks" -v`

Expected: PASS for the new text-layer context and diagnostics tests.

- [ ] **Step 6: Run existing HyperFrames contract tests for regression coverage**

Run: `uv run pytest tests/test_template_render_context.py tests/test_hyperframes_project_service.py tests/test_hyperframes_compiler.py -v`

Expected: PASS. Existing caption compilation should remain unchanged because no renderer code reads `text_cues` yet.

- [ ] **Step 7: Commit and push context/diagnostic propagation**

```bash
git add pixelle_video/models/template_render_context.py pixelle_video/services/hyperframes_project_service.py tests/test_template_render_context.py tests/test_hyperframes_project_service.py
git commit -m "feat: expose text layer in template context"
git push origin dev
```

### Task 5: Final phase-0 verification and plan handoff

**Files:**
- Create: `pixelle_video/models/text_overlay.py`
- Create: `pixelle_video/models/creation_package.py`
- Modify: `pixelle_video/models/render_package.py`
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Create: `tests/test_text_overlay_models.py`
- Create: `tests/test_creation_package.py`
- Modify: `tests/test_render_package_models.py`
- Modify: `tests/test_template_render_context.py`
- Modify: `tests/test_hyperframes_project_service.py`

- [ ] **Step 1: Run the full phase-0 verification suite**

Run: `uv run pytest tests/test_text_overlay_models.py tests/test_creation_package.py tests/test_render_package_models.py tests/test_template_render_context.py tests/test_hyperframes_project_service.py tests/test_hyperframes_compiler.py -v`

Expected: PASS. This proves policy normalization, creation package serialization, render manifest compatibility, template context exposure, and HyperFrames project diagnostics are locked.

- [ ] **Step 2: Run import-level smoke checks**

Run: `uv run python -c "from pixelle_video.models.creation_package import CreationPackage; from pixelle_video.models.render_package import TextCue, TextTrack; from pixelle_video.models.text_overlay import TextRenderingPolicy; print(CreationPackage(task_id='smoke').version, TextTrack(id='t', kind='overlay', name='Overlay').version, TextCue(id='c', track_id='t', text='x', start=0, end=1, role='keyword').version, TextRenderingPolicy().version)"`

Expected output contains:

```text
creation_package.v1 text_track.v1 text_cue.v1 text_rendering_policy.v1
```

- [ ] **Step 3: Audit the final diff before closing phase 0**

Run:

```bash
git diff --stat
git diff -- pixelle_video/models/text_overlay.py pixelle_video/models/creation_package.py pixelle_video/models/render_package.py pixelle_video/models/template_render_context.py pixelle_video/services/hyperframes_project_service.py tests/test_text_overlay_models.py tests/test_creation_package.py tests/test_render_package_models.py tests/test_template_render_context.py tests/test_hyperframes_project_service.py
```

Expected: only phase-0 text-layer contract files are present. No planner/compiler, UI, ASS, prompt injection, or renderer behavior should appear in this diff.

- [ ] **Step 4: Commit and push any final verification-only fixes**

If Step 1 or Step 2 required a small correction, commit only the corrected phase-0 files:

```bash
git add pixelle_video/models/text_overlay.py pixelle_video/models/creation_package.py pixelle_video/models/render_package.py pixelle_video/models/template_render_context.py pixelle_video/services/hyperframes_project_service.py tests/test_text_overlay_models.py tests/test_creation_package.py tests/test_render_package_models.py tests/test_template_render_context.py tests/test_hyperframes_project_service.py
git commit -m "fix: stabilize text layer contract tests"
git push origin dev
```

If Step 1 and Step 2 already passed without changes, do not create an empty commit.

## Self-Review

**Spec coverage:** This plan covers the approved spec's phase-0 requirements: `CreationPackage`, `TextRenderingPolicy`, `TextTrack`, `TextCue`, `RenderManifest`, `TemplateRenderContext`, versioned serialization, old manifest compatibility, and text-layer diagnostic payloads. It intentionally excludes planner/compiler, native prompt projection, UI, ASS burn-in, and renderer adapters because the spec identifies them as later phases.

**Placeholder scan:** No step uses `TBD`, unspecified error handling, or unnamed tests. Every code-changing step includes concrete test or implementation snippets and exact commands.

**Type consistency:** `TextOverlayPlan`, `TextRenderingPolicy`, `TextTrack`, `TextCue`, and `CreationPackage` signatures match across tests and implementation steps. `TextTrack.kind` stays on tracks, and `TextCue.role` stays on cues.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-24-text-layer-platform-contract-implementation.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.
