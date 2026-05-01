# Stage 2 PromptPlan Projection Design

## Stage 2 Gate C Closeout

Status: completed for the preview loop. Stage 2 now has a repository-backed `PromptPlanProjectionPreview` path that loads a validated `SceneCast`, applies its asset references to an existing `PromptPlan`, and returns a new projected PromptPlan preview.

This closeout does not change the boundary: the projected PromptPlan is not persisted, stale state is not marked or propagated, Provider routing/projection is not performed, and the preview endpoint is not part of the main generation path.

## Goal

Build a controlled backend loop that projects a validated `SceneCast` onto an existing `PromptPlan` and returns a preview of the projected PromptPlan. This turns Stage 2 AssetBible and SceneCast contracts into a usable workflow entry without connecting them to the main video generation pipeline.

## Scope

This design implements a projection preview path only:

- Load an `AssetBible` through `AssetBibleRepository`.
- Load a `SceneCast` through `AssetBibleRepository`.
- Load PromptPlans for a storyboard through `PromptPlanRepository`.
- Select the PromptPlan for the requested frame.
- Validate that `SceneCast` references belong to the requested `AssetBible`.
- Apply `SceneCast` asset references to the PromptPlan reserved fields.
- Return the projected PromptPlan plus minimal trace metadata.

This design does not implement:

- Main generation pipeline integration.
- Image generation or regeneration.
- PromptPlan persistence or stale mutation.
- Local JSON or JSONL services.
- Reference image, LoRA, image-to-image, provider routing, billing, or permissions.
- Frontend UI.
- Exposing local paths, workflow paths, provider URLs, or raw provider parameters as public contracts.
- Adding `title_style`, `caption_style`, `subtitle_style`, `overlay_style`, or `font*` fields to Stage 2 PromptPlan projection or AssetBible `StyleProfile.metadata`.

## API Contract

Add a draft App API endpoint under the existing AssetBible router:

```text
POST /api/projects/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-projection
```

Request body:

```json
{
  "workspace_id": "workspace_1",
  "storyboard_plan_id": "storyboard_plan_1",
  "frame_id": "frame_0001"
}
```

Response body:

```json
{
  "success": true,
  "message": "Success",
  "projection": {
    "prompt_plan": {
      "prompt_plan_id": "prompt_plan_1",
      "storyboard_plan_id": "storyboard_plan_1",
      "frame_id": "frame_0001",
      "image_prompt_draft_id": "image_prompt_draft_1",
      "prompt_sections": {
        "subject": "Luna studies the compass"
      },
      "final_prompt": "Luna studies the compass in the warm comic lab.",
      "source_trace_id": "trace_prompt_1",
      "character_ids": ["char_luna"],
      "scene_id": "scene_lab",
      "prop_ids": ["prop_compass"],
      "style_id": "style_warm_comic",
      "metadata": {
        "scene_cast_id": "cast_frame_1",
        "asset_bible_id": "bible_demo"
      }
    },
    "source": {
      "asset_bible_id": "bible_demo",
      "scene_cast_id": "cast_frame_1",
      "prompt_plan_id": "prompt_plan_1"
    }
  }
}
```

All route and request IDs must use `validate_public_reference_id`. The endpoint must reject local paths, URLs, and path-like IDs before repository calls where the field is part of the request body.

The `projection.prompt_plan` payload must be the full `PromptPlan.to_dict()` result after projection, not a reduced view. Frontend and future pipeline consumers should not need a second repository call to inspect the prompt text or reserved asset reference fields.

## Backend Service

Create a small service responsible for the projection workflow. The service owns orchestration only; it must not read files, write files, or know about FastAPI.

Proposed service:

```python
@dataclass(frozen=True)
class PromptPlanProjectionSource:
    asset_bible_id: str
    scene_cast_id: str
    prompt_plan_id: str


@dataclass(frozen=True)
class PromptPlanProjectionPreview:
    prompt_plan: PromptPlan
    source: PromptPlanProjectionSource


class AssetPromptPlanComposerService:
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
        ...
```

Dependencies:

- `AssetBibleRepository`
- `PromptPlanRepository`

The service loads the asset bible and scene cast, validates ownership and asset references, loads prompt plans for the storyboard, selects the matching frame, then calls `apply_scene_cast_to_prompt_plan()`.
It returns typed dataclasses, leaving API serialization and HTTP status mapping outside the service.

## Data Flow

```text
API request
  -> validate public IDs
  -> AssetPromptPlanComposerService
  -> AssetBibleRepository.load_asset_bible()
  -> AssetBibleRepository.load_scene_cast()
  -> validate_scene_cast()
  -> PromptPlanRepository.load_prompt_plans_by_storyboard()
  -> select PromptPlan by frame_id
  -> apply_scene_cast_to_prompt_plan()
  -> response projection preview
```

The original PromptPlan object must not be mutated. The projected result is a new `PromptPlan` instance.

## Error Handling

The service should raise typed `ValueError` subclasses with safe public messages so the API can map them deterministically:

- Missing AssetBible: `404`
- Missing SceneCast: `404`
- Missing PromptPlan for storyboard/frame: `404`
- AssetBible/project/workspace mismatch: `502` for repository corruption or wrong loaded data.
- SceneCast validation failure: `422`
- PromptPlan identity mismatch with SceneCast: `422`
- Missing repository dependency: `503`

The API must not expose local paths or raw backend implementation details in responses.

## Persistence Decision

This phase returns projection preview only. It does not call `PromptPlanRepository.save_prompt_plan_bundle()`.

Reason: the current repository contract is bundle-oriented. Persisting one projected frame through a bundle contract would either require reconstructing the whole bundle or inventing a partial update path. That would create technical debt. A future stale/persistence phase should extend the repository contract deliberately if single-frame PromptPlan updates are needed.

## Testing Strategy

Unit tests for the service:

- Returns a projected PromptPlan with `character_ids`, `scene_id`, `prop_ids`, and `style_id` from the SceneCast.
- Does not mutate the original PromptPlan.
- Rejects missing AssetBible.
- Rejects missing SceneCast.
- Rejects unknown SceneCast asset references.
- Rejects missing PromptPlan for the requested frame.
- Rejects mismatched workspace, project, asset bible, storyboard, and frame identities.

API tests:

- Returns projection preview through injected repositories.
- Fails fast when `asset_bible_repository` or `prompt_plan_repository` is not configured.
- Rejects path-like IDs in route and body.
- Maps missing resources to `404`, validation errors to `422`, corrupted repository identity to `502`.
- Does not expose local paths in response.

## Acceptance Criteria

- The endpoint works through repository injection only.
- No local JSON, JSONL, or filesystem service is introduced.
- No main video generation pipeline code is modified.
- No title, subtitle, caption, font, or text rendering style fields enter `StyleProfile`, `SceneCast`, or PromptPlan projection.
- The projection preview can be used by a future frontend without creating fake UI-only state.
- Targeted tests cover projection, non-mutation, missing resources, invalid references, path-like IDs, safe error mapping, and text rendering metadata rejection.
