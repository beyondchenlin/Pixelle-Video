# Stage 2 AssetBible / IP / SceneCast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 2 IP and visual-consistency contract layer: AssetBible, IPProfile, CharacterProfile, SceneCast, and PromptComposer extension that fills Stage 1A PromptPlan reserved fields.

**Architecture:** Implement Stage 2 as an isolated domain layer first. It may read Stage 1A `PromptPlan` reserved fields and produce validated references, but it must not alter the Stage 1A PromptPlan core shape or connect to the main generation path until Gate A passes.

**Tech Stack:** Python dataclasses, local JSON persistence, FastAPI schemas/routers for draft asset management, pytest, existing Pixelle `StoryboardPlan` and Stage 1A `PromptPlan`.

---

## Planning Authority

This plan implements Stage 2 contract work only. It is governed by:

- `docs/pixelle_video_full_planning_md/03_IP_LIBRARY_AND_VISUAL_CONSISTENCY.md`
- `docs/pixelle_video_full_planning_md/04_PROMPT_COMPOSER_AND_SCENE_CASTING.md`
- `docs/pixelle_video_full_planning_md/15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md`

Repository override:

```text
AGENTS.md forbids git worktree use in this repository.
Execute in the current workspace with narrow staging and atomic commits.
Use Chinese commit messages.
```

## Scope

This plan implements:

- `AssetBible`.
- `IPProfile`.
- `CharacterProfile`.
- `SceneAsset`.
- `PropAsset`.
- `StyleProfile`.
- `SceneCast`.
- Local AssetBible store.
- SceneCast validation.
- PromptComposer extension that fills `PromptPlan.character_ids`, `scene_id`, `prop_ids`, and `style_id`.

This plan does not implement:

- Reference image management.
- LoRA management.
- Image-to-image consistency.
- Provider routing.
- Billing or permissions.
- Main generation-path integration before Stage 1A PromptPlan is stable.

## File Structure

- Create `pixelle_video/models/asset_bible.py`: asset and IP contracts.
- Create `pixelle_video/models/scene_cast.py`: frame-level cast contracts.
- Create `pixelle_video/services/asset_bible_service.py`: local JSON asset bible store.
- Create `pixelle_video/services/scene_casting.py`: validation and cast creation helpers.
- Create `pixelle_video/services/prompt_composer.py`: Stage 2 reserved-field projection into PromptPlan.
- Create `api/schemas/asset_bible.py`: draft asset request/response schemas.
- Create `api/routers/asset_bible.py`: local asset bible CRUD endpoints.
- Modify `api/app.py`: include router after local tests pass.
- Add tests:
  - `tests/test_asset_bible_models.py`
  - `tests/test_asset_bible_service.py`
  - `tests/test_scene_casting.py`
  - `tests/test_prompt_composer_asset_fields.py`
  - `tests/test_asset_bible_api.py`

---

### Task 1: AssetBible And IP Domain Models

**Files:**
- Create: `pixelle_video/models/asset_bible.py`
- Test: `tests/test_asset_bible_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_asset_bible_models.py
from pixelle_video.models.asset_bible import (
    AssetBible,
    CharacterProfile,
    IPProfile,
    PropAsset,
    SceneAsset,
    StyleProfile,
)


def test_asset_bible_preserves_ip_character_scene_prop_and_style():
    ip = IPProfile.create(
        project_id="project-1",
        name="原创侦探世界",
        style_hint="noir comic",
        world_hint="rainy neon city",
        forbidden_elements=["known copyrighted character"],
    )
    character = CharacterProfile.create(
        ip_id=ip.ip_id,
        name="林岚",
        visual_traits=["short black hair", "brown trench coat"],
        personality="calm detective",
    )
    scene = SceneAsset.create(ip_id=ip.ip_id, name="霓虹巷口", visual_description="narrow neon alley")
    prop = PropAsset.create(ip_id=ip.ip_id, name="旧雨伞", visual_description="black umbrella")
    style = StyleProfile.create(ip_id=ip.ip_id, name="黑色漫画", prompt_hint="high contrast noir comic")

    bible = AssetBible.create(
        project_id="project-1",
        ip_profile=ip,
        characters=[character],
        scenes=[scene],
        props=[prop],
        styles=[style],
    )
    restored = AssetBible.from_dict(bible.to_dict())

    assert restored.ip_profile.name == "原创侦探世界"
    assert restored.characters[0].character_id.startswith("char_")
    assert restored.scenes[0].scene_id.startswith("scene_")
    assert restored.props[0].prop_id.startswith("prop_")
    assert restored.styles[0].style_id.startswith("style_")
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_asset_bible_models.py -v`

Expected: fail with missing `asset_bible` module.

- [ ] **Step 3: Create AssetBible models**

```python
# pixelle_video/models/asset_bible.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_copy(item) for item in value]
    return value


@dataclass(frozen=True)
class IPProfile:
    ip_id: str
    project_id: str
    name: str
    style_hint: str | None = None
    world_hint: str | None = None
    forbidden_elements: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        name: str,
        style_hint: str | None = None,
        world_hint: str | None = None,
        forbidden_elements: Sequence[str] = (),
    ) -> "IPProfile":
        return cls(
            ip_id=stable_id("ip", project_id, name),
            project_id=project_id,
            name=name,
            style_hint=style_hint,
            world_hint=world_hint,
            forbidden_elements=tuple(forbidden_elements),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ip_id": self.ip_id,
            "project_id": self.project_id,
            "name": self.name,
            "style_hint": self.style_hint,
            "world_hint": self.world_hint,
            "forbidden_elements": list(self.forbidden_elements),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IPProfile":
        return cls(
            ip_id=str(payload["ip_id"]),
            project_id=str(payload["project_id"]),
            name=str(payload["name"]),
            style_hint=payload.get("style_hint"),
            world_hint=payload.get("world_hint"),
            forbidden_elements=tuple(payload.get("forbidden_elements") or ()),
        )


@dataclass(frozen=True)
class CharacterProfile:
    character_id: str
    ip_id: str
    name: str
    visual_traits: tuple[str, ...]
    personality: str | None = None

    @classmethod
    def create(cls, *, ip_id: str, name: str, visual_traits: Sequence[str], personality: str | None = None) -> "CharacterProfile":
        return cls(
            character_id=stable_id("char", ip_id, name),
            ip_id=ip_id,
            name=name,
            visual_traits=tuple(visual_traits),
            personality=personality,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "ip_id": self.ip_id,
            "name": self.name,
            "visual_traits": list(self.visual_traits),
            "personality": self.personality,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CharacterProfile":
        return cls(
            character_id=str(payload["character_id"]),
            ip_id=str(payload["ip_id"]),
            name=str(payload["name"]),
            visual_traits=tuple(payload.get("visual_traits") or ()),
            personality=payload.get("personality"),
        )


@dataclass(frozen=True)
class SceneAsset:
    scene_id: str
    ip_id: str
    name: str
    visual_description: str

    @classmethod
    def create(cls, *, ip_id: str, name: str, visual_description: str) -> "SceneAsset":
        return cls(stable_id("scene", ip_id, name), ip_id, name, visual_description)

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "ip_id": self.ip_id, "name": self.name, "visual_description": self.visual_description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SceneAsset":
        return cls(str(payload["scene_id"]), str(payload["ip_id"]), str(payload["name"]), str(payload["visual_description"]))


@dataclass(frozen=True)
class PropAsset:
    prop_id: str
    ip_id: str
    name: str
    visual_description: str

    @classmethod
    def create(cls, *, ip_id: str, name: str, visual_description: str) -> "PropAsset":
        return cls(stable_id("prop", ip_id, name), ip_id, name, visual_description)

    def to_dict(self) -> dict[str, Any]:
        return {"prop_id": self.prop_id, "ip_id": self.ip_id, "name": self.name, "visual_description": self.visual_description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PropAsset":
        return cls(str(payload["prop_id"]), str(payload["ip_id"]), str(payload["name"]), str(payload["visual_description"]))


@dataclass(frozen=True)
class StyleProfile:
    style_id: str
    ip_id: str
    name: str
    prompt_hint: str

    @classmethod
    def create(cls, *, ip_id: str, name: str, prompt_hint: str) -> "StyleProfile":
        return cls(stable_id("style", ip_id, name), ip_id, name, prompt_hint)

    def to_dict(self) -> dict[str, Any]:
        return {"style_id": self.style_id, "ip_id": self.ip_id, "name": self.name, "prompt_hint": self.prompt_hint}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StyleProfile":
        return cls(str(payload["style_id"]), str(payload["ip_id"]), str(payload["name"]), str(payload["prompt_hint"]))


@dataclass(frozen=True)
class AssetBible:
    asset_bible_id: str
    project_id: str
    ip_profile: IPProfile
    characters: tuple[CharacterProfile, ...] = field(default_factory=tuple)
    scenes: tuple[SceneAsset, ...] = field(default_factory=tuple)
    props: tuple[PropAsset, ...] = field(default_factory=tuple)
    styles: tuple[StyleProfile, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        ip_profile: IPProfile,
        characters: Sequence[CharacterProfile] = (),
        scenes: Sequence[SceneAsset] = (),
        props: Sequence[PropAsset] = (),
        styles: Sequence[StyleProfile] = (),
    ) -> "AssetBible":
        return cls(
            asset_bible_id=stable_id("asset_bible", project_id, ip_profile.ip_id),
            project_id=project_id,
            ip_profile=ip_profile,
            characters=tuple(characters),
            scenes=tuple(scenes),
            props=tuple(props),
            styles=tuple(styles),
        )

    def character_ids(self) -> set[str]:
        return {item.character_id for item in self.characters}

    def scene_ids(self) -> set[str]:
        return {item.scene_id for item in self.scenes}

    def prop_ids(self) -> set[str]:
        return {item.prop_id for item in self.props}

    def style_ids(self) -> set[str]:
        return {item.style_id for item in self.styles}

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_bible_id": self.asset_bible_id,
            "project_id": self.project_id,
            "ip_profile": self.ip_profile.to_dict(),
            "characters": [item.to_dict() for item in self.characters],
            "scenes": [item.to_dict() for item in self.scenes],
            "props": [item.to_dict() for item in self.props],
            "styles": [item.to_dict() for item in self.styles],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssetBible":
        return cls(
            asset_bible_id=str(payload["asset_bible_id"]),
            project_id=str(payload["project_id"]),
            ip_profile=IPProfile.from_dict(payload["ip_profile"]),
            characters=tuple(CharacterProfile.from_dict(item) for item in payload.get("characters") or ()),
            scenes=tuple(SceneAsset.from_dict(item) for item in payload.get("scenes") or ()),
            props=tuple(PropAsset.from_dict(item) for item in payload.get("props") or ()),
            styles=tuple(StyleProfile.from_dict(item) for item in payload.get("styles") or ()),
            created_at=str(payload["created_at"]),
        )


__all__ = ["AssetBible", "CharacterProfile", "IPProfile", "PropAsset", "SceneAsset", "StyleProfile"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_asset_bible_models.py -v`

Expected: one test passes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_asset_bible_models.py pixelle_video/models/asset_bible.py
git commit -m "feat: 新增资产圣经领域模型"
```

---

### Task 2: Local AssetBible Service

**Files:**
- Create: `pixelle_video/services/asset_bible_service.py`
- Test: `tests/test_asset_bible_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_asset_bible_service.py
import pytest

from pixelle_video.models.asset_bible import AssetBible, IPProfile
from pixelle_video.services.asset_bible_service import LocalAssetBibleService


@pytest.mark.asyncio
async def test_asset_bible_service_saves_and_loads_project_bible(tmp_path):
    service = LocalAssetBibleService(output_dir=tmp_path)
    ip = IPProfile.create(project_id="project-1", name="原创世界")
    bible = AssetBible.create(project_id="project-1", ip_profile=ip)

    await service.save(bible)
    loaded = await service.load(project_id="project-1")

    assert loaded == bible
    assert (tmp_path / "projects" / "project-1" / "asset_bible.json").exists()
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_asset_bible_service.py -v`

Expected: fail with missing `asset_bible_service`.

- [ ] **Step 3: Create service**

```python
# pixelle_video/services/asset_bible_service.py
from __future__ import annotations

import json
from pathlib import Path

from pixelle_video.models.asset_bible import AssetBible


class LocalAssetBibleService:
    def __init__(self, output_dir: str | Path = "output") -> None:
        self.output_dir = Path(output_dir)

    def _path(self, project_id: str) -> Path:
        return self.output_dir / "projects" / project_id / "asset_bible.json"

    async def save(self, asset_bible: AssetBible) -> None:
        path = self._path(asset_bible.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asset_bible.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    async def load(self, project_id: str) -> AssetBible | None:
        path = self._path(project_id)
        if not path.exists():
            return None
        return AssetBible.from_dict(json.loads(path.read_text(encoding="utf-8")))


__all__ = ["LocalAssetBibleService"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_asset_bible_service.py -v`

Expected: one test passes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_asset_bible_service.py pixelle_video/services/asset_bible_service.py
git commit -m "feat: 新增资产圣经本地存储"
```

---

### Task 3: SceneCast Model And Validation

**Files:**
- Create: `pixelle_video/models/scene_cast.py`
- Create: `pixelle_video/services/scene_casting.py`
- Test: `tests/test_scene_casting.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scene_casting.py
import pytest

from pixelle_video.models.asset_bible import AssetBible, CharacterProfile, IPProfile, SceneAsset, StyleProfile
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.scene_casting import validate_scene_cast


def _asset_bible():
    ip = IPProfile.create(project_id="project-1", name="原创世界")
    char = CharacterProfile.create(ip_id=ip.ip_id, name="林岚", visual_traits=["trench coat"])
    scene = SceneAsset.create(ip_id=ip.ip_id, name="巷口", visual_description="neon alley")
    style = StyleProfile.create(ip_id=ip.ip_id, name="漫画", prompt_hint="comic")
    return AssetBible.create(project_id="project-1", ip_profile=ip, characters=[char], scenes=[scene], styles=[style])


def test_scene_cast_validates_referenced_ids():
    bible = _asset_bible()
    cast = SceneCast(
        frame_id="frame_0001",
        character_ids=[bible.characters[0].character_id],
        scene_id=bible.scenes[0].scene_id,
        prop_ids=[],
        style_id=bible.styles[0].style_id,
    )

    validate_scene_cast(cast, asset_bible=bible)


def test_scene_cast_rejects_unknown_character_id():
    bible = _asset_bible()
    cast = SceneCast(frame_id="frame_0001", character_ids=["char_missing"])

    with pytest.raises(ValueError, match="unknown character_id"):
        validate_scene_cast(cast, asset_bible=bible)
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_scene_casting.py -v`

Expected: fail with missing `scene_cast`.

- [ ] **Step 3: Create SceneCast model**

```python
# pixelle_video/models/scene_cast.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SceneCast:
    frame_id: str
    character_ids: tuple[str, ...] = field(default_factory=tuple)
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = field(default_factory=tuple)
    style_id: str | None = None
    notes: str | None = None

    def __init__(
        self,
        *,
        frame_id: str,
        character_ids: Sequence[str] = (),
        scene_id: str | None = None,
        prop_ids: Sequence[str] = (),
        style_id: str | None = None,
        notes: str | None = None,
    ) -> None:
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "character_ids", tuple(character_ids))
        object.__setattr__(self, "scene_id", scene_id)
        object.__setattr__(self, "prop_ids", tuple(prop_ids))
        object.__setattr__(self, "style_id", style_id)
        object.__setattr__(self, "notes", notes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "style_id": self.style_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SceneCast":
        return cls(
            frame_id=str(payload["frame_id"]),
            character_ids=payload.get("character_ids") or (),
            scene_id=payload.get("scene_id"),
            prop_ids=payload.get("prop_ids") or (),
            style_id=payload.get("style_id"),
            notes=payload.get("notes"),
        )


__all__ = ["SceneCast"]
```

- [ ] **Step 4: Create validator**

```python
# pixelle_video/services/scene_casting.py
from __future__ import annotations

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.scene_cast import SceneCast


def validate_scene_cast(scene_cast: SceneCast, *, asset_bible: AssetBible) -> None:
    for character_id in scene_cast.character_ids:
        if character_id not in asset_bible.character_ids():
            raise ValueError(f"unknown character_id: {character_id}")
    if scene_cast.scene_id and scene_cast.scene_id not in asset_bible.scene_ids():
        raise ValueError(f"unknown scene_id: {scene_cast.scene_id}")
    for prop_id in scene_cast.prop_ids:
        if prop_id not in asset_bible.prop_ids():
            raise ValueError(f"unknown prop_id: {prop_id}")
    if scene_cast.style_id and scene_cast.style_id not in asset_bible.style_ids():
        raise ValueError(f"unknown style_id: {scene_cast.style_id}")


__all__ = ["validate_scene_cast"]
```

- [ ] **Step 5: Run the tests to verify pass**

Run: `pytest tests/test_scene_casting.py -v`

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_scene_casting.py pixelle_video/models/scene_cast.py pixelle_video/services/scene_casting.py
git commit -m "feat: 新增场景角色分配校验"
```

---

### Task 4: PromptComposer Reserved Field Projection

**Files:**
- Create: `pixelle_video/services/prompt_composer.py`
- Test: `tests/test_prompt_composer_asset_fields.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompt_composer_asset_fields.py
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.prompt_composer import apply_scene_cast_to_prompt_plan


def test_apply_scene_cast_fills_reserved_prompt_plan_fields():
    plan = PromptPlan.create(
        frame_id="frame_0001",
        storyboard_plan_id="plan-1",
        image_prompt_draft_id="draft-1",
        prompt_sections={"image_prompt": "base prompt"},
        final_prompt="base prompt",
    )
    cast = SceneCast(
        frame_id="frame_0001",
        character_ids=["char_1"],
        scene_id="scene_1",
        prop_ids=["prop_1"],
        style_id="style_1",
    )

    updated = apply_scene_cast_to_prompt_plan(plan, scene_cast=cast)

    assert updated.prompt_plan_id == plan.prompt_plan_id
    assert updated.character_ids == ("char_1",)
    assert updated.scene_id == "scene_1"
    assert updated.prop_ids == ("prop_1",)
    assert updated.style_id == "style_1"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_prompt_composer_asset_fields.py -v`

Expected: fail with missing `prompt_composer`.

- [ ] **Step 3: Create projection helper**

```python
# pixelle_video/services/prompt_composer.py
from __future__ import annotations

from dataclasses import replace

from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast


def apply_scene_cast_to_prompt_plan(prompt_plan: PromptPlan, *, scene_cast: SceneCast) -> PromptPlan:
    if prompt_plan.frame_id != scene_cast.frame_id:
        raise ValueError("scene_cast frame_id must match prompt_plan frame_id")
    return replace(
        prompt_plan,
        character_ids=tuple(scene_cast.character_ids),
        scene_id=scene_cast.scene_id,
        prop_ids=tuple(scene_cast.prop_ids),
        style_id=scene_cast.style_id,
    )


__all__ = ["apply_scene_cast_to_prompt_plan"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_prompt_composer_asset_fields.py -v`

Expected: one test passes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_composer_asset_fields.py pixelle_video/services/prompt_composer.py
git commit -m "feat: 支持场景角色投影到提示词计划"
```

---

### Task 5: AssetBible Draft API

**Files:**
- Create: `api/schemas/asset_bible.py`
- Create: `api/routers/asset_bible.py`
- Modify: `api/app.py`
- Test: `tests/test_asset_bible_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_asset_bible_api.py
import pytest
from httpx import ASGITransport, AsyncClient

from api.app import app


@pytest.mark.asyncio
async def test_create_minimal_asset_bible_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/projects/project-1/asset-bible",
            json={
                "ip_name": "原创侦探世界",
                "style_hint": "noir comic",
                "world_hint": "rainy neon city",
                "forbidden_elements": ["known copyrighted character"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["ip_profile"]["name"] == "原创侦探世界"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_asset_bible_api.py -v`

Expected: fail because asset bible API does not exist.

- [ ] **Step 3: Add schemas**

```python
# api/schemas/asset_bible.py
from __future__ import annotations

from pydantic import BaseModel, Field


class AssetBibleCreateRequest(BaseModel):
    ip_name: str = Field(..., min_length=1)
    style_hint: str | None = None
    world_hint: str | None = None
    forbidden_elements: list[str] = Field(default_factory=list)


class AssetBibleResponse(BaseModel):
    asset_bible_id: str
    project_id: str
    ip_profile: dict
    characters: list[dict]
    scenes: list[dict]
    props: list[dict]
    styles: list[dict]
```

- [ ] **Step 4: Add router**

```python
# api/routers/asset_bible.py
from __future__ import annotations

from fastapi import APIRouter

from api.schemas.asset_bible import AssetBibleCreateRequest, AssetBibleResponse
from pixelle_video.models.asset_bible import AssetBible, IPProfile
from pixelle_video.services.asset_bible_service import LocalAssetBibleService

router = APIRouter(prefix="/projects", tags=["AssetBible"])


@router.post("/{project_id}/asset-bible", response_model=AssetBibleResponse)
async def create_asset_bible(project_id: str, request: AssetBibleCreateRequest) -> AssetBibleResponse:
    ip_profile = IPProfile.create(
        project_id=project_id,
        name=request.ip_name,
        style_hint=request.style_hint,
        world_hint=request.world_hint,
        forbidden_elements=request.forbidden_elements,
    )
    asset_bible = AssetBible.create(project_id=project_id, ip_profile=ip_profile)
    await LocalAssetBibleService().save(asset_bible)
    return AssetBibleResponse(**asset_bible.to_dict())
```

- [ ] **Step 5: Register router**

Modify `api/app.py`:

```python
from api.routers.asset_bible import router as asset_bible_router
```

Register near other routers:

```python
app.include_router(asset_bible_router, prefix=api_config.api_prefix)
```

- [ ] **Step 6: Run the tests to verify pass**

Run: `pytest tests/test_asset_bible_api.py -v`

Expected: one test passes.

- [ ] **Step 7: Commit**

```bash
git add tests/test_asset_bible_api.py api/schemas/asset_bible.py api/routers/asset_bible.py api/app.py
git commit -m "feat: 新增资产圣经草稿接口"
```

---

## Stage 2 Verification Checklist

Run:

```bash
pytest \
  tests/test_asset_bible_models.py \
  tests/test_asset_bible_service.py \
  tests/test_scene_casting.py \
  tests/test_prompt_composer_asset_fields.py \
  tests/test_asset_bible_api.py \
  tests/test_prompt_plan_model.py \
  -v
```

Expected: all selected tests pass.

## Implementation Notes

- Do not connect AssetBible or SceneCast to the production generation path until Stage 1A PromptPlan exists.
- Do not introduce reference image, LoRA, or image-to-image workflows in this plan.
- Do not modify the core shape of `PromptPlan`; only fill reserved fields.
- Do not implement billing, permissions, ProviderCapability, or public API policy here.
- Stage 2 work can run in parallel with Stage 1A as long as tests use local fixtures and do not mutate Stage 1A files without coordination.

## Spec Coverage Self-Review

- IPProfile, CharacterProfile, SceneAsset, PropAsset, StyleProfile, and AssetBible are covered by Task 1.
- Local persistence is covered by Task 2.
- SceneCast and ID validation are covered by Task 3.
- PromptComposer reserved-field projection is covered by Task 4.
- Draft API entry is covered by Task 5.
- Placeholder scan: no placeholder tasks remain; each task has file paths, test commands, expected failures, and commit commands.
