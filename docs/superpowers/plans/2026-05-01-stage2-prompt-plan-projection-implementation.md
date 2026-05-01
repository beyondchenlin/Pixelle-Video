# Stage 2 PromptPlan Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Stage 2 Gate C Closeout

Status: completed for the preview loop. The implemented scope is the backend/App API `PromptPlanProjectionPreview` path only: it validates repository-backed AssetBible / SceneCast references, selects the requested frame PromptPlan, returns a new projected PromptPlan preview, and leaves the source PromptPlan unchanged.

Closed boundaries remain in force: no projected PromptPlan persistence, no stale marking or dependency propagation, no Provider routing/projection, no image generation, and no main generation path integration. Public contracts must not expose local paths, workflow paths, provider URLs, or raw provider parameters. `title_style`, `caption_style`, `subtitle_style`, `overlay_style`, and `font*` remain outside Stage 2 PromptPlan projection and AssetBible `StyleProfile.metadata`.

This document is retained as implementation history. The unchecked task lists, commit commands, and push commands below are archived implementation instructions from the completed pass; do not execute them as the current active plan. The current follow-up plan is the separate Stage 1B stale dependency propagation plan, and it must not turn this Stage 2 preview into persistence, stale mutation, Provider routing/projection, or main generation integration.

**Goal:** Add a backend-only preview endpoint that projects a validated `SceneCast` onto an existing `PromptPlan` without persisting the projected plan.

**Architecture:** Add a focused orchestration service that depends only on `AssetBibleRepository`, `PromptPlanRepository`, current domain models, `validate_scene_cast()`, and `apply_scene_cast_to_prompt_plan()`. The FastAPI router performs public ID validation, repository injection, HTTP error mapping, and response serialization.

**Tech Stack:** Python dataclasses, FastAPI, Pydantic v2, pytest, existing Pixelle domain models and repository protocols.

---

## File Structure

- Create `pixelle_video/services/asset_prompt_plan_composer.py`: orchestration service, projection dataclasses, and typed service exceptions.
- Create `tests/test_asset_prompt_plan_composer.py`: service-level TDD coverage with in-memory repositories.
- Modify `api/schemas/asset_bible.py`: request and response schemas for projection preview.
- Modify `api/routers/asset_bible.py`: endpoint, prompt plan repository dependency lookup, and service exception to HTTP mapping.
- Modify `tests/test_asset_bible_api.py`: API-level TDD coverage and fake prompt plan repository.

## Task 1: Service Projection Workflow

**Files:**
- Create: `tests/test_asset_prompt_plan_composer.py`
- Create: `pixelle_video/services/asset_prompt_plan_composer.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/test_asset_prompt_plan_composer.py` with this coverage:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.services.asset_prompt_plan_composer import (
    AssetBibleNotFoundError,
    AssetPromptPlanComposerService,
    PromptPlanNotFoundError,
    PromptPlanProjectionValidationError,
    RepositoryIdentityError,
    SceneCastNotFoundError,
)


@dataclass
class FakeAssetBibleRepository:
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def load_asset_bible(self, workspace_id: str, asset_bible_id: str) -> dict[str, Any] | None:
        return self.asset_bibles.get((workspace_id, asset_bible_id))

    async def load_scene_cast(self, workspace_id: str, scene_cast_id: str) -> dict[str, Any] | None:
        return self.scene_casts.get((workspace_id, scene_cast_id))


@dataclass
class FakePromptPlanRepository:
    prompt_plans: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)

    async def load_prompt_plans_by_storyboard(self, workspace_id: str, storyboard_id: str) -> list[dict[str, Any]]:
        return self.prompt_plans.get((workspace_id, storyboard_id), [])


def asset_bible_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "asset_bible_id": "bible_demo",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "character_profiles": [
            {"character_id": "char_luna", "workspace_id": "workspace_1", "project_id": "project_1", "display_name": "Luna"}
        ],
        "scene_assets": [
            {"scene_id": "scene_lab", "workspace_id": "workspace_1", "project_id": "project_1", "display_name": "Sky Lab"}
        ],
        "prop_assets": [
            {"prop_id": "prop_compass", "workspace_id": "workspace_1", "project_id": "project_1", "display_name": "Star Compass"}
        ],
        "style_profiles": [
            {"style_id": "style_warm_comic", "workspace_id": "workspace_1", "project_id": "project_1", "display_name": "Warm Comic", "visual_style": "warm comic"}
        ],
    }
    payload.update(overrides)
    return payload


def scene_cast_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "scene_cast_id": "cast_frame_1",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "asset_bible_id": "bible_demo",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
    }
    payload.update(overrides)
    return payload


def prompt_plan_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "prompt_plan_id": "prompt_plan_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_1",
        "prompt_sections": {"visual_goal": "Show Luna in the lab."},
        "final_prompt": "Show Luna in the lab.",
        "source_trace_id": "trace_1",
        "metadata": {"source": "stage1a"},
    }
    payload.update(overrides)
    return payload


def service_with_defaults() -> tuple[AssetPromptPlanComposerService, FakeAssetBibleRepository, FakePromptPlanRepository]:
    asset_repository = FakeAssetBibleRepository()
    prompt_repository = FakePromptPlanRepository()
    asset_repository.asset_bibles[("workspace_1", "bible_demo")] = asset_bible_payload()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload()
    prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [prompt_plan_payload()]
    return (
        AssetPromptPlanComposerService(
            asset_bible_repository=asset_repository,
            prompt_plan_repository=prompt_repository,
        ),
        asset_repository,
        prompt_repository,
    )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_projects_scene_cast_without_mutating_source_plan():
    service, _, prompt_repository = service_with_defaults()
    source_plan = prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")][0]

    preview = await service.preview_prompt_plan_projection(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
    )

    assert preview.prompt_plan.prompt_plan_id == "prompt_plan_1"
    assert preview.prompt_plan.character_ids == ("char_luna",)
    assert preview.prompt_plan.scene_id == "scene_lab"
    assert preview.prompt_plan.prop_ids == ("prop_compass",)
    assert preview.prompt_plan.style_id == "style_warm_comic"
    assert preview.prompt_plan.metadata["scene_cast_id"] == "cast_frame_1"
    assert preview.source.asset_bible_id == "bible_demo"
    assert preview.source.scene_cast_id == "cast_frame_1"
    assert preview.source.prompt_plan_id == "prompt_plan_1"
    assert "character_ids" not in source_plan
    assert source_plan["metadata"] == {"source": "stage1a"}


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_missing_asset_bible():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.asset_bibles.clear()

    with pytest.raises(AssetBibleNotFoundError):
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_missing_scene_cast():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.scene_casts.clear()

    with pytest.raises(SceneCastNotFoundError):
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_unknown_scene_cast_asset_reference():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload(character_ids=["char_missing"])

    with pytest.raises(PromptPlanProjectionValidationError) as exc_info:
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "char_missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_missing_prompt_plan_for_frame():
    service, _, prompt_repository = service_with_defaults()
    prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [prompt_plan_payload(frame_id="frame_0002")]

    with pytest.raises(PromptPlanNotFoundError):
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_repository_identity_mismatch():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.asset_bibles[("workspace_1", "bible_demo")] = asset_bible_payload(project_id="other_project")

    with pytest.raises(RepositoryIdentityError) as exc_info:
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "project" in str(exc_info.value)


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_scene_cast_frame_mismatch():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload(frame_id="frame_0002")

    with pytest.raises(PromptPlanProjectionValidationError) as exc_info:
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "frame_id" in str(exc_info.value)
```

- [ ] **Step 2: Run service tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_composer.py
```

Expected: FAIL because `pixelle_video.services.asset_prompt_plan_composer` does not exist.

- [ ] **Step 3: Implement the service**

Create `pixelle_video/services/asset_prompt_plan_composer.py` with these elements:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.repositories.assets import AssetBibleRepository
from pixelle_video.repositories.prompt_plans import PromptPlanRepository
from pixelle_video.services.prompt_composer import apply_scene_cast_to_prompt_plan
from pixelle_video.services.scene_casting import SceneCastValidationError, validate_scene_cast


class PromptPlanProjectionError(ValueError):
    """Base class for safe public projection errors."""


class ProjectionDependencyError(PromptPlanProjectionError):
    pass


class AssetBibleNotFoundError(PromptPlanProjectionError):
    pass


class SceneCastNotFoundError(PromptPlanProjectionError):
    pass


class PromptPlanNotFoundError(PromptPlanProjectionError):
    pass


class RepositoryIdentityError(PromptPlanProjectionError):
    pass


class PromptPlanProjectionValidationError(PromptPlanProjectionError):
    pass


@dataclass(frozen=True)
class PromptPlanProjectionSource:
    asset_bible_id: str
    scene_cast_id: str
    prompt_plan_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "asset_bible_id": self.asset_bible_id,
            "scene_cast_id": self.scene_cast_id,
            "prompt_plan_id": self.prompt_plan_id,
        }


@dataclass(frozen=True)
class PromptPlanProjectionPreview:
    prompt_plan: PromptPlan
    source: PromptPlanProjectionSource

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan": self.prompt_plan.to_dict(),
            "source": self.source.to_dict(),
        }


class AssetPromptPlanComposerService:
    def __init__(
        self,
        *,
        asset_bible_repository: AssetBibleRepository | None,
        prompt_plan_repository: PromptPlanRepository | None,
    ) -> None:
        if asset_bible_repository is None:
            raise ProjectionDependencyError("asset bible repository is not configured")
        if prompt_plan_repository is None:
            raise ProjectionDependencyError("prompt plan repository is not configured")
        self.asset_bible_repository = asset_bible_repository
        self.prompt_plan_repository = prompt_plan_repository

    async def preview_prompt_plan_projection(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
    ) -> PromptPlanProjectionPreview:
        asset_bible = await self._load_asset_bible(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        scene_cast = await self._load_scene_cast(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
        )
        try:
            validate_scene_cast(scene_cast, asset_bible)
        except SceneCastValidationError as exc:
            raise PromptPlanProjectionValidationError(str(exc)) from exc

        prompt_plan = await self._load_prompt_plan(
            workspace_id=workspace_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
        )
        try:
            projected = apply_scene_cast_to_prompt_plan(prompt_plan, scene_cast)
        except ValueError as exc:
            raise PromptPlanProjectionValidationError(str(exc)) from exc
        return PromptPlanProjectionPreview(
            prompt_plan=projected,
            source=PromptPlanProjectionSource(
                asset_bible_id=asset_bible.asset_bible_id,
                scene_cast_id=scene_cast.scene_cast_id,
                prompt_plan_id=projected.prompt_plan_id,
            ),
        )
```

The implementation must include private loaders that parse dictionaries into domain models, check requested identity fields, and raise the typed errors named above with short messages.

- [ ] **Step 4: Run service tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_composer.py
```

Expected: all tests in `tests/test_asset_prompt_plan_composer.py` pass.

- [ ] **Step 5: Commit service task**

Run:

```powershell
git add pixelle_video/services/asset_prompt_plan_composer.py tests/test_asset_prompt_plan_composer.py
git commit -m "feat: 增加场景出场提示词计划投影服务"
git push
```

## Task 2: API Projection Preview Endpoint

**Files:**
- Modify: `tests/test_asset_bible_api.py`
- Modify: `api/schemas/asset_bible.py`
- Modify: `api/routers/asset_bible.py`

- [ ] **Step 1: Write failing API tests**

Extend `tests/test_asset_bible_api.py`:

```python
@dataclass
class FakePromptPlanRepository:
    prompt_plans: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    load_calls: list[tuple[str, str]] = field(default_factory=list)

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, Any]]:
        self.load_calls.append((workspace_id, storyboard_id))
        return self.prompt_plans.get((workspace_id, storyboard_id), [])


def _client(
    repository: FakeAssetBibleRepository | None = None,
    *,
    prompt_plan_repository: FakePromptPlanRepository | None = None,
) -> TestClient:
    from api.routers.asset_bible import router as asset_bible_router

    app = FastAPI()
    if repository is not None:
        app.state.asset_bible_repository = repository
    if prompt_plan_repository is not None:
        app.state.prompt_plan_repository = prompt_plan_repository
    app.include_router(asset_bible_router)
    return TestClient(app)


def _prompt_plan_payload(**overrides) -> dict[str, Any]:
    payload = {
        "prompt_plan_id": "prompt_plan_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_1",
        "prompt_sections": {"visual_goal": "Show Luna in the lab."},
        "final_prompt": "Show Luna in the lab.",
        "source_trace_id": "trace_1",
        "metadata": {"source": "stage1a"},
    }
    payload.update(overrides)
    return payload
```

Add tests that create an asset bible and scene cast, then call:

```python
response = client.post(
    "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
    json={
        "workspace_id": "workspace_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
    },
)
```

Assertions:

```python
assert response.status_code == 200
body = response.json()
assert body["success"] is True
assert body["projection"]["prompt_plan"]["prompt_plan_id"] == "prompt_plan_1"
assert body["projection"]["prompt_plan"]["final_prompt"] == "Show Luna in the lab."
assert body["projection"]["prompt_plan"]["character_ids"] == ["char_luna"]
assert body["projection"]["prompt_plan"]["scene_id"] == "scene_lab"
assert body["projection"]["prompt_plan"]["prop_ids"] == ["prop_compass"]
assert body["projection"]["prompt_plan"]["style_id"] == "style_warm_comic"
assert body["projection"]["source"] == {
    "asset_bible_id": "bible_demo",
    "scene_cast_id": "cast_frame_1",
    "prompt_plan_id": "prompt_plan_1",
}
assert "C:\\" not in str(body)
assert "local_path" not in str(body)
```

Add separate tests for:

```python
assert missing prompt plan repository returns 503
assert path-like request body IDs return 422 before prompt repository load
assert missing prompt plan for frame returns 404
assert unknown scene cast asset reference returns 422
assert corrupted asset bible project identity returns 502
```

- [ ] **Step 2: Run API tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py
```

Expected: FAIL because the endpoint and schemas are not implemented.

- [ ] **Step 3: Implement schemas**

Add these classes to `api/schemas/asset_bible.py`:

```python
class PromptPlanProjectionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    storyboard_plan_id: str
    frame_id: str

    @field_validator("workspace_id", "storyboard_plan_id", "frame_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class PromptPlanProjectionSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_bible_id: str
    scene_cast_id: str
    prompt_plan_id: str


class PromptPlanProjectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_plan: dict[str, Any]
    source: PromptPlanProjectionSourceResponse


class PromptPlanProjectionPreviewResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    projection: PromptPlanProjectionPayload
```

Export the four schema classes through `__all__`.

- [ ] **Step 4: Implement endpoint**

Update `api/routers/asset_bible.py`:

```python
from pixelle_video.services.asset_prompt_plan_composer import (
    AssetBibleNotFoundError,
    AssetPromptPlanComposerService,
    ProjectionDependencyError,
    PromptPlanNotFoundError,
    PromptPlanProjectionValidationError,
    RepositoryIdentityError,
    SceneCastNotFoundError,
)
```

Add `PromptPlanProjectionPreviewRequest` and `PromptPlanProjectionPreviewResponse` to schema imports.

Add the endpoint:

```python
@router.post(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-projection",
    response_model=PromptPlanProjectionPreviewResponse,
)
async def preview_prompt_plan_projection(
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    payload: PromptPlanProjectionPreviewRequest,
    request: Request,
) -> PromptPlanProjectionPreviewResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    scene_cast_id = _validate_public_id("scene_cast_id", scene_cast_id)
    service = AssetPromptPlanComposerService(
        asset_bible_repository=_get_asset_bible_repository(request),
        prompt_plan_repository=_get_prompt_plan_repository(request),
    )
    try:
        preview = await service.preview_prompt_plan_projection(
            workspace_id=payload.workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=payload.storyboard_plan_id,
            frame_id=payload.frame_id,
        )
    except (AssetBibleNotFoundError, SceneCastNotFoundError, PromptPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PromptPlanProjectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryIdentityError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProjectionDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PromptPlanProjectionPreviewResponse(projection=preview.to_dict())
```

Add dependency lookup:

```python
def _get_prompt_plan_repository(request: Request):
    repository = getattr(request.app.state, "prompt_plan_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="prompt plan repository is not configured",
        )
    return repository
```

- [ ] **Step 5: Run API tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py
```

Expected: all API tests pass.

- [ ] **Step 6: Commit API task**

Run:

```powershell
git add api/schemas/asset_bible.py api/routers/asset_bible.py tests/test_asset_bible_api.py
git commit -m "feat: 增加场景出场提示词计划投影接口"
git push
```

## Task 3: Verification And Review

**Files:**
- Verify: full touched-file test set and repository test suite

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py tests/test_prompt_composer_asset_projection.py tests/test_scene_casting_validation.py
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run lint on touched Python files**

Run:

```powershell
python -m ruff check pixelle_video/services/asset_prompt_plan_composer.py api/schemas/asset_bible.py api/routers/asset_bible.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py
```

Expected: no lint errors.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: First self-review pass**

Run:

```powershell
git diff origin/dev...HEAD -- pixelle_video/services/asset_prompt_plan_composer.py api/schemas/asset_bible.py api/routers/asset_bible.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py docs/superpowers/specs/2026-05-01-stage2-prompt-plan-projection-design.md docs/superpowers/plans/2026-05-01-stage2-prompt-plan-projection-implementation.md
```

Review for:

```text
No main pipeline integration.
No persistence of projected PromptPlan.
No local JSON, JSONL, or filesystem service.
No text rendering style fields added to asset style models.
Service has no FastAPI dependency.
API does not expose local paths.
Errors map to 404, 422, 502, and 503 as designed.
```

- [ ] **Step 5: Second self-review pass**

Run:

```powershell
rg -n "save_prompt_plan_bundle|mark_prompt_plan_stale|local_path|C:\\\\|font_|caption_style|title_style|overlay_style" pixelle_video/services/asset_prompt_plan_composer.py api/schemas/asset_bible.py api/routers/asset_bible.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py docs/superpowers/specs/2026-05-01-stage2-prompt-plan-projection-design.md docs/superpowers/plans/2026-05-01-stage2-prompt-plan-projection-implementation.md
```

Expected: no production code violations. Test assertions may contain blocked strings only when verifying responses do not expose them.

- [ ] **Step 6: Commit plan if it is still uncommitted**

Run:

```powershell
git status --short
git add docs/superpowers/plans/2026-05-01-stage2-prompt-plan-projection-implementation.md
git commit -m "docs: 规划场景出场提示词计划投影实现"
git push
```

Only run the commit if the plan file was not already committed before implementation.

## Plan Self-Review

- Spec coverage: service orchestration, API endpoint, validation, error mapping, non-persistence, no main pipeline integration, and full PromptPlan response are covered.
- Type consistency: service returns `PromptPlanProjectionPreview`, API serializes `preview.to_dict()`, schemas model `projection.prompt_plan` as a full dictionary and `projection.source` as typed IDs.
- Scope control: implementation is backend-only and does not alter generation pipeline, repository contracts, text rendering styles, or frontend state.
- Gate C closeout: preview loop is complete, while persistence, stale propagation, Provider routing/projection, public raw paths/URLs, and text-rendering style metadata remain explicitly out of scope.
