# Text Rendering Contract v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified platform text rendering contract so Pixelle captions, overlays, HyperFrames text, HTML text, ASS burn-in, and native prompt hints use one shared, persisted `TextRenderPackage`.

**Architecture:** Keep the existing `TextRenderingPolicy -> TextOverlayPlan -> TextCueCompiler -> RenderManifest -> renderer adapters` direction, but insert `TextRenderPackage` as the canonical persisted fact source. Add `TextStyleProfile`, `CaptionRenderingSettings`, `TextLayoutPlan`, `TextStyleResolver`, and `TextRendererAdapter` so pipelines and renderers consume one contract instead of rebuilding text state locally.

**Tech Stack:** Python dataclasses, Pydantic API schemas, Streamlit UI, FFmpeg ASS subtitles, HyperFrames compiled HTML, pytest.

**Repository constraint:** Do not create or use `git worktree` in this repository. Execute this plan in the current workspace and stage only the files listed by each task.

---

## File Structure

- Create: `pixelle_video/models/text_render_package.py`
  - Owns `CaptionRenderingSettings`, `TextRenderPackage`, serialization, and compatibility defaults.
- Create: `pixelle_video/models/text_style.py`
  - Owns `TextStyleProfile`, color normalization, style profile serialization, default caption/overlay profiles.
- Create: `pixelle_video/models/text_layout.py`
  - Owns `TextLayoutPlan`, safe-area, wrapped-line, and layer metadata.
- Create: `pixelle_video/services/text_style_resolver.py`
  - Owns style lookup and fallback diagnostics for every renderer adapter.
- Create: `pixelle_video/services/text_rendering_orchestrator.py`
  - Builds text settings, text policy, style profiles, layout plan, `TextRenderPackage`, and disabled reasons for every pipeline.
- Create: `pixelle_video/services/text_content_sanitizer.py`
  - Produces safe display text before ASS/HTML/HyperFrames adapter projection.
- Create: `pixelle_video/services/text_layout_planner.py`
  - Produces shared wrapping, safe-area, and collision-avoidance intent before renderer adapters run.
- Create: `pixelle_video/services/text_renderer_adapter.py`
  - Defines `TextRendererAdapter`, `TextRenderExportResult`, and shared adapter diagnostics.
- Modify: `pixelle_video/models/render_package.py`
  - Adds `text_style_profiles` to `RenderManifest`.
- Modify: `pixelle_video/models/template_render_context.py`
  - Adds `text_style_profiles` to compiled HyperFrames context.
- Create: `pixelle_video/services/ass_style_builder.py`
  - Converts `TextStyleProfile` into ASS `Style:` lines.
- Create: `pixelle_video/services/font_resolver.py`
  - Resolves fontsdir and real font family names for ASS burn-in without exposing renderer fields to UI/API.
- Modify: `pixelle_video/services/ass_text_adapter.py`
  - Removes hardcoded styles and resolves styles from manifest profiles.
- Modify: `pixelle_video/services/video.py`
  - Burns ASS artifacts with ffmpeg `ass=...:fontsdir=...` and records fallback conditions.
- Modify: `pixelle_video/services/hyperframes_project_service.py`
  - Carries `text_style_profiles` through normalization, context building, and diagnostics.
- Modify: `pixelle_video/services/hyperframes_compiler.py`
  - Emits text style CSS variables for text cues.
- Modify: `pixelle_video/services/text_cue_compiler.py`
  - Assigns default caption/overlay style profile ids to tracks/cues.
- Modify: `api/schemas/text_rendering.py`
  - Adds user-facing style request schemas.
- Modify: `web/components/style_config.py`
  - Delegates text rendering controls to a focused component.
- Create: `web/components/text_rendering_config.py`
  - Adds Streamlit controls for caption style, overlay text layer, and image text policy as three sibling sections.
- Modify: `pixelle_video/pipelines/standard.py`
  - Calls the shared orchestrator and records separate caption/text-layer summaries.
- Modify: `pixelle_video/pipelines/custom.py`
  - Parses text rendering through the shared orchestrator and records unsupported renderer reasons.
- Modify: `pixelle_video/pipelines/asset_based.py`
  - Preserves caption styles and records overlay/image-text support state for user-asset pipelines.
- Test: `tests/test_text_style_models.py`
- Test: `tests/test_text_render_package_models.py`
- Test: `tests/test_text_content_sanitizer.py`
- Test: `tests/test_text_layout_planner.py`
- Test: `tests/test_text_renderer_adapter_contract.py`
- Test: `tests/test_text_style_resolver.py`
- Test: `tests/test_text_rendering_orchestrator.py`
- Test: `tests/test_ass_style_builder.py`
- Test: `tests/test_ass_text_adapter.py`
- Test: `tests/test_video_ass_burn_in.py`
- Test: `tests/test_render_package_models.py`
- Test: `tests/test_hyperframes_compiler.py`
- Test: `tests/test_hyperframes_project_service.py`
- Test: `tests/test_style_config_text_rendering_ui.py`
- Test: `tests/test_standard_pipeline_text_rendering_summary.py`
- Test: `tests/test_pipeline_text_rendering_contract.py`
- Test: `tests/test_text_rendering_golden_artifacts.py`
- Fixture: `tests/fixtures/text_rendering/text_render_package_legacy_caption.json`
- Fixture: `tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json`
- Fixture: `tests/fixtures/text_rendering/render_manifest_with_text_styles.json`

## Task 0: Freeze Canonical Text Rendering Package

**Files:**
- Create: `pixelle_video/models/text_render_package.py`
- Create: `pixelle_video/models/text_layout.py`
- Test: `tests/test_text_render_package_models.py`
- Test: `tests/test_text_rendering_golden_artifacts.py`
- Fixture: `tests/fixtures/text_rendering/text_render_package_legacy_caption.json`
- Fixture: `tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json`

- [x] **Step 1: Write failing package tests**

```python
from pixelle_video.models.text_render_package import (
    CaptionRenderingSettings,
    TextRenderPackage,
)
from pixelle_video.models.text_layout import TextLayoutPlan


def test_caption_settings_separate_caption_overlay_and_image_text():
    settings = CaptionRenderingSettings(
        enabled=True,
        source="narration_timing",
        style_profile="caption-default",
        punctuation_mode="strip_all",
        renderer_targets=("hyperframes", "ass"),
    )

    assert settings.enabled is True
    assert settings.style_profile == "caption-default"
    assert settings.renderer_targets == ("hyperframes", "ass")


def test_text_render_package_round_trips_with_version():
    package = TextRenderPackage(
        version="text_render_package.v1",
        task_id="task-1",
        caption_settings=CaptionRenderingSettings(),
        text_style_profiles=(),
        caption_cues=(),
        text_tracks=(),
        text_cues=(),
        layout_plan=TextLayoutPlan(),
        diagnostics={"disabled_reasons": []},
    )

    restored = TextRenderPackage.from_dict(package.to_dict())

    assert restored.version == "text_render_package.v1"
    assert restored.caption_settings.style_profile == "caption-default"
```

Add `tests/test_text_rendering_golden_artifacts.py`:

```python
import json
from pathlib import Path


FIXTURE_DIR = Path("tests/fixtures/text_rendering")


def test_text_render_package_golden_fixtures_are_versioned():
    for name in [
        "text_render_package_legacy_caption.json",
        "text_render_package_overlay_hybrid.json",
    ]:
        payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        assert payload["version"] == "text_render_package.v1"
        assert "caption_settings" in payload
        assert "text_style_profiles" in payload
```

- [x] **Step 2: Run package tests to verify they fail**

Run:

```bash
pytest tests/test_text_render_package_models.py tests/test_text_rendering_golden_artifacts.py -v
```

Expected: FAIL because `text_render_package.py` and golden fixtures do not exist.

- [x] **Step 3: Implement canonical package models**

Create `pixelle_video/models/text_render_package.py` with immutable dataclasses:

- `CaptionRenderingSettings(version, enabled, source, style_profile, punctuation_mode, renderer_targets)`
- `TextRenderPackage(version, task_id, caption_settings, text_style_profiles, caption_cues, text_tracks, text_cues, layout_plan, diagnostics)`
- `to_dict()` and `from_dict()` methods that accept missing v1 fields by applying defaults and recording compatibility diagnostics.

Create `pixelle_video/models/text_layout.py` with `TextLayoutPlan(version, safe_areas, wrapped_lines, collisions, diagnostics)` and serialization helpers. Keep layout as intent, not renderer CSS or ASS tags.

Do not import renderer services in this model file.

- [x] **Step 4: Add golden fixtures**

Create `tests/fixtures/text_rendering/text_render_package_legacy_caption.json` with one caption cue and no overlay cue. Create `tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json` with caption style, overlay style, one subtitle cue, one overlay cue, and one native hint diagnostic. Create `tests/fixtures/text_rendering/render_manifest_with_text_styles.json` as the derived manifest fixture used by ASS/HyperFrames adapter tests.

- [x] **Step 5: Run package tests**

Run:

```bash
pytest tests/test_text_render_package_models.py tests/test_text_rendering_golden_artifacts.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add pixelle_video/models/text_render_package.py pixelle_video/models/text_layout.py tests/test_text_render_package_models.py tests/test_text_rendering_golden_artifacts.py tests/fixtures/text_rendering/text_render_package_legacy_caption.json tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json tests/fixtures/text_rendering/render_manifest_with_text_styles.json
git commit -m "feat: add canonical text render package"
```

## Task 1: Add TextStyleProfile Contract

**Files:**
- Create: `pixelle_video/models/text_style.py`
- Test: `tests/test_text_style_models.py`

- [x] **Step 1: Write failing model tests**

Add tests covering serialization, defaults, color validation, opacity validation, and scale factor.

```python
import pytest

from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
    normalize_hex_color,
)


def test_text_style_profile_round_trips():
    profile = TextStyleProfile(
        id="caption-default",
        name="Caption Default",
        font_size=68,
        primary_color="#ffff00",
        stroke_color="#000000",
        background_color="#111111",
        background_opacity=0.35,
        margin_y=120,
    )

    restored = TextStyleProfile.from_dict(profile.to_dict())

    assert restored == TextStyleProfile(
        id="caption-default",
        name="Caption Default",
        font_size=68,
        primary_color="#FFFF00",
        stroke_color="#000000",
        background_color="#111111",
        background_opacity=0.35,
        margin_y=120,
    )


def test_normalize_hex_color_rejects_invalid_values():
    with pytest.raises(ValueError, match="hex color"):
        normalize_hex_color("yellow")


def test_text_style_profile_rejects_invalid_opacity():
    with pytest.raises(ValueError, match="background_opacity"):
        TextStyleProfile(id="bad", name="Bad", background_opacity=1.5)


def test_default_text_style_profiles_include_caption_default():
    profiles = build_default_text_style_profiles()

    assert profiles[0].id == DEFAULT_CAPTION_STYLE_ID
    assert profiles[0].position == "bottom"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_text_style_models.py -v
```

Expected: FAIL because `pixelle_video.models.text_style` does not exist.

- [x] **Step 3: Implement text style model**

Create `pixelle_video/models/text_style.py` with:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

DEFAULT_CAPTION_STYLE_ID = "caption-default"
DEFAULT_OVERLAY_STYLE_ID = "overlay-default"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_POSITIONS = {"top", "center", "bottom", "lower_third", "top_left", "top_right", "bottom_left", "bottom_right"}
_ALIGNMENTS = {"left", "center", "right"}


def normalize_hex_color(value: str | None, *, field_name: str = "color") -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not _HEX_RE.match(cleaned):
        raise ValueError(f"{field_name} must be a #RRGGBB hex color")
    return cleaned.upper()


@dataclass(frozen=True)
class TextStyleProfile:
    id: str
    name: str
    version: str = "text_style_profile.v1"
    font_family: str = "Noto Sans CJK SC"
    font_file: str | None = None
    font_size: int = 64
    font_weight: int = 700
    primary_color: str = "#FFFFFF"
    background_color: str | None = None
    background_opacity: float = 0.0
    stroke_color: str = "#000000"
    stroke_width: int = 2
    shadow_color: str | None = None
    shadow_blur: int = 0
    position: str = "bottom"
    alignment: str = "center"
    margin_x: int = 80
    margin_y: int = 140
    max_width_ratio: float = 0.86
    line_height: float = 1.18
    max_chars_per_line: int | None = None
    punctuation_mode: str = "strip_all"
    scale_basis_width: int = 1080
    scale_basis_height: int = 1920

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("TextStyleProfile id cannot be empty")
        if self.font_size <= 0:
            raise ValueError("font_size must be positive")
        if self.stroke_width < 0:
            raise ValueError("stroke_width must be non-negative")
        if self.shadow_blur < 0:
            raise ValueError("shadow_blur must be non-negative")
        if self.margin_x < 0 or self.margin_y < 0:
            raise ValueError("margins must be non-negative")
        if not 0.0 <= float(self.background_opacity) <= 1.0:
            raise ValueError("background_opacity must be between 0 and 1")
        if self.position not in _POSITIONS:
            raise ValueError(f"Unsupported text position: {self.position}")
        if self.alignment not in _ALIGNMENTS:
            raise ValueError(f"Unsupported text alignment: {self.alignment}")
        if self.scale_basis_width <= 0 or self.scale_basis_height <= 0:
            raise ValueError("scale basis dimensions must be positive")
        object.__setattr__(self, "primary_color", normalize_hex_color(self.primary_color, field_name="primary_color"))
        object.__setattr__(self, "stroke_color", normalize_hex_color(self.stroke_color, field_name="stroke_color"))
        object.__setattr__(self, "background_color", normalize_hex_color(self.background_color, field_name="background_color"))
        object.__setattr__(self, "shadow_color", normalize_hex_color(self.shadow_color, field_name="shadow_color"))

    def scale_for_canvas(self, width: int, height: int) -> float:
        width_scale = max(1, int(width)) / self.scale_basis_width
        height_scale = max(1, int(height)) / self.scale_basis_height
        return min(width_scale, height_scale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "font_family": self.font_family,
            "font_file": self.font_file,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "primary_color": self.primary_color,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "stroke_color": self.stroke_color,
            "stroke_width": self.stroke_width,
            "shadow_color": self.shadow_color,
            "shadow_blur": self.shadow_blur,
            "position": self.position,
            "alignment": self.alignment,
            "margin_x": self.margin_x,
            "margin_y": self.margin_y,
            "max_width_ratio": self.max_width_ratio,
            "line_height": self.line_height,
            "max_chars_per_line": self.max_chars_per_line,
            "punctuation_mode": self.punctuation_mode,
            "scale_basis_width": self.scale_basis_width,
            "scale_basis_height": self.scale_basis_height,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextStyleProfile":
        return cls(
            version=str(data.get("version", "text_style_profile.v1")),
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            font_family=str(data.get("font_family", "Noto Sans CJK SC")),
            font_file=data.get("font_file"),
            font_size=int(data.get("font_size", 64)),
            font_weight=int(data.get("font_weight", 700)),
            primary_color=str(data.get("primary_color", "#FFFFFF")),
            background_color=data.get("background_color"),
            background_opacity=float(data.get("background_opacity", 0.0)),
            stroke_color=str(data.get("stroke_color", "#000000")),
            stroke_width=int(data.get("stroke_width", 2)),
            shadow_color=data.get("shadow_color"),
            shadow_blur=int(data.get("shadow_blur", 0)),
            position=str(data.get("position", "bottom")),
            alignment=str(data.get("alignment", "center")),
            margin_x=int(data.get("margin_x", 80)),
            margin_y=int(data.get("margin_y", 140)),
            max_width_ratio=float(data.get("max_width_ratio", 0.86)),
            line_height=float(data.get("line_height", 1.18)),
            max_chars_per_line=(
                int(data["max_chars_per_line"])
                if data.get("max_chars_per_line") is not None
                else None
            ),
            punctuation_mode=str(data.get("punctuation_mode", "strip_all")),
            scale_basis_width=int(data.get("scale_basis_width", 1080)),
            scale_basis_height=int(data.get("scale_basis_height", 1920)),
        )


def build_default_text_style_profiles() -> list[TextStyleProfile]:
    return [
        TextStyleProfile(id=DEFAULT_CAPTION_STYLE_ID, name="Caption Default"),
        TextStyleProfile(
            id=DEFAULT_OVERLAY_STYLE_ID,
            name="Overlay Default",
            font_size=76,
            position="center",
            margin_y=80,
        ),
    ]
```

- [x] **Step 4: Run model tests**

Run:

```bash
pytest tests/test_text_style_models.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/models/text_style.py tests/test_text_style_models.py
git commit -m "feat: add text style profile contract"
```

## Task 2: Add Text Style Profiles To RenderManifest

**Files:**
- Modify: `pixelle_video/models/render_package.py`
- Test: `tests/test_render_package_models.py`

- [x] **Step 1: Write failing RenderManifest test**

Append:

```python
from pixelle_video.models.text_style import TextStyleProfile


def test_render_manifest_round_trips_text_style_profiles():
    manifest = RenderManifest(
        task_id="task-1",
        title="Text styles",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_style_profiles=[
            TextStyleProfile(id="caption-default", name="Caption Default", font_size=66)
        ],
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.text_style_profiles[0].id == "caption-default"
    assert restored.text_style_profiles[0].font_size == 66
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_render_package_models.py::test_render_manifest_round_trips_text_style_profiles -v
```

Expected: FAIL because `RenderManifest.__init__` does not accept `text_style_profiles`.

- [x] **Step 3: Implement RenderManifest field**

Modify `pixelle_video/models/render_package.py`:

```python
from pixelle_video.models.text_style import TextStyleProfile
```

Add dataclass field and init parameter:

```python
text_style_profiles: List[TextStyleProfile] = field(default_factory=list)
```

Inside `__init__`:

```python
self.text_style_profiles = list(text_style_profiles or [])
```

Inside `to_dict()`:

```python
"text_style_profiles": [profile.to_dict() for profile in self.text_style_profiles],
```

Inside `from_dict()`:

```python
text_style_profiles=[
    TextStyleProfile.from_dict(item)
    for item in data.get("text_style_profiles", [])
],
```

- [x] **Step 4: Run RenderManifest tests**

Run:

```bash
pytest tests/test_render_package_models.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/models/render_package.py tests/test_render_package_models.py
git commit -m "feat: carry text style profiles in render manifest"
```

## Task 2A: Add TextStyleResolver And TextRenderingOrchestrator

**Files:**
- Create: `pixelle_video/services/text_style_resolver.py`
- Create: `pixelle_video/services/text_rendering_orchestrator.py`
- Test: `tests/test_text_style_resolver.py`
- Test: `tests/test_text_rendering_orchestrator.py`

- [x] **Step 1: Write failing resolver tests**

```python
from pixelle_video.models.render_package import TextCue, TextTrack
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
)
from pixelle_video.services.text_style_resolver import TextStyleResolver


def test_resolver_prefers_cue_style_then_track_style_then_role_default():
    resolver = TextStyleResolver(
        profiles=[
            TextStyleProfile(id="cue-style", name="Cue"),
            TextStyleProfile(id="track-style", name="Track"),
        ]
    )
    track = TextTrack(
        id="track-1",
        kind="overlay",
        name="Overlay",
        renderer_targets=("ass",),
        style_profile="track-style",
    )
    cue = TextCue(
        id="cue-1",
        track_id="track-1",
        text="重点",
        start=0,
        end=1,
        role="keyword",
        style_profile="cue-style",
    )

    assert resolver.resolve_for_cue(cue=cue, track=track).id == "cue-style"


def test_resolver_records_fallback_for_missing_style():
    resolver = TextStyleResolver(profiles=[])
    track = TextTrack(
        id="subtitle",
        kind="subtitle",
        name="Subtitle",
        renderer_targets=("ass",),
        style_profile="missing",
    )
    cue = TextCue(
        id="cue-1",
        track_id="subtitle",
        text="字幕",
        start=0,
        end=1,
        role="subtitle",
    )

    profile = resolver.resolve_for_cue(cue=cue, track=track)

    assert profile.id == DEFAULT_CAPTION_STYLE_ID
    assert resolver.diagnostics["fallbacks"][0]["missing_style_profile"] == "missing"


def test_overlay_role_defaults_to_overlay_profile():
    resolver = TextStyleResolver(profiles=[])
    track = TextTrack(
        id="overlay",
        kind="overlay",
        name="Overlay",
        renderer_targets=("hyperframes",),
    )
    cue = TextCue(
        id="cue-1",
        track_id="overlay",
        text="重点",
        start=0,
        end=1,
        role="keyword",
    )

    assert resolver.resolve_for_cue(cue=cue, track=track).id == DEFAULT_OVERLAY_STYLE_ID
```

- [x] **Step 2: Run resolver tests to verify they fail**

Run:

```bash
pytest tests/test_text_style_resolver.py -v
```

Expected: FAIL because `text_style_resolver.py` does not exist.

- [x] **Step 3: Implement resolver**

Create `pixelle_video/services/text_style_resolver.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from pixelle_video.models.render_package import TextCue, TextTrack
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
)


@dataclass
class TextStyleResolver:
    profiles: Iterable[TextStyleProfile] = ()
    strict: bool = False
    diagnostics: dict = field(default_factory=lambda: {"fallbacks": []})

    def __post_init__(self) -> None:
        merged = {profile.id: profile for profile in build_default_text_style_profiles()}
        merged.update({profile.id: profile for profile in self.profiles})
        self.profiles_by_id = merged

    def resolve_for_cue(self, *, cue: TextCue, track: TextTrack | None) -> TextStyleProfile:
        requested = [cue.style_profile, track.style_profile if track is not None else None]
        for style_id in requested:
            if not style_id:
                continue
            profile = self.profiles_by_id.get(style_id)
            if profile is not None:
                return profile
        default_id = DEFAULT_CAPTION_STYLE_ID if cue.role == "subtitle" else DEFAULT_OVERLAY_STYLE_ID
        profile = self.profiles_by_id.get(default_id)
        if profile is not None:
            missing = next((style_id for style_id in requested if style_id), None)
            if missing:
                self.diagnostics["fallbacks"].append(
                    {
                        "cue_id": cue.id,
                        "missing_style_profile": missing,
                        "resolved_style_profile": profile.id,
                    }
                )
            return profile
        if self.strict:
            raise ValueError(f"No text style profile resolved for cue {cue.id}")
        profile = self.profiles_by_id[DEFAULT_CAPTION_STYLE_ID]
        self.diagnostics["fallbacks"].append(
            {"cue_id": cue.id, "resolved_style_profile": profile.id}
        )
        return profile
```

- [x] **Step 4: Write failing orchestrator tests**

```python
from pixelle_video.models.text_style import DEFAULT_CAPTION_STYLE_ID
from pixelle_video.services.text_rendering_orchestrator import TextRenderingOrchestrator


def test_orchestrator_builds_caption_style_when_overlay_disabled():
    result = TextRenderingOrchestrator().build(
        text_rendering={
            "overlay": {"enabled": False},
            "caption_style": {"font_size": 72, "primary_color": "#FFFF00"},
            "image_text": {"suppress_embedded_text": True},
        },
        narrations=["第一句"],
        render_backend="hyperframes",
    )

    assert result.caption_style.id == DEFAULT_CAPTION_STYLE_ID
    assert result.caption_style.font_size == 72
    assert result.caption_settings.enabled is True
    assert result.text_render_package.version == "text_render_package.v1"
    assert result.settings.overlay.enabled is False
    assert result.overlay_policy.enabled_targets == ()
    assert result.image_text_policy.suppress_embedded_text is True
```

- [x] **Step 5: Run orchestrator test to verify it fails**

Run:

```bash
pytest tests/test_text_rendering_orchestrator.py -v
```

Expected: FAIL because the orchestrator does not exist.

- [x] **Step 6: Implement orchestrator boundary**

Create `pixelle_video/services/text_rendering_orchestrator.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pixelle_video.models.text_layout import TextLayoutPlan
from pixelle_video.models.text_overlay import (
    ImageTextPromptPolicy,
    TextOverlayPlan,
    TextRenderingPolicy,
    TextRenderingSettings,
    build_text_rendering_policy,
    build_text_rendering_settings,
)
from pixelle_video.models.text_render_package import (
    CaptionRenderingSettings,
    TextRenderPackage,
)
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
)
from pixelle_video.services.text_overlay_planner import TextOverlayPlanner


@dataclass(frozen=True)
class TextRenderingBuildResult:
    settings: TextRenderingSettings
    text_render_package: TextRenderPackage
    caption_settings: CaptionRenderingSettings
    overlay_policy: TextRenderingPolicy
    overlay_plan: TextOverlayPlan
    text_style_profiles: tuple[TextStyleProfile, ...]
    caption_style: TextStyleProfile
    overlay_style: TextStyleProfile
    image_text_policy: ImageTextPromptPolicy
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _profile_from_request(
    *,
    style_id: str,
    name: str,
    data: Mapping[str, Any] | None,
    defaults: Mapping[str, Any] | None = None,
) -> TextStyleProfile:
    payload = {"id": style_id, "name": name}
    if defaults:
        payload.update(defaults)
    if data:
        payload.update(dict(data))
    payload["id"] = style_id
    payload["name"] = name
    return TextStyleProfile.from_dict(payload)


class TextRenderingOrchestrator:
    def __init__(self, overlay_planner: TextOverlayPlanner | None = None) -> None:
        self.overlay_planner = overlay_planner or TextOverlayPlanner()

    def build(
        self,
        *,
        text_rendering: Mapping[str, Any] | None,
        narrations: Sequence[str] = (),
        render_backend: str | None = None,
        frame_count: int | None = None,
    ) -> TextRenderingBuildResult:
        settings = build_text_rendering_settings(text_rendering)
        overlay_policy = build_text_rendering_policy(settings.overlay)
        request = dict(text_rendering or {})
        caption_style = _profile_from_request(
            style_id=DEFAULT_CAPTION_STYLE_ID,
            name="Caption Default",
            data=request.get("caption_style"),
        )
        caption_payload = dict(request.get("caption") or {})
        caption_settings = CaptionRenderingSettings(
            enabled=bool(caption_payload.get("enabled", True)),
            source=str(caption_payload.get("source", "narration_timing")),
            style_profile=caption_style.id,
            punctuation_mode=str(caption_payload.get("punctuation_mode", "strip_all")),
            renderer_targets=tuple(caption_payload.get("renderer_targets", ("hyperframes", "ass"))),
        )
        overlay_style = _profile_from_request(
            style_id=DEFAULT_OVERLAY_STYLE_ID,
            name="Overlay Default",
            data=request.get("overlay_style"),
            defaults={"font_size": 76, "position": "center", "margin_y": 80},
        )
        overlay_enabled = settings.overlay.enabled and bool(overlay_policy.enabled_targets)
        overlay_plan = (
            self.overlay_planner.plan(narrations=narrations, policy=overlay_policy)
            if overlay_enabled
            else TextOverlayPlan()
        )
        diagnostics = {
            "render_backend": render_backend,
            "frame_count": frame_count,
            "overlay_enabled": overlay_enabled,
            "disabled_reasons": [],
        }
        if not overlay_enabled:
            diagnostics["disabled_reasons"].append("overlay_text_layer_disabled")
        package = TextRenderPackage(
            version="text_render_package.v1",
            task_id=str(request.get("task_id", "")),
            caption_settings=caption_settings,
            text_style_profiles=(caption_style, overlay_style),
            caption_cues=(),
            text_tracks=(),
            text_cues=(),
            layout_plan=TextLayoutPlan(),
            diagnostics=diagnostics,
        )
        return TextRenderingBuildResult(
            settings=settings,
            text_render_package=package,
            caption_settings=caption_settings,
            overlay_policy=overlay_policy,
            overlay_plan=overlay_plan,
            text_style_profiles=(caption_style, overlay_style),
            caption_style=caption_style,
            overlay_style=overlay_style,
            image_text_policy=settings.image_text,
            diagnostics=diagnostics,
        )
```

This file must not emit ASS `force_style`, CSS text, ffmpeg filter strings, or `fontsdir`.

- [x] **Step 7: Run resolver and orchestrator tests**

Run:

```bash
pytest tests/test_text_style_resolver.py tests/test_text_rendering_orchestrator.py -v
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add pixelle_video/services/text_style_resolver.py pixelle_video/services/text_rendering_orchestrator.py tests/test_text_style_resolver.py tests/test_text_rendering_orchestrator.py
git commit -m "feat: centralize text rendering style resolution"
```

## Task 2B: Add Text Sanitization, Layout Planning, And Adapter Protocol

**Files:**
- Create: `pixelle_video/services/text_content_sanitizer.py`
- Create: `pixelle_video/services/text_layout_planner.py`
- Create: `pixelle_video/services/text_renderer_adapter.py`
- Test: `tests/test_text_content_sanitizer.py`
- Test: `tests/test_text_layout_planner.py`
- Test: `tests/test_text_renderer_adapter_contract.py`

- [x] **Step 1: Write failing sanitizer tests**

```python
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer


def test_sanitizer_removes_ass_override_tags_and_control_chars():
    result = TextContentSanitizer().sanitize("你好{\\pos(1,2)}\u200b<script>x</script>")

    assert result.raw_text == "你好{\\pos(1,2)}\u200b<script>x</script>"
    assert "{\\pos" not in result.display_text
    assert "\u200b" not in result.display_text
    assert result.requires_html_escape is True
```

- [x] **Step 2: Write failing layout planner tests**

```python
from pixelle_video.services.text_layout_planner import TextLayoutPlanner


def test_layout_planner_uses_cjk_display_width_and_safe_area():
    plan = TextLayoutPlanner().plan_text(
        text="这是一个很长的中文标题",
        max_display_width=10,
        slot="lower_third",
    )

    assert len(plan.wrapped_lines) >= 2
    assert plan.safe_area == "caption_safe_area"
    assert plan.slot == "lower_third"
```

- [x] **Step 3: Write failing adapter protocol test**

```python
from pixelle_video.services.text_renderer_adapter import TextRenderExportResult


def test_export_result_records_required_diagnostics():
    result = TextRenderExportResult(
        target="ass",
        enabled=True,
        artifacts={"master_ass": "text_layer/master.ass"},
        cue_count=2,
        style_profile_ids=("caption-default",),
        fallbacks=(),
        warnings=(),
        duration_ms=12,
    )

    assert result.to_dict()["target"] == "ass"
    assert result.to_dict()["artifacts"]["master_ass"] == "text_layer/master.ass"
```

- [x] **Step 4: Run tests to verify they fail**

Run:

```bash
pytest tests/test_text_content_sanitizer.py tests/test_text_layout_planner.py tests/test_text_renderer_adapter_contract.py -v
```

Expected: FAIL because these services do not exist.

- [x] **Step 5: Implement the three source-boundary services**

Required behavior:

- `TextContentSanitizer.sanitize(...)` returns `raw_text`, `display_text`, `removed_tokens`, `requires_html_escape`, and `requires_ass_escape`.
- `TextLayoutPlanner.plan_text(...)` uses display width, not byte length, and returns wrapped lines plus safe-area/slot/layer intent.
- `TextRenderExportResult` serializes a standard adapter result shape.
- `TextRendererAdapter` is a `Protocol` with `supports(...)` and `export(...)`.
- No ASS tags, HTML tags, CSS strings, or ffmpeg filter strings are emitted by sanitizer or layout planner.

- [x] **Step 6: Run tests**

Run:

```bash
pytest tests/test_text_content_sanitizer.py tests/test_text_layout_planner.py tests/test_text_renderer_adapter_contract.py -v
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add pixelle_video/services/text_content_sanitizer.py pixelle_video/services/text_layout_planner.py pixelle_video/services/text_renderer_adapter.py tests/test_text_content_sanitizer.py tests/test_text_layout_planner.py tests/test_text_renderer_adapter_contract.py
git commit -m "feat: add text rendering safety and adapter contracts"
```

## Task 3: Build ASS Style Builder

**Files:**
- Create: `pixelle_video/services/ass_style_builder.py`
- Test: `tests/test_ass_style_builder.py`

- [x] **Step 1: Write failing ASS style builder tests**

```python
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.ass_style_builder import AssStyleBuilder, ass_color


def test_ass_color_converts_hex_to_ass_bbggrr():
    assert ass_color("#FFFFFF") == "&H00FFFFFF"
    assert ass_color("#000000") == "&H00000000"
    assert ass_color("#FFCC00") == "&H0000CCFF"


def test_ass_style_scales_font_and_margin_for_canvas():
    profile = TextStyleProfile(
        id="caption-default",
        name="Caption Default",
        font_size=64,
        stroke_width=4,
        margin_y=140,
        scale_basis_width=1080,
        scale_basis_height=1920,
    )

    style = AssStyleBuilder().build_style(
        name="Default",
        profile=profile,
        canvas_width=720,
        canvas_height=1280,
    )

    assert "Style: Default" in style
    assert ",43," in style
    assert ",3,0,2,53,53,93,1" in style
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_ass_style_builder.py -v
```

Expected: FAIL because builder does not exist.

- [x] **Step 3: Implement ASS style builder**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass

from pixelle_video.models.text_style import TextStyleProfile

_ASS_ALIGNMENT = {
    ("bottom", "center"): 2,
    ("lower_third", "center"): 2,
    ("top", "center"): 8,
    ("center", "center"): 5,
    ("top_left", "left"): 7,
    ("top_right", "right"): 9,
    ("bottom_left", "left"): 1,
    ("bottom_right", "right"): 3,
}


def ass_color(value: str, *, alpha: int = 0) -> str:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError("ASS color input must be #RRGGBB")
    red = cleaned[0:2]
    green = cleaned[2:4]
    blue = cleaned[4:6]
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


@dataclass(frozen=True)
class AssStyleBuilder:
    def build_style(
        self,
        *,
        name: str,
        profile: TextStyleProfile,
        canvas_width: int,
        canvas_height: int,
    ) -> str:
        scale = profile.scale_for_canvas(canvas_width, canvas_height)
        font_size = max(1, int(round(profile.font_size * scale)))
        outline = max(0, int(round(profile.stroke_width * scale)))
        margin_x = max(0, int(round(profile.margin_x * scale)))
        margin_y = max(0, int(round(profile.margin_y * scale)))
        alignment = _ASS_ALIGNMENT.get(
            (profile.position, profile.alignment),
            2,
        )
        background_alpha = int(round((1.0 - profile.background_opacity) * 255))
        background = profile.background_color or "#000000"
        return (
            f"Style: {name},{profile.font_family},{font_size},"
            f"{ass_color(profile.primary_color)},"
            f"{ass_color(profile.stroke_color, alpha=128)},"
            f"{ass_color(background, alpha=background_alpha)},"
            f"{1 if profile.font_weight >= 600 else 0},0,1,"
            f"{outline},0,{alignment},{margin_x},{margin_x},{margin_y},1"
        )
```

- [x] **Step 4: Run ASS builder tests**

Run:

```bash
pytest tests/test_ass_style_builder.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/services/ass_style_builder.py tests/test_ass_style_builder.py
git commit -m "feat: build ass styles from text profiles"
```

## Task 4: Remove Hardcoded ASS Styles

**Files:**
- Modify: `pixelle_video/services/ass_text_adapter.py`
- Test: `tests/test_ass_text_adapter.py`

- [x] **Step 1: Add failing adapter test for manifest styles**

Append:

```python
from pixelle_video.models.text_style import TextStyleProfile


def test_ass_export_uses_manifest_text_style_profiles(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Styled text",
        width=1080,
        height=1920,
        fps=30,
        template_id="legacy",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-yellow",
                name="Caption Yellow",
                font_size=72,
                primary_color="#FFFF00",
                stroke_width=5,
            )
        ],
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
                style_profile="caption-yellow",
            )
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="字幕",
                start=0,
                end=1,
                role="subtitle",
            )
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)
    text = outputs.master.read_text(encoding="utf-8")

    assert "Style: caption-yellow" in text
    assert ",72," in text
    assert "&H0000FFFF" in text
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_ass_text_adapter.py::test_ass_export_uses_manifest_text_style_profiles -v
```

Expected: FAIL because adapter still emits hardcoded `Default` and `Overlay`.

- [x] **Step 3: Update AssTextAdapter**

Implement style resolution:

```python
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
)
from pixelle_video.services.ass_style_builder import AssStyleBuilder
from pixelle_video.services.text_renderer_adapter import TextRenderExportResult
from pixelle_video.services.text_style_resolver import TextStyleResolver
```

Behavior:

- Resolve all styles through `TextStyleResolver`; do not implement fallback inside `AssTextAdapter`.
- Build one ASS style per referenced profile in the `TextRenderPackage`/manifest.
- For subtitle cues default to `DEFAULT_CAPTION_STYLE_ID`.
- For non-subtitle cues default to `DEFAULT_OVERLAY_STYLE_ID`.
- Dialogue style name is the resolved style profile id.
- Return or expose a `TextRenderExportResult` shape for artifacts and fallback diagnostics.

- [x] **Step 4: Run ASS adapter tests**

Run:

```bash
pytest tests/test_ass_text_adapter.py tests/test_ass_style_builder.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/services/ass_text_adapter.py tests/test_ass_text_adapter.py
git commit -m "feat: export ass using text style profiles"
```

## Task 4A: Resolve Fonts And Burn ASS With fontsdir

**Files:**
- Create: `pixelle_video/services/font_resolver.py`
- Modify: `pixelle_video/services/video.py`
- Test: `tests/test_video_ass_burn_in.py`

- [x] **Step 1: Write failing font resolver and ffmpeg filter tests**

```python
from pathlib import Path

from pixelle_video.services.font_resolver import FontResolver
from pixelle_video.services.video import VideoService


def test_font_resolver_prefers_profile_font_directory(tmp_path):
    font_file = tmp_path / "NotoSansCJK-Regular.ttc"
    font_file.write_bytes(b"font")

    resolved = FontResolver().resolve_fontsdir(font_file=str(font_file))

    assert resolved == tmp_path


def test_video_service_builds_ass_filter_with_fontsdir(tmp_path):
    ass_file = tmp_path / "master.ass"
    ass_file.write_text("[Script Info]\n", encoding="utf-8")
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()

    filter_expr = VideoService()._build_ass_filter(ass_file, fonts_dir=fonts_dir)

    assert "ass=" in filter_expr
    assert "fontsdir=" in filter_expr
    assert "master.ass" in filter_expr
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_video_ass_burn_in.py -v
```

Expected: FAIL because `FontResolver` and `_build_ass_filter` do not exist.

- [x] **Step 3: Implement FontResolver**

Create `pixelle_video/services/font_resolver.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FontResolver:
    project_font_dirs: tuple[Path, ...] = (
        Path("fonts"),
        Path("font"),
        Path("resource/fonts"),
    )

    def resolve_fontsdir(self, *, font_file: str | None = None) -> Path | None:
        if font_file:
            path = Path(font_file)
            if path.exists() and path.parent.exists():
                return path.parent
        for candidate in self.project_font_dirs:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None
```

- [x] **Step 4: Add ASS filter builder to VideoService**

Add a private helper:

```python
def _build_ass_filter(self, ass_file: str | Path, *, fonts_dir: str | Path | None = None) -> str:
    escaped_ass = self._escape_ffmpeg_filter_path(str(Path(ass_file)))
    if fonts_dir is None:
        return f"ass='{escaped_ass}'"
    escaped_fonts = self._escape_ffmpeg_filter_path(str(Path(fonts_dir)))
    return f"ass='{escaped_ass}':fontsdir='{escaped_fonts}'"
```

Update `burn_ass_subtitles(...)` to use this helper. If no fontsdir is available, continue with `ass='...'` and let caller summary record the fallback.

- [x] **Step 5: Run ASS burn-in tests**

Run:

```bash
pytest tests/test_video_ass_burn_in.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add pixelle_video/services/font_resolver.py pixelle_video/services/video.py tests/test_video_ass_burn_in.py
git commit -m "feat: burn ass subtitles with font directory"
```

## Task 5: Carry Caption And Text Layer Styles Through HyperFrames

**Files:**
- Modify: `pixelle_video/models/template_render_context.py`
- Modify: `pixelle_video/services/hyperframes_project_service.py`
- Modify: `pixelle_video/services/hyperframes_compiler.py`
- Test: `tests/test_hyperframes_project_service.py`
- Test: `tests/test_hyperframes_compiler.py`

- [x] **Step 1: Write failing HyperFrames tests**

Add compiler assertion:

```python
from pixelle_video.models.text_style import TextStyleProfile


def test_hyperframes_compiler_emits_text_style_variables(tmp_path):
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-yellow",
                name="Caption Yellow",
                primary_color="#FFFF00",
            )
        ],
        text_tracks=[
            TextTrack(
                id="overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("hyperframes",),
                style_profile="caption-yellow",
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="overlay",
                text="重点",
                start=0,
                end=1,
                role="keyword",
                slot="center",
            )
        ],
    )

    HyperFramesCompiler().compile(project_dir=tmp_path, context=context)

    html = (tmp_path / "compositions" / "text_layer.html").read_text(encoding="utf-8")
    assert 'data-style-profile="caption-yellow"' in html
    assert "--text-fill: #FFFF00" in html
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_hyperframes_compiler.py::test_hyperframes_compiler_emits_text_style_variables -v
```

Expected: FAIL because context/compiler do not carry style profiles.

- [x] **Step 3: Implement context and compiler style support**

Required behavior:

- `TemplateRenderContext` gets `text_style_profiles: List[TextStyleProfile]`.
- `build_template_render_context(...)` passes `manifest.text_style_profiles`.
- `_build_text_tracks_payload(...)` includes `text_style_profiles`.
- `_build_caption_cues_from_sentences(...)` assigns normal captions a caption style profile id independent of overlay text layer state.
- `HyperFramesProjectService` reads from `TextRenderPackage` when present and derives the normalized manifest from it.
- `HyperFramesCompiler._render_captions(...)` resolves `CaptionCue.style_profile` through `TextStyleResolver` and emits caption CSS variables into `captions.html`.
- `HyperFramesCompiler._render_text_cues(...)` resolves style id from cue then track through `TextStyleResolver`.
- Text content comes from sanitized display text; HTML escaping stays adapter-specific.
- Layout slot/safe-area intent comes from `TextLayoutPlan`, not template-local guesses.
- Each text cue DOM includes `data-style-profile`.
- Inline style contains CSS variables from the resolved `TextStyleProfile`.

- [x] **Step 4: Run HyperFrames tests**

Run:

```bash
pytest tests/test_hyperframes_compiler.py tests/test_hyperframes_project_service.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/models/template_render_context.py pixelle_video/services/hyperframes_project_service.py pixelle_video/services/hyperframes_compiler.py tests/test_hyperframes_compiler.py tests/test_hyperframes_project_service.py
git commit -m "feat: carry text styles through hyperframes"
```

## Task 6: Assign Style Profiles During Cue Compilation

**Files:**
- Modify: `pixelle_video/services/text_cue_compiler.py`
- Test: `tests/test_text_cue_compiler.py`

- [x] **Step 1: Write failing compiler test**

```python
from pixelle_video.models.text_style import DEFAULT_OVERLAY_STYLE_ID


def test_text_cue_compiler_assigns_overlay_style_profile():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="c1",
                    text="重点",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(package=package, sentence_units=[])

    assert tracks[0].style_profile == DEFAULT_OVERLAY_STYLE_ID
    assert cues[0].style_profile == DEFAULT_OVERLAY_STYLE_ID
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_text_cue_compiler.py::test_text_cue_compiler_assigns_overlay_style_profile -v
```

Expected: FAIL because compiler does not assign style profiles.

- [x] **Step 3: Implement default style assignment**

Rules:

- `role == "subtitle"` uses `DEFAULT_CAPTION_STYLE_ID`.
- `role == "model_native_hint"` uses no visual style profile.
- all other programmatic text uses `DEFAULT_OVERLAY_STYLE_ID`.

- [x] **Step 4: Run compiler tests**

Run:

```bash
pytest tests/test_text_cue_compiler.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/services/text_cue_compiler.py tests/test_text_cue_compiler.py
git commit -m "feat: assign default text style profiles to cues"
```

## Task 7: Extend API And UI Style Inputs As Three Independent Sections

**Files:**
- Modify: `api/schemas/text_rendering.py`
- Create: `web/components/text_rendering_config.py`
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `web/i18n/locales/zh_CN.json`
- Test: `tests/test_style_config_text_rendering_ui.py`

- [x] **Step 1: Write schema tests**

Add:

```python
from api.schemas.text_rendering import TextRenderingRequest


def test_text_rendering_request_accepts_caption_style():
    request = TextRenderingRequest.model_validate(
        {
            "overlay": {"enabled": True, "renderer_targets": ["ass"]},
            "caption_style": {
                "font_size": 72,
                "primary_color": "#FFFF00",
                "stroke_color": "#000000",
                "stroke_width": 4,
            },
        }
    )

    assert request.caption_style.font_size == 72
    assert request.caption_style.primary_color == "#FFFF00"


def test_text_rendering_controls_live_in_focused_component():
    from pathlib import Path

    component = Path("web/components/text_rendering_config.py")
    style_config = Path("web/components/style_config.py")

    assert component.exists()
    assert "render_text_rendering_controls" in component.read_text(encoding="utf-8")
    assert "caption_style" in component.read_text(encoding="utf-8")
    assert "def render_text_rendering_controls" not in style_config.read_text(encoding="utf-8")
```

- [x] **Step 2: Run schema test to verify it fails**

Run:

```bash
pytest tests/test_style_config_text_rendering_ui.py::test_text_rendering_request_accepts_caption_style tests/test_style_config_text_rendering_ui.py::test_text_rendering_controls_live_in_focused_component -v
```

Expected: FAIL because schema does not have `caption_style` and the focused UI component does not exist.

- [x] **Step 3: Implement Pydantic style request**

Add `TextStyleProfileRequest` with:

- `font_family`
- `font_size`
- `primary_color`
- `stroke_color`
- `stroke_width`
- `background_color`
- `background_opacity`
- `position`
- `margin_y`
- `max_chars_per_line`

Then add:

```python
caption_style: Optional[TextStyleProfileRequest] = None
overlay_style: Optional[TextStyleProfileRequest] = None
```

- [x] **Step 4: Add UI controls in a focused component**

Create `web/components/text_rendering_config.py`. In `render_text_rendering_controls(...)`, render three sibling sections inside the existing `section.text_rendering` expander:

1. Caption style section.
2. Overlay text layer section.
3. Image text policy section.

Caption style controls are always rendered inside the text rendering panel and are not gated by `text_layer_enabled`:

- `st.number_input` for font size
- `st.color_picker` for primary color
- `st.color_picker` for stroke color
- `st.number_input` for stroke width
- `st.selectbox` for position
- `st.number_input` for margin_y

Return these values inside `text_rendering["caption_style"]`.

Keep `render_text_layer_controls(render_backend)` for overlay text layer only. Its checkbox should mean “enable overlay/keyword/native-hint text layer”, not “enable captions”.

Keep `image_text.suppress_embedded_text` as image prompt policy only. It must not enable or disable captions.

In `web/components/style_config.py`, import the focused component:

```python
from web.components.text_rendering_config import (
    build_text_rendering_payload,
    render_text_layer_controls,
    render_text_rendering_controls,
)
```

Do not keep duplicate text rendering UI definitions in `style_config.py`.

- [x] **Step 5: Run UI/schema tests**

Run:

```bash
pytest tests/test_style_config_text_rendering_ui.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add api/schemas/text_rendering.py web/components/text_rendering_config.py web/components/style_config.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json tests/test_style_config_text_rendering_ui.py
git commit -m "feat: expose text style controls"
```

## Task 8: Wire Styles Into StandardPipeline And Separate Summaries

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_standard_pipeline_text_rendering_summary.py`

- [x] **Step 1: Write failing caption summary test**

```python
from types import SimpleNamespace

from pixelle_video.models.text_style import TextStyleProfile


def test_standard_pipeline_caption_summary_is_independent_from_text_layer():
    ctx = SimpleNamespace(observability={})

    pipeline._record_caption_rendering_summary(
        ctx,
        caption_cue_count=12,
        style_profile=TextStyleProfile(
            id="caption-yellow",
            name="Caption Yellow",
            primary_color="#FFFF00",
        ),
        renderer_targets=("hyperframes", "ass"),
        artifacts={"subtitle_only_ass": "text_layer/subtitle_only.ass"},
    )

    summary = ctx.observability["caption_rendering_summary"]
    assert summary["caption_cue_count"] == 12
    assert summary["style_profile_id"] == "caption-yellow"
    assert summary["artifacts"]["subtitle_only_ass"] == "text_layer/subtitle_only.ass"
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_standard_pipeline_text_rendering_summary.py -v
```

Expected: FAIL until a caption rendering summary is implemented.

- [x] **Step 3: Build style profiles from request**

In `StandardPipeline.plan_visuals(...)`:

- Parse `ctx.params["text_rendering"]["caption_style"]` independently of `ctx.params["text_rendering"]["overlay"]`.
- Build caption style profiles even when `overlay.enabled` is false.
- Build overlay style profiles only for overlay text layer output.
- Store `TextRenderPackage` in the task directory and keep a reference on pipeline context.
- Pass `TextRenderPackage.text_style_profiles` into `RenderManifest` in both legacy and HyperFrames post-production.
- Derive caption/text/image summaries from `TextRenderPackage` and adapter export results.
- Ensure disabling overlay text layer does not clear or skip caption style.

- [x] **Step 4: Add separate summary methods**

Add `StandardPipeline._record_caption_rendering_summary(...)` for normal captions:

- `enabled`
- `caption_cue_count`
- `style_profile_id`
- `renderer_targets`
- `artifacts`
- `fallbacks`

Keep `StandardPipeline._record_text_layer_summary(...)` for overlay text layer only:

- `style_profile_ids`
- `artifacts`
- `fallbacks`
- optional adapter timing fields

Do not put normal caption style under `text_layer_summary`.

- [x] **Step 5: Run pipeline-related tests**

Run:

```bash
pytest tests/test_standard_pipeline_text_rendering_summary.py tests/test_standard_pipeline_staged_mode.py -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_text_rendering_summary.py tests/test_standard_pipeline_staged_mode.py
git commit -m "feat: wire text styles into standard pipeline"
```

## Task 8A: Wire Contract Into Custom And AssetBased Pipelines

**Files:**
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/pipelines/asset_based.py`
- Test: `tests/test_pipeline_text_rendering_contract.py`

- [x] **Step 1: Write failing cross-pipeline contract tests**

```python
from types import SimpleNamespace

from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.custom import CustomPipeline


class FakeCore:
    config = {"template": {"default_template": "1080x1920/image_default.html"}}
    llm = object()
    tts = object()
    media = object()
    video = object()
    frame_processor = object()
    persistence = object()


def test_custom_pipeline_records_text_rendering_summary_when_overlay_unsupported():
    pipeline = CustomPipeline(FakeCore())
    ctx = SimpleNamespace(
        params={
            "text_rendering": {
                "caption_style": {"font_size": 72},
                "overlay": {"enabled": True, "renderer_targets": ["ass"]},
            }
        },
        observability={},
    )

    pipeline._record_text_rendering_contract_summary(
        ctx,
        supported_overlay=False,
        disabled_reason="custom_pipeline_overlay_not_supported",
    )

    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == "caption-default"
    assert ctx.observability["text_layer_summary"]["enabled"] is False
    assert (
        ctx.observability["text_layer_summary"]["disabled_reason"]
        == "custom_pipeline_overlay_not_supported"
    )


def test_asset_based_pipeline_caption_style_is_independent_from_overlay_support():
    pipeline = AssetBasedPipeline(FakeCore())
    ctx = SimpleNamespace(
        request={
            "text_rendering": {
                "caption_style": {"primary_color": "#FFFF00"},
                "overlay": {"enabled": False},
            }
        },
        observability={},
    )

    pipeline._record_text_rendering_contract_summary(
        ctx,
        supported_overlay=False,
        disabled_reason="asset_based_overlay_disabled",
    )

    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == "caption-default"
    assert ctx.observability["text_layer_summary"]["disabled_reason"] == "asset_based_overlay_disabled"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_pipeline_text_rendering_contract.py -v
```

Expected: FAIL because `custom` and `asset_based` do not record the shared contract summaries.

- [x] **Step 3: Add shared summary helper usage**

Both pipelines must call `TextRenderingOrchestrator().build(...)` with their incoming `text_rendering` payload before render-time branching. Minimum required behavior:

- A `TextRenderPackage` is produced or an explicit disabled package is recorded.
- `caption_rendering_summary` records caption style id even when overlay is disabled or unsupported.
- `text_layer_summary` records `enabled=False`, renderer targets, disabled reason, and style profile ids when overlay cannot run.
- `image_text_policy_summary` records `not_applicable` when the pipeline does not generate image/video prompts.
- No renderer-specific style fields are emitted.

- [x] **Step 4: Run cross-pipeline tests**

Run:

```bash
pytest tests/test_pipeline_text_rendering_contract.py -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pixelle_video/pipelines/custom.py pixelle_video/pipelines/asset_based.py tests/test_pipeline_text_rendering_contract.py
git commit -m "feat: report text rendering contract across pipelines"
```

## Task 9: Full Verification

**Files:**
- No new files.

- [x] **Step 1: Run focused text rendering suite**

Run:

```bash
pytest tests/test_text_render_package_models.py tests/test_text_style_models.py tests/test_text_content_sanitizer.py tests/test_text_layout_planner.py tests/test_text_renderer_adapter_contract.py tests/test_text_style_resolver.py tests/test_text_rendering_orchestrator.py tests/test_ass_style_builder.py tests/test_ass_text_adapter.py tests/test_video_ass_burn_in.py tests/test_text_cue_compiler.py tests/test_hyperframes_compiler.py tests/test_hyperframes_project_service.py -v
```

Expected: PASS.

- [x] **Step 2: Run broader affected suite**

Run:

```bash
pytest tests/test_render_package_models.py tests/test_template_render_context.py tests/test_standard_pipeline_staged_mode.py tests/test_style_config_text_rendering_ui.py tests/test_pipeline_text_rendering_contract.py -v
```

Expected: PASS.

- [x] **Step 3: Validate golden fixture JSON**

Run:

```bash
python -m json.tool tests/fixtures/text_rendering/text_render_package_legacy_caption.json > $null
python -m json.tool tests/fixtures/text_rendering/text_render_package_overlay_hybrid.json > $null
python -m json.tool tests/fixtures/text_rendering/render_manifest_with_text_styles.json > $null
```

Expected: PASS with valid JSON.

- [x] **Step 4: Run golden artifact and visual smoke tests**

Run:

```bash
pytest tests/test_text_rendering_golden_artifacts.py -v
```

Expected: PASS. The test must verify ASS/HyperFrames snapshots and at least one rendered text layer is non-empty and inside its declared safe area.

- [x] **Step 5: Run lint or syntax check**

Run:

```bash
python -m compileall pixelle_video api web tests
```

Expected: PASS with no syntax errors.

- [x] **Step 6: Commit final docs if needed**

```bash
git add docs/superpowers/specs/2026-04-25-text-rendering-contract-v2-design.md docs/superpowers/plans/2026-04-25-text-rendering-contract-v2.md
git commit -m "docs: plan text rendering contract v2"
```

## Self-Review

Spec coverage:

- Canonical persisted text rendering package: Task 0.
- Unified text style contract: Tasks 1 and 2.
- Shared resolver/orchestrator boundary: Task 2A.
- Text safety, shared layout, and adapter protocol: Task 2B.
- ASS adapter without hardcoded style: Tasks 3 and 4.
- ASS font directory and burn-in reliability: Task 4A.
- HyperFrames style consumption: Task 5.
- Cue style assignment: Task 6.
- API/UI user-facing style controls and UI component boundary: Task 7.
- Pipeline summary and observability: Task 8.
- Cross-pipeline contract coverage: Task 8A.
- Verification: Task 9.

Known implementation caution:

- Current worktree may contain unrelated user changes. Each commit must stage only files listed in the task.
- Repository AGENTS forbids `git worktree`; do not follow the writing-plans default worktree recommendation here.
- This plan does not replace the distributed generation plan. Artifact storage and S3/MinIO remain separate production infrastructure work.
- Do not introduce renderer-specific request fields. Style request fields must stay platform-level.
- Do not let `StandardPipeline.plan_visuals` remain the only place that constructs text rendering state.
- Do not let any renderer adapter mutate or invent `TextRenderPackage` fields; adapters only return `TextRenderExportResult`.
- Do not ship this without golden fixture and visual non-empty/safe-area checks.
