# Stage 1B Stale 写入点集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Stage 1B stale dependency propagation to real AssetBible, SceneCast, PromptPlan, and image artifact write points without changing Stage 2 preview-only behavior.

**Architecture:** Add small application services that sit above existing repositories. Repositories keep their save/load responsibility; the new services generate public version tokens, upsert dependency edges, and call `StaleDependencyPropagationService`. API routes switch to the stale-aware service only for AssetBible and SceneCast save endpoints; Stage 2 projection preview remains read-only.

**Tech Stack:** Python dataclasses, repository Protocols, pytest async tests, FastAPI route tests, existing Pixelle domain models.

---

## Planning Authority

This plan implements:

- `docs/superpowers/specs/2026-05-01-stage1b-stale-write-integration-design.md`
- `docs/superpowers/specs/2026-05-01-stage1b-stale-dependency-propagation-design.md`
- `docs/superpowers/plans/2026-05-01-stage1b-stale-dependency-propagation-implementation.md`

Hard boundaries:

- Do not persist Stage 2 projection preview.
- Do not mark stale from Stage 2 projection preview.
- Do not connect provider routing, ComfyUI routing, TTS, HyperFrames, or main generation paths.
- Do not expose local paths, workflow paths, provider URLs, or storage paths as dependency IDs.
- Keep text rendering fields out of PromptPlan projection and AssetBible `StyleProfile.metadata`.

Naming note: the design document calls the image artifact edge writer `StaleAwareArtifactWriteService`. This implementation plan uses `ArtifactDependencyWriteService` because the component does not save artifacts or trigger stale propagation; it only records the `image_artifact.generated_from_prompt_plan` dependency edge after the real artifact write point succeeds.

## File Structure

- Create `pixelle_video/services/dependency_versions.py`: stable public version token generator.
- Create `tests/test_dependency_versions.py`: deterministic token and path/URL boundary tests.
- Create `pixelle_video/services/stale_write_integration.py`: stale-aware AssetBible, SceneCast, and PromptPlan write services plus shared result dataclasses.
- Create `pixelle_video/services/artifact_dependency_integration.py`: image artifact dependency edge recording service.
- Create `tests/test_stale_write_integration.py`: unit tests for AssetBible, SceneCast, and PromptPlan write coordination.
- Create `tests/test_artifact_dependency_integration.py`: unit tests for image artifact dependency edge recording.
- Modify `pixelle_video/services/storyboard_workbench.py`: optionally record image artifact dependency edges after regeneration results are persisted.
- Modify `tests/test_storyboard_frame_regeneration.py`: regression coverage for real workbench artifact dependency recording.
- Modify `api/routers/asset_bible.py`: route save endpoints through `StaleAwareAssetBibleWriteService` when stale repositories are configured.
- Modify `tests/test_asset_bible_api.py`: route-level coverage for stale write integration and fallback dependency errors.
- Modify `tests/test_asset_bible_api.py`: boundary test proving projection preview does not call stale-aware write service.

## Task 1: Dependency Version Tokens

**Files:**
- Create: `tests/test_dependency_versions.py`
- Create: `pixelle_video/services/dependency_versions.py`

- [ ] **Step 1: Write failing tests for stable public version tokens**

Create `tests/test_dependency_versions.py`:

```python
from pixelle_video.models.asset_bible import AssetBible, CharacterProfile, IPProfile
from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan, PromptPlanBundle
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.models.artifact import ArtifactVersion, ArtifactVersionStatus
from pixelle_video.services.dependency_versions import DependencyVersionService


def test_asset_bible_version_is_stable_for_same_public_payload():
    service = DependencyVersionService()
    first = AssetBible(
        asset_bible_id="bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        ip_profiles=(
            IPProfile(
                ip_profile_id="ip_main",
                workspace_id="workspace_1",
                project_id="project_1",
                name="Pixelle Demo",
                metadata={"last_saved_by": "user_1"},
            ),
        ),
        character_profiles=(
            CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
            ),
        ),
        metadata={"updated_at": "2026-05-01T10:00:00Z"},
    )
    second = AssetBible.from_dict({
        **first.to_dict(),
        "metadata": {"updated_at": "2026-05-01T11:00:00Z"},
        "ip_profiles": [
            {
                **first.to_dict()["ip_profiles"][0],
                "metadata": {"last_saved_by": "user_2"},
            }
        ],
    })

    assert service.version_for_asset_bible(first) == service.version_for_asset_bible(second)
    assert service.version_for_asset_bible(first).startswith("asset_bible_rev_")
    assert "\\" not in service.version_for_asset_bible(first)
    assert "/" not in service.version_for_asset_bible(first)
    assert "://" not in service.version_for_asset_bible(first)


def test_scene_cast_version_changes_when_business_payload_changes():
    service = DependencyVersionService()
    first = SceneCast(
        scene_cast_id="cast_frame_0001",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        asset_bible_id="bible_demo",
        character_ids=("char_luna",),
        continuity_notes=("Keep goggles visible.",),
    )
    second = SceneCast.from_dict({
        **first.to_dict(),
        "continuity_notes": ["Use the red jacket."],
    })

    assert service.version_for_scene_cast(first) != service.version_for_scene_cast(second)
    assert service.version_for_scene_cast(first).startswith("scene_cast_rev_")


def test_prompt_plan_bundle_versions_are_public_and_deterministic():
    service = DependencyVersionService()
    draft = ImagePromptDraft(
        image_prompt_draft_id="draft_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        prompt_text="Show Luna in the lab.",
    )
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_1",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
        metadata={"scene_cast_id": "cast_frame_0001"},
    )
    bundle = PromptPlanBundle(
        storyboard_plan_id="storyboard_plan_1",
        image_prompt_drafts=(draft,),
        prompt_plans=(plan,),
    )

    first = service.version_for_prompt_plan(bundle.prompt_plans[0])
    second = service.version_for_prompt_plan(PromptPlan.from_dict(bundle.prompt_plans[0].to_dict()))

    assert first == second
    assert first.startswith("prompt_plan_rev_")


def test_artifact_version_token_uses_public_artifact_identity_not_storage_key():
    service = DependencyVersionService()
    version = ArtifactVersion(
        version_id="artifact_version_1",
        artifact_id="artifact_frame_0001_image",
        workspace_id="workspace_1",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_1",
        storage_key="artifacts/workspace_1/frame_0001/artifact_version_1.png",
        status=ArtifactVersionStatus.SUCCEEDED,
        provider="comfyui",
    )

    token = service.version_for_artifact_version(version)

    assert token.startswith("image_artifact_rev_")
    assert "artifacts" not in token
    assert "/" not in token
    assert "\\" not in token
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_dependency_versions.py
```

Expected: FAIL because `pixelle_video.services.dependency_versions` does not exist.

- [ ] **Step 3: Implement `DependencyVersionService`**

Create `pixelle_video/services/dependency_versions.py`:

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pixelle_video.models.artifact import ArtifactVersion
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast


TRANSIENT_KEYS = {
    "created_at",
    "updated_at",
    "generated_at",
    "last_saved_by",
    "last_saved_at",
}


class DependencyVersionService:
    def version_for_asset_bible(self, asset_bible: AssetBible) -> str:
        return _version_token("asset_bible", asset_bible.to_dict())

    def version_for_scene_cast(self, scene_cast: SceneCast) -> str:
        return _version_token("scene_cast", scene_cast.to_dict())

    def version_for_prompt_plan(self, prompt_plan: PromptPlan) -> str:
        return _version_token("prompt_plan", prompt_plan.to_dict())

    def version_for_artifact_version(self, version: ArtifactVersion) -> str:
        payload = {
            "artifact_id": version.artifact_id,
            "version_id": version.version_id,
            "workspace_id": version.workspace_id,
            "frame_id": version.frame_id,
            "source_prompt_plan_id": version.source_prompt_plan_id,
            "status": version.status.value,
            "provider": version.provider,
            "width": version.width,
            "height": version.height,
            "trace_event_id": version.trace_event_id,
            "metadata": version.metadata,
        }
        return _version_token("image_artifact", payload)


def _version_token(prefix: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _strip_transient(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_rev_{digest}"


def _strip_transient(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_transient(item)
            for key, item in value.items()
            if str(key) not in TRANSIENT_KEYS
        }
    if isinstance(value, list | tuple):
        return [_strip_transient(item) for item in value]
    return deepcopy(value)
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_dependency_versions.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pixelle_video/services/dependency_versions.py tests/test_dependency_versions.py
git commit -m "feat: 生成 stale 公开版本 token"
git push origin dev
```

## Task 2: Stale-Aware AssetBible And SceneCast Writes

**Files:**
- Create/Modify: `pixelle_video/services/stale_write_integration.py`
- Test: `tests/test_stale_write_integration.py`

- [ ] **Step 1: Write failing tests for AssetBible and SceneCast write integration**

Create `tests/test_stale_write_integration.py` with shared fakes and these tests:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.asset_bible import AssetBible, CharacterProfile, IPProfile
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.stale_write_integration import StaleAwareAssetBibleWriteService


@dataclass
class FakeAssetBibleRepository:
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def save_asset_bible(self, workspace_id: str, asset_bible: dict[str, Any]) -> dict[str, Any]:
        self.asset_bibles[(workspace_id, asset_bible["asset_bible_id"])] = dict(asset_bible)
        return dict(asset_bible)

    async def load_asset_bible(self, workspace_id: str, asset_bible_id: str) -> dict[str, Any] | None:
        return self.asset_bibles.get((workspace_id, asset_bible_id))

    async def list_asset_bibles(self, workspace_id: str, project_id: str) -> list[dict[str, Any]]:
        return []

    async def save_scene_cast(self, workspace_id: str, scene_cast: dict[str, Any]) -> dict[str, Any]:
        self.scene_casts[(workspace_id, scene_cast["scene_cast_id"])] = dict(scene_cast)
        return dict(scene_cast)

    async def load_scene_cast(self, workspace_id: str, scene_cast_id: str) -> dict[str, Any] | None:
        return self.scene_casts.get((workspace_id, scene_cast_id))

    async def list_scene_casts(self, workspace_id: str, project_id: str, asset_bible_id: str) -> list[dict[str, Any]]:
        return []


@dataclass
class FakeDependencyEdgeRepository:
    edges: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges[(workspace_id, edge["edge_id"])] = dict(edge)
        return dict(edge)

    async def list_downstream_edges(self, workspace_id: str, upstream_type: str, upstream_id: str) -> list[dict[str, Any]]:
        return [
            edge
            for (stored_workspace_id, _), edge in self.edges.items()
            if stored_workspace_id == workspace_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class FakeStaleMarkRepository:
    marks: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = field(default_factory=dict)

    async def mark_stale(self, workspace_id: str, mark: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        key = (
            workspace_id,
            mark["target_type"],
            mark["target_id"],
            mark["reason_code"],
            mark["upstream_type"],
            mark["upstream_id"],
            mark["upstream_version"],
        )
        if key in self.marks:
            return dict(self.marks[key]), False
        self.marks[key] = dict(mark)
        return dict(mark), True

    async def list_stale_marks(self, workspace_id: str, target_type: str, target_id: str) -> list[dict[str, Any]]:
        return []


def _asset_bible() -> AssetBible:
    return AssetBible(
        asset_bible_id="bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        ip_profiles=(
            IPProfile(
                ip_profile_id="ip_main",
                workspace_id="workspace_1",
                project_id="project_1",
                name="Pixelle Demo",
            ),
        ),
        character_profiles=(
            CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
            ),
        ),
    )


def _scene_cast() -> SceneCast:
    return SceneCast(
        scene_cast_id="cast_frame_0001",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        asset_bible_id="bible_demo",
        character_ids=("char_luna",),
    )


@pytest.mark.asyncio
async def test_save_asset_bible_triggers_asset_bible_stale_propagation():
    assets = FakeAssetBibleRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    service = StaleAwareAssetBibleWriteService(
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_asset_bible("workspace_1", _asset_bible())

    assert result.saved_payload["asset_bible_id"] == "bible_demo"
    assert result.version_token.startswith("asset_bible_rev_")
    assert result.propagation_summary.upstream_type == "asset_bible"
    assert result.propagation_summary.upstream_id == "bible_demo"
    assert result.propagation_summary.upstream_version == result.version_token


@pytest.mark.asyncio
async def test_save_scene_cast_writes_asset_bible_dependency_edge_and_triggers_scene_cast_propagation():
    assets = FakeAssetBibleRepository()
    await assets.save_asset_bible("workspace_1", _asset_bible().to_dict())
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    service = StaleAwareAssetBibleWriteService(
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_scene_cast("workspace_1", _scene_cast())

    edge = next(iter(edges.edges.values()))
    assert edge["edge_id"] == "dep_scene_cast_cast_frame_0001_asset_bible_bible_demo"
    assert edge["upstream_type"] == "asset_bible"
    assert edge["upstream_id"] == "bible_demo"
    assert edge["upstream_version"].startswith("asset_bible_rev_")
    assert edge["downstream_type"] == "scene_cast"
    assert edge["downstream_id"] == "cast_frame_0001"
    assert edge["relation"] == "scene_cast.references_asset_bible"
    assert result.propagation_summary.upstream_type == "scene_cast"
    assert result.propagation_summary.upstream_id == "cast_frame_0001"
    assert result.version_token.startswith("scene_cast_rev_")
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_stale_write_integration.py
```

Expected: FAIL because `StaleAwareAssetBibleWriteService` does not exist.

- [ ] **Step 3: Implement AssetBible and SceneCast stale-aware write service**

Create `pixelle_video/services/stale_write_integration.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.models.stale_dependency import DependencyEdge, StalePropagationSummary, UpstreamChangeEvent
from pixelle_video.repositories.assets import AssetBibleRepository
from pixelle_video.repositories.stale_dependencies import DependencyEdgeRepository, StaleMarkRepository
from pixelle_video.services.dependency_versions import DependencyVersionService
from pixelle_video.services.stale_dependency_propagation import StaleDependencyPropagationService


class StaleWriteIntegrationError(ValueError):
    pass


class StaleWriteDependencyNotFoundError(StaleWriteIntegrationError):
    pass


@dataclass(frozen=True)
class StaleAwareWriteResult:
    saved_payload: Mapping[str, Any]
    version_tokens: tuple[str, ...]
    propagation_summaries: tuple[StalePropagationSummary, ...]
    dependency_edges: tuple[DependencyEdge, ...] = field(default_factory=tuple)

    @property
    def version_token(self) -> str:
        if len(self.version_tokens) != 1:
            raise StaleWriteIntegrationError("write result contains multiple version tokens")
        return self.version_tokens[0]

    @property
    def propagation_summary(self) -> StalePropagationSummary:
        if len(self.propagation_summaries) != 1:
            raise StaleWriteIntegrationError("write result contains multiple propagation summaries")
        return self.propagation_summaries[0]


class StaleAwareAssetBibleWriteService:
    def __init__(
        self,
        *,
        asset_bible_repository: AssetBibleRepository,
        edge_repository: DependencyEdgeRepository,
        stale_repository: StaleMarkRepository,
        version_service: DependencyVersionService | None = None,
    ) -> None:
        self.asset_bible_repository = asset_bible_repository
        self.edge_repository = edge_repository
        self.stale_repository = stale_repository
        self.version_service = version_service or DependencyVersionService()
        self.propagation_service = StaleDependencyPropagationService(
            edge_repository=edge_repository,
            stale_repository=stale_repository,
        )

    async def save_asset_bible(self, workspace_id: str, asset_bible: AssetBible) -> StaleAwareWriteResult:
        saved = await self.asset_bible_repository.save_asset_bible(workspace_id, asset_bible.to_dict())
        saved_model = AssetBible.from_dict(saved)
        version_token = self.version_service.version_for_asset_bible(saved_model)
        summary = await self.propagation_service.propagate_upstream_change(
            UpstreamChangeEvent(
                workspace_id=workspace_id,
                project_id=saved_model.project_id,
                upstream_type="asset_bible",
                upstream_id=saved_model.asset_bible_id,
                upstream_version=version_token,
                reason_code="asset_bible_changed",
            )
        )
        return StaleAwareWriteResult(
            saved_payload=saved_model.to_dict(),
            version_tokens=(version_token,),
            propagation_summaries=(summary,),
        )

    async def save_scene_cast(self, workspace_id: str, scene_cast: SceneCast) -> StaleAwareWriteResult:
        asset_bible_payload = await self.asset_bible_repository.load_asset_bible(
            workspace_id,
            scene_cast.asset_bible_id,
        )
        if asset_bible_payload is None:
            raise StaleWriteDependencyNotFoundError("asset bible draft was not found")
        asset_bible = AssetBible.from_dict(asset_bible_payload)
        asset_bible_version = self.version_service.version_for_asset_bible(asset_bible)
        saved = await self.asset_bible_repository.save_scene_cast(workspace_id, scene_cast.to_dict())
        saved_model = SceneCast.from_dict(saved)
        scene_cast_version = self.version_service.version_for_scene_cast(saved_model)
        edge = DependencyEdge(
            edge_id=f"dep_scene_cast_{saved_model.scene_cast_id}_asset_bible_{saved_model.asset_bible_id}",
            workspace_id=workspace_id,
            project_id=saved_model.project_id,
            upstream_type="asset_bible",
            upstream_id=saved_model.asset_bible_id,
            upstream_version=asset_bible_version,
            downstream_type="scene_cast",
            downstream_id=saved_model.scene_cast_id,
            relation="scene_cast.references_asset_bible",
        )
        await self.edge_repository.save_dependency_edge(workspace_id, edge.to_dict())
        summary = await self.propagation_service.propagate_upstream_change(
            UpstreamChangeEvent(
                workspace_id=workspace_id,
                project_id=saved_model.project_id,
                upstream_type="scene_cast",
                upstream_id=saved_model.scene_cast_id,
                upstream_version=scene_cast_version,
                reason_code="scene_cast_changed",
            )
        )
        return StaleAwareWriteResult(
            saved_payload=saved_model.to_dict(),
            version_tokens=(scene_cast_version,),
            propagation_summaries=(summary,),
            dependency_edges=(edge,),
        )
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_dependency_versions.py tests/test_stale_write_integration.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pixelle_video/services/stale_write_integration.py tests/test_stale_write_integration.py
git commit -m "feat: 接入 AssetBible stale 写入协调"
git push origin dev
```

## Task 3: PromptPlan Bundle Write Integration

**Files:**
- Modify: `pixelle_video/services/stale_write_integration.py`
- Modify: `tests/test_stale_write_integration.py`

- [ ] **Step 1: Add failing PromptPlan integration tests**

Append to `tests/test_stale_write_integration.py`:

```python
from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan, PromptPlanBundle
from pixelle_video.services.stale_write_integration import StaleAwarePromptPlanWriteService


@dataclass
class FakePromptPlanRepository:
    bundles: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def save_prompt_plan_bundle(self, workspace_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
        self.bundles.append((workspace_id, dict(bundle)))
        return dict(bundle)

    async def load_prompt_plans_by_storyboard(self, workspace_id: str, storyboard_id: str) -> list[dict[str, Any]]:
        return []

    async def mark_prompt_plan_stale(
        self,
        workspace_id: str,
        prompt_plan_id: str,
        reason: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"prompt_plan_id": prompt_plan_id, "stale": True}


def _prompt_plan_bundle_with_scene_cast() -> PromptPlanBundle:
    draft = ImagePromptDraft(
        image_prompt_draft_id="draft_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        prompt_text="Show Luna in the lab.",
    )
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_1",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
        metadata={"scene_cast_id": "cast_frame_0001"},
    )
    return PromptPlanBundle(
        storyboard_plan_id="storyboard_plan_1",
        image_prompt_drafts=(draft,),
        prompt_plans=(plan,),
    )


@pytest.mark.asyncio
async def test_save_prompt_plan_bundle_writes_scene_cast_dependency_edge_and_triggers_prompt_plan_propagation():
    assets = FakeAssetBibleRepository()
    await assets.save_asset_bible("workspace_1", _asset_bible().to_dict())
    await assets.save_scene_cast("workspace_1", _scene_cast().to_dict())
    prompts = FakePromptPlanRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    service = StaleAwarePromptPlanWriteService(
        prompt_plan_repository=prompts,
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_prompt_plan_bundle(
        "workspace_1",
        "project_1",
        _prompt_plan_bundle_with_scene_cast(),
    )

    edge = next(iter(edges.edges.values()))
    assert edge["edge_id"] == "dep_prompt_plan_prompt_plan_1_scene_cast_cast_frame_0001"
    assert edge["upstream_type"] == "scene_cast"
    assert edge["upstream_id"] == "cast_frame_0001"
    assert edge["upstream_version"].startswith("scene_cast_rev_")
    assert edge["downstream_type"] == "prompt_plan"
    assert edge["downstream_id"] == "prompt_plan_1"
    assert edge["relation"] == "prompt_plan.uses_scene_cast"
    assert result.propagation_summary.upstream_type == "prompt_plan"
    assert result.propagation_summary.upstream_id == "prompt_plan_1"


@pytest.mark.asyncio
async def test_save_prompt_plan_bundle_without_public_dependency_source_does_not_guess_edges():
    assets = FakeAssetBibleRepository()
    prompts = FakePromptPlanRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    bundle = _prompt_plan_bundle_with_scene_cast()
    plan_payload = bundle.prompt_plans[0].to_dict()
    plan_payload["metadata"] = {}
    no_source_bundle = PromptPlanBundle(
        storyboard_plan_id=bundle.storyboard_plan_id,
        image_prompt_drafts=bundle.image_prompt_drafts,
        prompt_plans=(PromptPlan.from_dict(plan_payload),),
    )
    service = StaleAwarePromptPlanWriteService(
        prompt_plan_repository=prompts,
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_prompt_plan_bundle(
        "workspace_1",
        "project_1",
        no_source_bundle,
    )

    assert edges.edges == {}
    assert result.propagation_summary.upstream_type == "prompt_plan"
    assert result.propagation_summary.upstream_id == "prompt_plan_1"


@pytest.mark.asyncio
async def test_save_prompt_plan_bundle_preserves_every_prompt_plan_propagation_summary():
    assets = FakeAssetBibleRepository()
    await assets.save_asset_bible("workspace_1", _asset_bible().to_dict())
    await assets.save_scene_cast("workspace_1", _scene_cast().to_dict())
    prompts = FakePromptPlanRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    first_bundle = _prompt_plan_bundle_with_scene_cast()
    second_draft = ImagePromptDraft(
        image_prompt_draft_id="draft_2",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0002",
        prompt_text="Show Luna entering the observatory.",
    )
    second_plan = PromptPlan(
        prompt_plan_id="prompt_plan_2",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0002",
        image_prompt_draft_id="draft_2",
        prompt_sections={"visual_goal": "Show Luna entering the observatory."},
        final_prompt="Show Luna entering the observatory.",
        metadata={"scene_cast_id": "cast_frame_0001"},
    )
    bundle = PromptPlanBundle(
        storyboard_plan_id="storyboard_plan_1",
        image_prompt_drafts=(*first_bundle.image_prompt_drafts, second_draft),
        prompt_plans=(*first_bundle.prompt_plans, second_plan),
    )
    service = StaleAwarePromptPlanWriteService(
        prompt_plan_repository=prompts,
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_prompt_plan_bundle("workspace_1", "project_1", bundle)

    assert tuple(summary.upstream_id for summary in result.propagation_summaries) == (
        "prompt_plan_1",
        "prompt_plan_2",
    )
    assert len(result.version_tokens) == 2
    assert all(version.startswith("prompt_plan_rev_") for version in result.version_tokens)
    assert len(result.dependency_edges) == 2
```

- [ ] **Step 2: Run PromptPlan tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_stale_write_integration.py::test_save_prompt_plan_bundle_writes_scene_cast_dependency_edge_and_triggers_prompt_plan_propagation tests/test_stale_write_integration.py::test_save_prompt_plan_bundle_without_public_dependency_source_does_not_guess_edges tests/test_stale_write_integration.py::test_save_prompt_plan_bundle_preserves_every_prompt_plan_propagation_summary
```

Expected: FAIL because `StaleAwarePromptPlanWriteService` does not exist.

- [ ] **Step 3: Implement PromptPlan write service**

Update `pixelle_video/services/stale_write_integration.py` with:

```python
from pixelle_video.models.prompt_plan import PromptPlanBundle
from pixelle_video.repositories.prompt_plans import PromptPlanRepository


class StaleAwarePromptPlanWriteService:
    def __init__(
        self,
        *,
        prompt_plan_repository: PromptPlanRepository,
        asset_bible_repository: AssetBibleRepository,
        edge_repository: DependencyEdgeRepository,
        stale_repository: StaleMarkRepository,
        version_service: DependencyVersionService | None = None,
    ) -> None:
        self.prompt_plan_repository = prompt_plan_repository
        self.asset_bible_repository = asset_bible_repository
        self.edge_repository = edge_repository
        self.version_service = version_service or DependencyVersionService()
        self.propagation_service = StaleDependencyPropagationService(
            edge_repository=edge_repository,
            stale_repository=stale_repository,
        )

    async def save_prompt_plan_bundle(
        self,
        workspace_id: str,
        project_id: str,
        bundle: PromptPlanBundle,
    ) -> StaleAwareWriteResult:
        pending_edges: dict[str, DependencyEdge] = {}
        for prompt_plan in bundle.prompt_plans:
            edge = await self._edge_for_prompt_plan(workspace_id, project_id, prompt_plan)
            if edge is not None:
                pending_edges[prompt_plan.prompt_plan_id] = edge
        saved = await self.prompt_plan_repository.save_prompt_plan_bundle(workspace_id, bundle.to_dict())
        saved_bundle = PromptPlanBundle.from_dict(saved)
        edges: list[DependencyEdge] = []
        summaries: list[StalePropagationSummary] = []
        version_tokens: list[str] = []
        for prompt_plan in saved_bundle.prompt_plans:
            prompt_plan_version = self.version_service.version_for_prompt_plan(prompt_plan)
            version_tokens.append(prompt_plan_version)
            edge = pending_edges.get(prompt_plan.prompt_plan_id)
            if edge is not None:
                await self.edge_repository.save_dependency_edge(workspace_id, edge.to_dict())
                edges.append(edge)
            summaries.append(
                await self.propagation_service.propagate_upstream_change(
                    UpstreamChangeEvent(
                        workspace_id=workspace_id,
                        project_id=project_id,
                        upstream_type="prompt_plan",
                        upstream_id=prompt_plan.prompt_plan_id,
                        upstream_version=prompt_plan_version,
                        reason_code="prompt_plan_changed",
                    )
                )
            )
        if not summaries:
            raise StaleWriteIntegrationError("prompt plan bundle must include at least one prompt plan")
        return StaleAwareWriteResult(
            saved_payload=saved_bundle.to_dict(),
            version_tokens=tuple(version_tokens),
            propagation_summaries=tuple(summaries),
            dependency_edges=tuple(edges),
        )

    async def _edge_for_prompt_plan(
        self,
        workspace_id: str,
        project_id: str,
        prompt_plan,
    ) -> DependencyEdge | None:
        scene_cast_id = prompt_plan.metadata.get("scene_cast_id")
        asset_bible_id = prompt_plan.metadata.get("asset_bible_id")
        if isinstance(scene_cast_id, str) and scene_cast_id:
            scene_cast_payload = await self.asset_bible_repository.load_scene_cast(workspace_id, scene_cast_id)
            if scene_cast_payload is None:
                raise StaleWriteDependencyNotFoundError("scene cast draft was not found")
            scene_cast = SceneCast.from_dict(scene_cast_payload)
            return DependencyEdge(
                edge_id=f"dep_prompt_plan_{prompt_plan.prompt_plan_id}_scene_cast_{scene_cast.scene_cast_id}",
                workspace_id=workspace_id,
                project_id=project_id,
                upstream_type="scene_cast",
                upstream_id=scene_cast.scene_cast_id,
                upstream_version=self.version_service.version_for_scene_cast(scene_cast),
                downstream_type="prompt_plan",
                downstream_id=prompt_plan.prompt_plan_id,
                relation="prompt_plan.uses_scene_cast",
            )
        if isinstance(asset_bible_id, str) and asset_bible_id:
            asset_bible_payload = await self.asset_bible_repository.load_asset_bible(workspace_id, asset_bible_id)
            if asset_bible_payload is None:
                raise StaleWriteDependencyNotFoundError("asset bible draft was not found")
            asset_bible = AssetBible.from_dict(asset_bible_payload)
            return DependencyEdge(
                edge_id=f"dep_prompt_plan_{prompt_plan.prompt_plan_id}_asset_bible_{asset_bible.asset_bible_id}",
                workspace_id=workspace_id,
                project_id=project_id,
                upstream_type="asset_bible",
                upstream_id=asset_bible.asset_bible_id,
                upstream_version=self.version_service.version_for_asset_bible(asset_bible),
                downstream_type="prompt_plan",
                downstream_id=prompt_plan.prompt_plan_id,
                relation="prompt_plan.references_asset_bible",
            )
        return None

```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_dependency_versions.py tests/test_stale_write_integration.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pixelle_video/services/stale_write_integration.py tests/test_stale_write_integration.py
git commit -m "feat: 接入 PromptPlan stale 写入协调"
git push origin dev
```

## Task 4: Image Artifact Dependency Recording

**Files:**
- Create: `pixelle_video/services/artifact_dependency_integration.py`
- Create: `tests/test_artifact_dependency_integration.py`

- [ ] **Step 1: Add failing artifact dependency test**

Create `tests/test_artifact_dependency_integration.py`:

```python
from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.artifact import ArtifactVersion, ArtifactVersionStatus
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.services.artifact_dependency_integration import ArtifactDependencyWriteService


@dataclass
class FakeDependencyEdgeRepository:
    edges: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges[(workspace_id, edge["edge_id"])] = dict(edge)
        return dict(edge)

    async def list_downstream_edges(self, workspace_id: str, upstream_type: str, upstream_id: str) -> list[dict[str, Any]]:
        return []


def _prompt_plan() -> PromptPlan:
    return PromptPlan(
        prompt_plan_id="prompt_plan_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_1",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
    )


@pytest.mark.asyncio
async def test_record_image_artifact_dependency_writes_prompt_plan_edge_without_storage_path_identity():
    edges = FakeDependencyEdgeRepository()
    service = ArtifactDependencyWriteService(edge_repository=edges)
    prompt_plan = _prompt_plan()
    version = ArtifactVersion(
        version_id="artifact_version_1",
        artifact_id="artifact_frame_0001_image",
        workspace_id="workspace_1",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_1",
        storage_key="artifacts/workspace_1/frame_0001/artifact_version_1.png",
        status=ArtifactVersionStatus.SUCCEEDED,
        provider="comfyui",
    )

    edge = await service.record_image_artifact_dependency(
        workspace_id="workspace_1",
        project_id="project_1",
        artifact_version=version,
        prompt_plan=prompt_plan,
    )

    assert edge.edge_id == "dep_image_artifact_artifact_frame_0001_image_prompt_plan_prompt_plan_1"
    assert edge.upstream_type == "prompt_plan"
    assert edge.upstream_id == "prompt_plan_1"
    assert edge.upstream_version.startswith("prompt_plan_rev_")
    assert edge.downstream_type == "image_artifact"
    assert edge.downstream_id == "artifact_frame_0001_image"
    assert edge.relation == "image_artifact.generated_from_prompt_plan"
    assert "artifacts/" not in str(edge.to_dict())
    assert "storage_key" not in str(edge.to_dict())
```

- [ ] **Step 2: Run artifact test to verify RED**

Run:

```powershell
python -m pytest -q tests/test_artifact_dependency_integration.py
```

Expected: FAIL because `ArtifactDependencyWriteService` does not exist.

- [ ] **Step 3: Implement artifact dependency writer**

Create `pixelle_video/services/artifact_dependency_integration.py`:

```python
from __future__ import annotations

from pixelle_video.models.artifact import ArtifactVersion
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.stale_dependency import DependencyEdge
from pixelle_video.repositories.stale_dependencies import DependencyEdgeRepository
from pixelle_video.services.dependency_versions import DependencyVersionService


class ArtifactDependencyIntegrationError(ValueError):
    pass


class ArtifactDependencyWriteService:
    def __init__(
        self,
        *,
        edge_repository: DependencyEdgeRepository,
        version_service: DependencyVersionService | None = None,
    ) -> None:
        self.edge_repository = edge_repository
        self.version_service = version_service or DependencyVersionService()

    async def record_image_artifact_dependency(
        self,
        *,
        workspace_id: str,
        project_id: str,
        artifact_version: ArtifactVersion,
        prompt_plan: PromptPlan,
    ) -> DependencyEdge:
        if artifact_version.source_prompt_plan_id != prompt_plan.prompt_plan_id:
            raise ArtifactDependencyIntegrationError(
                "artifact version source prompt plan does not match prompt plan"
            )
        edge = DependencyEdge(
            edge_id=(
                f"dep_image_artifact_{artifact_version.artifact_id}_"
                f"prompt_plan_{prompt_plan.prompt_plan_id}"
            ),
            workspace_id=workspace_id,
            project_id=project_id,
            upstream_type="prompt_plan",
            upstream_id=prompt_plan.prompt_plan_id,
            upstream_version=self.version_service.version_for_prompt_plan(prompt_plan),
            downstream_type="image_artifact",
            downstream_id=artifact_version.artifact_id,
            relation="image_artifact.generated_from_prompt_plan",
        )
        await self.edge_repository.save_dependency_edge(workspace_id, edge.to_dict())
        return edge
```

- [ ] **Step 4: Run integration tests**

Run:

```powershell
python -m pytest -q tests/test_dependency_versions.py tests/test_artifact_dependency_integration.py tests/test_stale_dependency_propagation.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pixelle_video/services/artifact_dependency_integration.py tests/test_artifact_dependency_integration.py
git commit -m "feat: 记录 image artifact stale 依赖边"
git push origin dev
```

## Task 5: Storyboard Workbench Artifact Dependency Hook

**Files:**
- Modify: `pixelle_video/services/storyboard_workbench.py`
- Modify: `tests/test_storyboard_frame_regeneration.py`

- [ ] **Step 1: Add failing workbench integration test**

Append to `tests/test_storyboard_frame_regeneration.py`:

```python
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.services.artifact_dependency_integration import ArtifactDependencyWriteService


@dataclass
class RecordingDependencyEdgeRepository:
    edges: list[dict[str, object]] = field(default_factory=list)

    async def save_dependency_edge(self, workspace_id: str, edge: Mapping[str, object]) -> dict[str, object]:
        payload = dict(edge)
        self.edges.append(payload)
        return payload

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, object]]:
        return []


def _prompt_plan() -> PromptPlan:
    return PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
    )


@pytest.mark.asyncio
async def test_frame_image_regeneration_result_records_prompt_plan_dependency_edge(tmp_path):
    generated_file = tmp_path / "generated.png"
    generated_file.write_bytes(b"image")
    artifact_repository = RecordingArtifactRepository(created_versions=[])
    object_store = RecordingObjectStore(uploaded_files=[])
    trace_repository = RecordingTraceRepository(events=[])
    edge_repository = RecordingDependencyEdgeRepository()
    service = StoryboardWorkbenchService(
        artifact_repository=artifact_repository,
        object_store=object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=UnusedPromptPlanRepository(),
        artifact_dependency_service=ArtifactDependencyWriteService(edge_repository=edge_repository),
    )

    result = await service.record_frame_image_regeneration_result(
        workspace_id="workspace_1",
        project_id="project_1",
        task_id="regen-task-1",
        state=_state(),
        artifact_id="artifact_frame_0001_image",
        source_path=generated_file,
        prompt_plan=_prompt_plan(),
        provider="comfyui",
    )

    assert result.artifact_version.artifact_id == "artifact_frame_0001_image"
    assert edge_repository.edges[0]["relation"] == "image_artifact.generated_from_prompt_plan"
    assert edge_repository.edges[0]["upstream_id"] == "prompt_plan_001"
    assert edge_repository.edges[0]["downstream_id"] == "artifact_frame_0001_image"
    assert "storage_key" not in str(edge_repository.edges[0])
```

Also update the existing test imports in `tests/test_storyboard_frame_regeneration.py` from `from dataclasses import dataclass` to `from dataclasses import dataclass, field`.

- [ ] **Step 2: Run workbench test to verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_frame_regeneration.py::test_frame_image_regeneration_result_records_prompt_plan_dependency_edge
```

Expected: FAIL because `StoryboardWorkbenchService.__init__()` does not accept `artifact_dependency_service`.

- [ ] **Step 3: Implement optional artifact dependency hook**

Update `pixelle_video/services/storyboard_workbench.py`:

```python
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.services.artifact_dependency_integration import ArtifactDependencyWriteService
```

Update constructor:

```python
    def __init__(
        self,
        *,
        artifact_repository: ArtifactRepository,
        object_store: ArtifactObjectStore,
        trace_repository: TraceRepository,
        prompt_plan_repository: PromptPlanRepository,
        artifact_dependency_service: ArtifactDependencyWriteService | None = None,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.object_store = object_store
        self.trace_repository = trace_repository
        self.prompt_plan_repository = prompt_plan_repository
        self.artifact_dependency_service = artifact_dependency_service
```

Update `record_frame_image_regeneration_result()` signature:

```python
    async def record_frame_image_regeneration_result(
        self,
        *,
        workspace_id: str,
        task_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        source_path: str | PathLike[str],
        project_id: str | None = None,
        prompt_plan: PromptPlan | None = None,
        provider: str | None = None,
        provider_metadata: Mapping[str, Any] | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> FrameImageRegenerationResult:
```

After `artifact_version = ArtifactVersion.from_dict(stored_version)` add:

```python
        if self.artifact_dependency_service is not None and project_id is not None and prompt_plan is not None:
            await self.artifact_dependency_service.record_image_artifact_dependency(
                workspace_id=workspace_id,
                project_id=project_id,
                artifact_version=artifact_version,
                prompt_plan=prompt_plan,
            )
```

Do not load PromptPlan by path, workflow, provider metadata, or storage key. If the caller does not pass `project_id` and `prompt_plan`, skip edge recording instead of guessing.

- [ ] **Step 4: Run workbench regression tests**

Run:

```powershell
python -m pytest -q tests/test_artifact_dependency_integration.py tests/test_storyboard_frame_regeneration.py tests/test_storyboard_workbench_service.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pixelle_video/services/storyboard_workbench.py tests/test_storyboard_frame_regeneration.py
git commit -m "feat: 接入工作台 image artifact 依赖记录"
git push origin dev
```

## Task 6: AssetBible API Route Integration And Stage 2 Boundary Tests

**Files:**
- Modify: `api/routers/asset_bible.py`
- Modify: `tests/test_asset_bible_api.py`

- [ ] **Step 1: Add failing route tests for stale-aware save wiring**

Modify `tests/test_asset_bible_api.py` fake app setup to accept stale repositories. Define local fakes in that file rather than importing fakes from another test module:

```python
@dataclass
class FakeDependencyEdgeRepository:
    edges: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges[(workspace_id, edge["edge_id"])] = dict(edge)
        return dict(edge)

    async def list_downstream_edges(self, workspace_id: str, upstream_type: str, upstream_id: str) -> list[dict[str, Any]]:
        return [
            edge
            for (stored_workspace_id, _), edge in self.edges.items()
            if stored_workspace_id == workspace_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class FakeStaleMarkRepository:
    marks: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = field(default_factory=dict)

    async def mark_stale(self, workspace_id: str, mark: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        key = (
            workspace_id,
            mark["target_type"],
            mark["target_id"],
            mark["reason_code"],
            mark["upstream_type"],
            mark["upstream_id"],
            mark["upstream_version"],
        )
        if key in self.marks:
            return dict(self.marks[key]), False
        self.marks[key] = dict(mark)
        return dict(mark), True

    async def list_stale_marks(self, workspace_id: str, target_type: str, target_id: str) -> list[dict[str, Any]]:
        return []


def test_asset_bible_api_update_uses_stale_aware_write_service_when_configured():
    repository = FakeAssetBibleRepository()
    edge_repository = FakeDependencyEdgeRepository()
    stale_repository = FakeStaleMarkRepository()
    client = _client(
        repository,
        edge_repository=edge_repository,
        stale_repository=stale_repository,
    )

    response = client.put(
        "/projects/project_1/asset-bible/bible_demo",
        json=_asset_bible_payload(ip_name="Updated IP"),
    )

    assert response.status_code == 200
    assert response.json()["asset_bible"]["asset_bible_id"] == "bible_demo"
    assert repository.saved[-1][1]["asset_bible_id"] == "bible_demo"


def test_scene_cast_api_update_uses_stale_aware_write_service_and_writes_dependency_edge():
    repository = FakeAssetBibleRepository()
    edge_repository = FakeDependencyEdgeRepository()
    stale_repository = FakeStaleMarkRepository()
    client = _client(
        repository,
        edge_repository=edge_repository,
        stale_repository=stale_repository,
    )
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.put(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1",
        json=_scene_cast_payload(continuity_notes=["Updated continuity."]),
    )

    assert response.status_code == 200
    assert any(
        edge["relation"] == "scene_cast.references_asset_bible"
        for edge in edge_repository.edges.values()
    )


def test_projection_preview_does_not_use_stale_write_repositories():
    client, repository, prompt_plan_repository = _client_with_projection_dependencies()
    edge_repository = FakeDependencyEdgeRepository()
    stale_repository = FakeStaleMarkRepository()
    client.app.state.dependency_edge_repository = edge_repository
    client.app.state.stale_mark_repository = stale_repository

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 200
    assert edge_repository.edges == {}
    assert stale_repository.marks == {}
```

Update `_client()` signature:

```python
def _client(
    repository: FakeAssetBibleRepository | None = None,
    *,
    prompt_plan_repository: FakePromptPlanRepository | None = None,
    edge_repository: FakeDependencyEdgeRepository | None = None,
    stale_repository: FakeStaleMarkRepository | None = None,
) -> TestClient:
    from api.routers.asset_bible import router as asset_bible_router

    app = FastAPI()
    if repository is not None:
        app.state.asset_bible_repository = repository
    if prompt_plan_repository is not None:
        app.state.prompt_plan_repository = prompt_plan_repository
    if edge_repository is not None:
        app.state.dependency_edge_repository = edge_repository
    if stale_repository is not None:
        app.state.stale_mark_repository = stale_repository
    app.include_router(asset_bible_router)
    return TestClient(app)
```

- [ ] **Step 2: Run route tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py::test_scene_cast_api_update_uses_stale_aware_write_service_and_writes_dependency_edge tests/test_asset_bible_api.py::test_projection_preview_does_not_use_stale_write_repositories
```

Expected: at least the dependency edge assertion fails because routes still call repository directly.

- [ ] **Step 3: Wire AssetBible routes to stale-aware service**

In `api/routers/asset_bible.py`, add helpers:

```python
from pixelle_video.services.stale_write_integration import (
    StaleAwareAssetBibleWriteService,
    StaleWriteDependencyNotFoundError,
    StaleWriteIntegrationError,
)


def _get_dependency_edge_repository(request: Request):
    return getattr(request.app.state, "dependency_edge_repository", None)


def _get_stale_mark_repository(request: Request):
    return getattr(request.app.state, "stale_mark_repository", None)


def _build_stale_asset_write_service(request: Request) -> StaleAwareAssetBibleWriteService | None:
    edge_repository = _get_dependency_edge_repository(request)
    stale_repository = _get_stale_mark_repository(request)
    if edge_repository is None and stale_repository is None:
        return None
    if edge_repository is None or stale_repository is None:
        raise HTTPException(
            status_code=503,
            detail="stale write repositories are not fully configured",
        )
    return StaleAwareAssetBibleWriteService(
        asset_bible_repository=_get_asset_bible_repository(request),
        edge_repository=edge_repository,
        stale_repository=stale_repository,
    )
```

Update create/update AssetBible and create/update SceneCast:

```python
service = _build_stale_asset_write_service(request)
if service is None:
    saved = await repository.save_asset_bible(payload.workspace_id, asset_bible.to_dict())
else:
    try:
        result = await service.save_asset_bible(payload.workspace_id, asset_bible)
    except StaleWriteIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    saved = result.saved_payload
```

For SceneCast:

```python
service = _build_stale_asset_write_service(request)
if service is None:
    saved = await repository.save_scene_cast(payload.workspace_id, scene_cast.to_dict())
else:
    try:
        result = await service.save_scene_cast(payload.workspace_id, scene_cast)
    except StaleWriteDependencyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StaleWriteIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    saved = result.saved_payload
```

Do not change `preview_prompt_plan_projection()`.

- [ ] **Step 4: Run route and boundary tests**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py tests/test_asset_prompt_plan_composer.py tests/test_prompt_composer_asset_projection.py tests/test_scene_casting_validation.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add api/routers/asset_bible.py tests/test_asset_bible_api.py
git commit -m "feat: 接入 AssetBible API stale 写入服务"
git push origin dev
```

## Final Verification

Run all targeted suites:

```powershell
python -m pytest -q tests/test_dependency_versions.py tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_propagation.py tests/test_stale_write_integration.py tests/test_artifact_dependency_integration.py
```

Expected: all stale domain, repository, propagation, and write integration tests pass.

Run API and Stage 2 regressions:

```powershell
python -m pytest -q tests/test_asset_bible_api.py tests/test_asset_prompt_plan_composer.py tests/test_prompt_composer_asset_projection.py tests/test_scene_casting_validation.py tests/test_stage2_projection_pipeline_ui.py tests/test_storyboard_frame_regeneration.py tests/test_storyboard_workbench_service.py
```

Expected: AssetBible/SceneCast routes pass and Stage 2 projection preview remains preview-only.

Run lint:

```powershell
python -m ruff check pixelle_video/services/dependency_versions.py pixelle_video/services/stale_write_integration.py pixelle_video/services/artifact_dependency_integration.py pixelle_video/services/storyboard_workbench.py pixelle_video/models/stale_dependency.py pixelle_video/repositories/stale_dependencies.py pixelle_video/services/stale_dependency_propagation.py api/routers/asset_bible.py tests/test_dependency_versions.py tests/test_stale_write_integration.py tests/test_artifact_dependency_integration.py tests/test_asset_bible_api.py tests/test_storyboard_frame_regeneration.py
```

Expected: no lint errors.

Run boundary search:

```powershell
rg -n "D:\\\\|://|workflows/|workflow_path|provider_url|save_prompt_plan_bundle|stage2_projection|asset_prompt_plan_composer" pixelle_video/services/dependency_versions.py pixelle_video/services/stale_write_integration.py pixelle_video/services/artifact_dependency_integration.py pixelle_video/services/storyboard_workbench.py pixelle_video/services/stale_dependency_propagation.py api/routers/asset_bible.py tests/test_dependency_versions.py tests/test_stale_write_integration.py tests/test_artifact_dependency_integration.py tests/test_asset_bible_api.py tests/test_storyboard_frame_regeneration.py
```

Expected: production code contains no provider URL, local path, workflow path, Stage 2 persistence, or provider routing coupling. Test hits must be negative fixtures or explicit boundary assertions only.

## Parallelization Guidance

Safe parallel groups:

- Task 1 is a prerequisite for all implementation tasks.
- After Task 1, Task 2 and Task 4 can proceed in parallel because they have disjoint production files:
  - Task 2 owns `pixelle_video/services/stale_write_integration.py` for AssetBible/SceneCast only.
  - Task 4 owns `pixelle_video/services/artifact_dependency_integration.py`.
- Task 3 depends on Task 2 because it extends `stale_write_integration.py` and shared fakes.
- Task 5 depends on Task 4 because it injects `ArtifactDependencyWriteService` into `StoryboardWorkbenchService`.
- Task 6 depends on Task 2 and should run after Task 3 if the same API test file has changed, to avoid merge conflicts.

Recommended execution:

1. Task 1 inline or one worker.
2. Task 2 worker and Task 4 worker in separate worktrees only if available.
3. Task 3 after Task 2 lands.
4. Task 5 after Task 4 lands.
5. Task 6 last.
6. Final verification and review twice before continuing.

## Plan Self-Review

- Spec coverage: Every design component has an implementation task: version tokens, AssetBible/SceneCast writes, PromptPlan writes, artifact dependency edge, real workbench hook, API wiring, Stage 2 boundary tests.
- Placeholder scan: No open-ended placeholder instructions remain; each task has concrete files, tests, commands, and expected results.
- Type consistency: `StaleAwareWriteResult`, `DependencyVersionService`, `StaleAwareAssetBibleWriteService`, `StaleAwarePromptPlanWriteService`, and `ArtifactDependencyWriteService` names are consistent across tasks.
- Scope control: Plan does not persist Stage 2 projection, does not call provider routing, does not add front-end UI, and does not implement video segment/final video real repositories.
