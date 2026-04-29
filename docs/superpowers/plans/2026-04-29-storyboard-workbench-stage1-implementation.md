# Storyboard Workbench Stage 1B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 1B Pixelle AI short drama/comic storyboard image workbench slice: consume Stage 1A PromptPlan outputs, then add Artifact/ArtifactVersion, GenerationTrace, image candidate selection, image regeneration, lock/stale metadata, and raw-parameter deprecation markers without introducing FlowGram or a full Workflow Engine.

**Architecture:** Keep the existing `StandardPipeline`, `StoryboardPlan`, `ImagePromptComposer`, and video APIs working. Add focused domain contracts and local JSON services behind interfaces so Stage 1B can run on the current filesystem output layout while remaining replaceable by PostgreSQL/object storage later. Use existing `api.tasks` embedded execution for frame image regeneration, but only add light task types and no full DAG scheduling.

**Tech Stack:** Python dataclasses, Pydantic API schemas, FastAPI routers, local JSON/JSONL persistence, pytest, existing Pixelle `TaskManager`, existing ComfyUI/media service through `pixelle_video` core.

---

## Planning Authority

This plan is a Stage 1B implementation plan under the full Pixelle AI short drama/comic planning hierarchy. It must be executed only inside the boundaries defined by these documents:

- `docs/pixelle_video_full_planning_md/MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`
- `docs/pixelle_video_full_planning_md/12A_TEXT_IMAGE_PROMPT_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/13_STORYBOARD_WORKBENCH_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/14_ARTIFACT_TRACE_REGENERATION_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md`

This plan does not replace the master plan or the remaining capability subplans. It is the Stage 1B workbench slice and assumes Stage 1A owns the first implementation pass for text, storyboard planning, image prompt generation, and PromptPlan creation.

Stage 1A ownership override:

```text
Task 3 and Task 7 are historical bootstrap tasks from the original Stage 1 plan.
After Stage 1A is implemented, do not redefine PromptPlan or PromptPlanBuilder in Stage 1B.
Instead, use Task 3 and Task 7 as compatibility checks against the Stage 1A contracts.
```

## Skill-Gated Execution Rules

Use the documents above for product and architecture decisions, and use Superpowers skills for execution discipline.

Required execution flow:

```text
1. Review this plan with superpowers:executing-plans or superpowers:subagent-driven-development.
2. Before production code for each task, use superpowers:test-driven-development.
3. For every behavior change, write the failing test first and verify the expected failure.
4. Implement the minimum code required for the task.
5. Run the task-specific verification command in the task.
6. Commit each task atomically.
7. Before claiming the stage complete, use superpowers:verification-before-completion and run the full Stage 1B verification checklist.
```

Repository override:

```text
AGENTS.md forbids git worktree use in this repository.
If a Superpowers skill recommends a worktree, do not create one here.
Execute in the current workspace with narrow staging and atomic commits.
```

Stop conditions:

- A task references a file, model, API, or service that no longer exists.
- A test cannot be made to fail for the expected reason.
- A task would introduce FlowGram, full Workflow Engine, SaaS billing, ProviderCapability matrix, Quality Evaluation, or video segment generation into Stage 1B.
- The working tree contains unrelated changes that would be mixed into the task commit.

## Stage 1B Alignment Matrix

| Requirement source | Stage 1B coverage |
| --- | --- |
| `12A_TEXT_IMAGE_PROMPT_STAGE1A_SUBPLAN.md` | Stage 1A owns ScriptDraft, StoryboardPlan, image prompts, and initial PromptPlan generation. This plan consumes and extends those outputs instead of redefining them. |
| `13_STORYBOARD_WORKBENCH_SUBPLAN.md` | Tasks 4, 6, 8, and 9 implement workbench metadata, candidate listing, image selection, lock/stale behavior, and frame regeneration. |
| `14_ARTIFACT_TRACE_REGENERATION_SUBPLAN.md` | Tasks 1, 2, 5, 6, and 9 implement Artifact/ArtifactVersion, trace events, local services, image regeneration, and Trace linkage. |
| `15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md` | Tasks 3 and 7 implement PromptPlan with reserved SceneCast fields and PromptPlan construction without full AssetBible/SceneCast implementation. |
| `MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md` | Scope exclusions below keep Workflow, Worker, Provider, FlowGram, SaaS, video, and Quality/Admin work out of Stage 1. |

## Scope

This plan implements only Stage 1B from the accepted v2 review and updated master roadmap:

- `StoryboardPanel`-compatible metadata on current `StoryboardFrame`.
- `PromptPlan` compatibility with Stage 1A outputs and reserved `style_id`, `character_ids`, `scene_id`, and `prop_ids`.
- `Artifact` and `ArtifactVersion` as separate concepts.
- Local JSON artifact service and local JSONL trace service.
- Frame image candidate selection.
- Frame image regeneration through existing task infrastructure.
- Frame lock and stale dependency metadata.
- Raw generation parameter deprecation markers.

This plan intentionally does not implement:

- FlowGram Adapter.
- User-defined DAG workflows.
- Full `WorkflowRun` / `NodeRun`.
- SaaS billing, workspace policy, API keys, or public API hard rejection of raw fields.
- Provider routing matrix.
- Quality scoring.
- Video segment regeneration.
- ScriptDraft generation.
- Initial StoryboardPlan generation.
- Initial image prompt generation.

## Existing Code Anchors

- `pixelle_video/models/storyboard_plan.py` already owns stable `plan_id`, `frame_id`, `source_digest`, source spans, and frame validation.
- `pixelle_video/models/storyboard.py` contains the current `StoryboardFrame` used by rendering and video generation.
- `pixelle_video/services/persistence.py` serializes `Storyboard` and `StoryboardFrame` to `output/{task_id}/storyboard.json`.
- `pixelle_video/services/image_prompt_composer.py` converts `StoryboardPlan` into prompt contexts and returns `StyledImagePromptBatch`.
- `pixelle_video/services/frame_processor.py` can generate media for a single `StoryboardFrame` through `core.media`.
- `api/tasks` already provides task status, leases, task store, and embedded execution.
- `api/app.py` registers routers under `api_config.api_prefix`.

## File Structure

- Create `pixelle_video/models/artifact.py`: durable artifact and artifact-version contracts.
- Create `pixelle_video/models/generation_event.py`: trace event contract.
- Create `pixelle_video/models/prompt_plan.py`: prompt planning contract and projection contract.
- Create `pixelle_video/models/storyboard_workbench.py`: lock policy, stale flags, and stale propagation helpers.
- Modify `pixelle_video/models/storyboard.py`: add optional workbench fields to `StoryboardFrame`.
- Modify `pixelle_video/services/persistence.py`: persist and restore new `StoryboardFrame` fields.
- Create `pixelle_video/services/artifact_service.py`: local JSON artifact service.
- Create `pixelle_video/services/generation_trace.py`: local JSONL generation trace service.
- Create `pixelle_video/services/prompt_plan_service.py`: build `PromptPlan` objects from `StoryboardPlan` and generated prompts.
- Create `pixelle_video/services/storyboard_workbench.py`: selection and frame-regeneration orchestration.
- Modify `api/tasks/models.py`: add `FRAME_IMAGE_REGENERATION`.
- Modify `api/tasks/__init__.py`: export the expanded task type automatically through existing import.
- Create `api/schemas/storyboard_workbench.py`: request/response schemas for workbench endpoints.
- Create `api/routers/storyboard_workbench.py`: artifact listing, image selection, and image regeneration endpoints.
- Modify `api/app.py`: include the new router.
- Modify `api/schemas/video.py`: mark raw generation fields deprecated for App API.
- Add tests:
  - `tests/test_artifact_models.py`
  - `tests/test_generation_trace_service.py`
  - `tests/test_prompt_plan_model.py`
  - `tests/test_storyboard_workbench_metadata.py`
  - `tests/test_artifact_service.py`
  - `tests/test_storyboard_workbench_service.py`
  - `tests/test_prompt_plan_service.py`
  - `tests/test_storyboard_workbench_api.py`
  - `tests/test_raw_generation_parameter_policy.py`

---

### Task 1: Artifact Contract Models

**Files:**
- Create: `pixelle_video/models/artifact.py`
- Test: `tests/test_artifact_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_artifact_models.py
from pixelle_video.models.artifact import (
    Artifact,
    ArtifactType,
    ArtifactVersion,
    ArtifactVersionStatus,
)


def test_artifact_and_versions_are_separate_logical_objects():
    artifact = Artifact.create(
        project_id="project-1",
        artifact_type=ArtifactType.IMAGE,
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    version = ArtifactVersion.create(
        artifact_id=artifact.artifact_id,
        version=1,
        status=ArtifactVersionStatus.CANDIDATE,
        object_key="task-1/artifacts/images/frame_0001_v1.png",
        provider_id="comfyui",
        model_id="z-image",
        prompt="cinematic frame",
        seed=123,
    )

    selected = artifact.select_version(version.artifact_version_id)

    assert artifact.current_selected_version_id is None
    assert selected.current_selected_version_id == version.artifact_version_id
    assert artifact.artifact_id.startswith("artifact_")
    assert version.artifact_version_id.startswith(f"{artifact.artifact_id}_v0001")
    assert version.status == ArtifactVersionStatus.CANDIDATE


def test_artifact_round_trip_serialization_preserves_metadata():
    artifact = Artifact.create(
        project_id="project-1",
        artifact_type="image",
        logical_key="frame_0001_image",
        frame_id="frame_0001",
        metadata={"storyboard_id": "storyboard-1"},
    )
    version = ArtifactVersion.create(
        artifact_id=artifact.artifact_id,
        version=2,
        status="selected",
        payload={"width": 1024, "height": 1024},
        metadata={"provider_latency_ms": 1000},
    )

    restored_artifact = Artifact.from_dict(artifact.to_dict())
    restored_version = ArtifactVersion.from_dict(version.to_dict())

    assert restored_artifact == artifact
    assert restored_version == version
    assert restored_artifact.metadata["storyboard_id"] == "storyboard-1"
    assert restored_version.payload["width"] == 1024
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_artifact_models.py -v`

Expected: fail with `ModuleNotFoundError: No module named 'pixelle_video.models.artifact'`.

- [ ] **Step 3: Create the artifact models**

```python
# pixelle_video/models/artifact.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ArtifactType(str, Enum):
    SOURCE_DOCUMENT = "source_document"
    SCRIPT_DRAFT = "script_draft"
    ASSET_BIBLE = "asset_bible"
    STORYBOARD = "storyboard"
    STORYBOARD_PANEL = "storyboard_panel"
    PROMPT_PLAN = "prompt_plan"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO_SEGMENT = "video_segment"
    FINAL_VIDEO = "final_video"
    TRACE = "trace"


class ArtifactVersionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANDIDATE = "candidate"
    SELECTED = "selected"
    REJECTED = "rejected"
    FAILED = "failed"


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    project_id: str
    artifact_type: ArtifactType
    logical_key: str
    frame_id: str | None = None
    current_selected_version_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_iso_now)
    updated_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        artifact_type: ArtifactType | str,
        logical_key: str,
        frame_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "Artifact":
        artifact_type_value = ArtifactType(artifact_type)
        artifact_id = _stable_id("artifact", project_id, artifact_type_value.value, logical_key, frame_id or "")
        now = utc_iso_now()
        return cls(
            artifact_id=artifact_id,
            project_id=project_id,
            artifact_type=artifact_type_value,
            logical_key=logical_key,
            frame_id=frame_id,
            metadata=_json_copy(metadata or {}),
            created_at=now,
            updated_at=now,
        )

    def select_version(self, artifact_version_id: str) -> "Artifact":
        return replace(
            self,
            current_selected_version_id=artifact_version_id,
            updated_at=utc_iso_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "project_id": self.project_id,
            "artifact_type": self.artifact_type.value,
            "logical_key": self.logical_key,
            "frame_id": self.frame_id,
            "current_selected_version_id": self.current_selected_version_id,
            "metadata": _json_copy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Artifact":
        return cls(
            artifact_id=str(payload["artifact_id"]),
            project_id=str(payload["project_id"]),
            artifact_type=ArtifactType(payload["artifact_type"]),
            logical_key=str(payload["logical_key"]),
            frame_id=payload.get("frame_id"),
            current_selected_version_id=payload.get("current_selected_version_id"),
            metadata=_json_copy(payload.get("metadata") or {}),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )


@dataclass(frozen=True)
class ArtifactVersion:
    artifact_version_id: str
    artifact_id: str
    version: int
    status: ArtifactVersionStatus
    object_key: str | None = None
    url: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    prompt: str | None = None
    seed: int | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        version: int,
        status: ArtifactVersionStatus | str,
        object_key: str | None = None,
        url: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        prompt: str | None = None,
        seed: int | None = None,
        payload: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ArtifactVersion":
        if version < 1:
            raise ValueError("version must be >= 1")
        return cls(
            artifact_version_id=f"{artifact_id}_v{version:04d}",
            artifact_id=artifact_id,
            version=version,
            status=ArtifactVersionStatus(status),
            object_key=object_key,
            url=url,
            provider_id=provider_id,
            model_id=model_id,
            prompt=prompt,
            seed=seed,
            payload=_json_copy(payload) if payload is not None else None,
            metadata=_json_copy(metadata or {}),
        )

    def with_status(self, status: ArtifactVersionStatus | str) -> "ArtifactVersion":
        return replace(self, status=ArtifactVersionStatus(status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_version_id": self.artifact_version_id,
            "artifact_id": self.artifact_id,
            "version": self.version,
            "status": self.status.value,
            "object_key": self.object_key,
            "url": self.url,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "prompt": self.prompt,
            "seed": self.seed,
            "payload": _json_copy(self.payload) if self.payload is not None else None,
            "metadata": _json_copy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactVersion":
        return cls(
            artifact_version_id=str(payload["artifact_version_id"]),
            artifact_id=str(payload["artifact_id"]),
            version=int(payload["version"]),
            status=ArtifactVersionStatus(payload["status"]),
            object_key=payload.get("object_key"),
            url=payload.get("url"),
            provider_id=payload.get("provider_id"),
            model_id=payload.get("model_id"),
            prompt=payload.get("prompt"),
            seed=payload.get("seed"),
            payload=_json_copy(payload.get("payload")) if payload.get("payload") is not None else None,
            metadata=_json_copy(payload.get("metadata") or {}),
            created_at=str(payload["created_at"]),
        )


__all__ = [
    "Artifact",
    "ArtifactType",
    "ArtifactVersion",
    "ArtifactVersionStatus",
    "utc_iso_now",
]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_artifact_models.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_artifact_models.py pixelle_video/models/artifact.py
git commit -m "feat: 新增分镜工作台产物合同"
```

---

### Task 2: Generation Trace Model And Local JSONL Service

**Files:**
- Create: `pixelle_video/models/generation_event.py`
- Create: `pixelle_video/services/generation_trace.py`
- Test: `tests/test_generation_trace_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_generation_trace_service.py
import json

import pytest

from pixelle_video.models.generation_event import GenerationEvent, GenerationEventLevel
from pixelle_video.services.generation_trace import LocalJsonGenerationTraceService


@pytest.mark.asyncio
async def test_trace_service_appends_and_loads_events(tmp_path):
    service = LocalJsonGenerationTraceService(output_dir=tmp_path)

    await service.record_event(
        GenerationEvent.create(
            task_id="task-1",
            stage="image.regenerate",
            event_type="provider_request",
            level=GenerationEventLevel.INFO,
            frame_id="frame_0001",
            message="request sent",
            payload={"provider_id": "comfyui"},
        )
    )
    await service.record_event(
        GenerationEvent.create(
            task_id="task-1",
            stage="image.regenerate",
            event_type="artifact_created",
            frame_id="frame_0001",
            message="candidate created",
            payload={"artifact_version_id": "artifact_1_v0001"},
        )
    )

    events = await service.load_events("task-1")

    assert [event.event_type for event in events] == ["provider_request", "artifact_created"]
    assert events[0].payload["provider_id"] == "comfyui"
    raw_lines = (tmp_path / "task-1" / "trace" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(raw_lines[1])["message"] == "candidate created"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_generation_trace_service.py -v`

Expected: fail with missing `generation_event` or `generation_trace` modules.

- [ ] **Step 3: Add the event model**

```python
# pixelle_video/models/generation_event.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from pixelle_video.models.artifact import utc_iso_now


class GenerationEventLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value


@dataclass(frozen=True)
class GenerationEvent:
    event_id: str
    task_id: str
    stage: str
    event_type: str
    level: GenerationEventLevel = GenerationEventLevel.INFO
    frame_id: str | None = None
    artifact_id: str | None = None
    artifact_version_id: str | None = None
    provider_id: str | None = None
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        stage: str,
        event_type: str,
        level: GenerationEventLevel | str = GenerationEventLevel.INFO,
        frame_id: str | None = None,
        artifact_id: str | None = None,
        artifact_version_id: str | None = None,
        provider_id: str | None = None,
        message: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> "GenerationEvent":
        return cls(
            event_id=f"evt_{uuid.uuid4().hex}",
            task_id=task_id,
            stage=stage,
            event_type=event_type,
            level=GenerationEventLevel(level),
            frame_id=frame_id,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            provider_id=provider_id,
            message=message,
            payload=_json_copy(payload or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "stage": self.stage,
            "event_type": self.event_type,
            "level": self.level.value,
            "frame_id": self.frame_id,
            "artifact_id": self.artifact_id,
            "artifact_version_id": self.artifact_version_id,
            "provider_id": self.provider_id,
            "message": self.message,
            "payload": _json_copy(self.payload),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GenerationEvent":
        return cls(
            event_id=str(payload["event_id"]),
            task_id=str(payload["task_id"]),
            stage=str(payload["stage"]),
            event_type=str(payload["event_type"]),
            level=GenerationEventLevel(payload.get("level", "info")),
            frame_id=payload.get("frame_id"),
            artifact_id=payload.get("artifact_id"),
            artifact_version_id=payload.get("artifact_version_id"),
            provider_id=payload.get("provider_id"),
            message=str(payload.get("message") or ""),
            payload=_json_copy(payload.get("payload") or {}),
            created_at=str(payload["created_at"]),
        )


__all__ = ["GenerationEvent", "GenerationEventLevel"]
```

- [ ] **Step 4: Add the local JSONL trace service**

```python
# pixelle_video/services/generation_trace.py
from __future__ import annotations

import json
from pathlib import Path

from pixelle_video.models.generation_event import GenerationEvent


class LocalJsonGenerationTraceService:
    def __init__(self, output_dir: str | Path = "output") -> None:
        self.output_dir = Path(output_dir)

    def get_trace_dir(self, task_id: str) -> Path:
        return self.output_dir / task_id / "trace"

    def get_events_path(self, task_id: str) -> Path:
        return self.get_trace_dir(task_id) / "events.jsonl"

    async def record_event(self, event: GenerationEvent) -> None:
        events_path = self.get_events_path(event.task_id)
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    async def load_events(self, task_id: str) -> list[GenerationEvent]:
        events_path = self.get_events_path(task_id)
        if not events_path.exists():
            return []
        events: list[GenerationEvent] = []
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(GenerationEvent.from_dict(json.loads(line)))
        return events


__all__ = ["LocalJsonGenerationTraceService"]
```

- [ ] **Step 5: Run the tests to verify pass**

Run: `pytest tests/test_generation_trace_service.py -v`

Expected: one test passes.

- [ ] **Step 6: Commit**

```bash
git add tests/test_generation_trace_service.py pixelle_video/models/generation_event.py pixelle_video/services/generation_trace.py
git commit -m "feat: 新增本地生成追踪服务"
```

---

### Task 3: PromptPlan Contract With Reserved SceneCast Fields

**Files:**
- Create: `pixelle_video/models/prompt_plan.py`
- Test: `tests/test_prompt_plan_model.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompt_plan_model.py
from pixelle_video.models.prompt_plan import PromptPlan, PromptProjection


def test_prompt_plan_preserves_reserved_asset_fields():
    plan = PromptPlan.create(
        panel_id="frame_0001",
        base_prompt="a young detective enters a neon alley",
        final_prompt="cinematic comic panel, a young detective enters a neon alley",
        negative_prompt="blur, watermark",
        style_id="style_noir_comic",
        character_ids=["char_detective"],
        scene_id="scene_neon_alley",
        prop_ids=["prop_umbrella"],
        debug_parts={"style_block": "cinematic comic panel"},
    )

    payload = plan.to_dict()
    restored = PromptPlan.from_dict(payload)

    assert restored.prompt_plan_id.startswith("prompt_plan_")
    assert restored.character_ids == ("char_detective",)
    assert restored.scene_id == "scene_neon_alley"
    assert restored.debug_parts["style_block"] == "cinematic comic panel"


def test_prompt_projection_is_model_specific_and_not_fact_source():
    plan = PromptPlan.create(
        panel_id="frame_0001",
        base_prompt="base",
        final_prompt="final",
        negative_prompt="negative",
    )

    projection = PromptProjection.from_prompt_plan(
        plan,
        provider_id="comfyui",
        model_id="z-image",
    )

    assert projection.prompt == "final"
    assert projection.negative_prompt == "negative"
    assert projection.prompt_plan_id == plan.prompt_plan_id
    assert projection.provider_id == "comfyui"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_prompt_plan_model.py -v`

Expected: fail with missing `prompt_plan` module.

- [ ] **Step 3: Add PromptPlan and PromptProjection**

```python
# pixelle_video/models/prompt_plan.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.artifact import utc_iso_now


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value


def _stable_prompt_plan_id(panel_id: str, base_prompt: str, final_prompt: str | None) -> str:
    seed = "|".join([panel_id, base_prompt, final_prompt or ""])
    return f"prompt_plan_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True)
class PromptPlan:
    prompt_plan_id: str
    panel_id: str
    base_prompt: str
    final_prompt: str | None = None
    negative_prompt: str | None = None
    style_id: str | None = None
    world_id: str | None = None
    character_ids: tuple[str, ...] = field(default_factory=tuple)
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = field(default_factory=tuple)
    composer_version: str | None = None
    debug_parts: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        panel_id: str,
        base_prompt: str,
        final_prompt: str | None = None,
        negative_prompt: str | None = None,
        style_id: str | None = None,
        world_id: str | None = None,
        character_ids: list[str] | tuple[str, ...] | None = None,
        scene_id: str | None = None,
        prop_ids: list[str] | tuple[str, ...] | None = None,
        composer_version: str | None = None,
        debug_parts: Mapping[str, Any] | None = None,
    ) -> "PromptPlan":
        if not panel_id.strip():
            raise ValueError("panel_id must not be empty")
        if not base_prompt.strip():
            raise ValueError("base_prompt must not be empty")
        return cls(
            prompt_plan_id=_stable_prompt_plan_id(panel_id, base_prompt, final_prompt),
            panel_id=panel_id,
            base_prompt=base_prompt,
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            style_id=style_id,
            world_id=world_id,
            character_ids=tuple(character_ids or ()),
            scene_id=scene_id,
            prop_ids=tuple(prop_ids or ()),
            composer_version=composer_version,
            debug_parts=_json_copy(debug_parts or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan_id": self.prompt_plan_id,
            "panel_id": self.panel_id,
            "base_prompt": self.base_prompt,
            "final_prompt": self.final_prompt,
            "negative_prompt": self.negative_prompt,
            "style_id": self.style_id,
            "world_id": self.world_id,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "composer_version": self.composer_version,
            "debug_parts": _json_copy(self.debug_parts),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromptPlan":
        return cls(
            prompt_plan_id=str(payload["prompt_plan_id"]),
            panel_id=str(payload["panel_id"]),
            base_prompt=str(payload["base_prompt"]),
            final_prompt=payload.get("final_prompt"),
            negative_prompt=payload.get("negative_prompt"),
            style_id=payload.get("style_id"),
            world_id=payload.get("world_id"),
            character_ids=tuple(payload.get("character_ids") or ()),
            scene_id=payload.get("scene_id"),
            prop_ids=tuple(payload.get("prop_ids") or ()),
            composer_version=payload.get("composer_version"),
            debug_parts=_json_copy(payload.get("debug_parts") or {}),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class PromptProjection:
    prompt_plan_id: str
    provider_id: str
    model_id: str | None
    prompt: str
    negative_prompt: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_prompt_plan(
        cls,
        prompt_plan: PromptPlan,
        *,
        provider_id: str,
        model_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> "PromptProjection":
        prompt = prompt_plan.final_prompt or prompt_plan.base_prompt
        return cls(
            prompt_plan_id=prompt_plan.prompt_plan_id,
            provider_id=provider_id,
            model_id=model_id,
            prompt=prompt,
            negative_prompt=prompt_plan.negative_prompt,
            payload=_json_copy(payload or {}),
        )


__all__ = ["PromptPlan", "PromptProjection"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_prompt_plan_model.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_plan_model.py pixelle_video/models/prompt_plan.py
git commit -m "feat: 新增分镜提示词计划合同"
```

---

### Task 4: StoryboardFrame Workbench Metadata And Persistence

**Files:**
- Create: `pixelle_video/models/storyboard_workbench.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/test_storyboard_workbench_metadata.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storyboard_workbench_metadata.py
import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_workbench import (
    FrameLockPolicy,
    FrameStaleFlag,
    mark_frame_stale_after_prompt_change,
)
from pixelle_video.services.persistence import PersistenceService


def _config(task_id="task-1"):
    return StoryboardConfig(
        task_id=task_id,
        media_width=768,
        media_height=768,
        canvas_width=1280,
        canvas_height=720,
    )


def test_storyboard_frame_accepts_workbench_metadata():
    frame = StoryboardFrame(
        index=0,
        narration="第一格",
        image_prompt="old prompt",
        frame_id="frame_0001",
        panel_id="frame_0001",
        prompt_plan_id="prompt_plan_1",
        base_image_prompt="base prompt",
        final_image_prompt="final prompt",
        negative_prompt="blur",
        selected_image_version_id="artifact_image_v0002",
        lock_policy=FrameLockPolicy.LOCK_IMAGE.value,
        stale_flags=[FrameStaleFlag.VIDEO_SEGMENT.value],
        character_ids=["char_1"],
        scene_id="scene_1",
        prop_ids=["prop_1"],
    )

    assert frame.frame_id == "frame_0001"
    assert frame.selected_image_version_id == "artifact_image_v0002"
    assert frame.lock_policy == "lock_image"
    assert frame.stale_flags == ["video_segment"]
    assert frame.character_ids == ["char_1"]


def test_stale_helper_does_not_duplicate_flags():
    frame = StoryboardFrame(
        index=0,
        narration="第一格",
        image_prompt="old prompt",
        stale_flags=[FrameStaleFlag.IMAGE.value],
    )

    mark_frame_stale_after_prompt_change(frame)
    mark_frame_stale_after_prompt_change(frame)

    assert frame.stale_flags == ["image", "video_segment", "final_video"]


@pytest.mark.asyncio
async def test_persistence_round_trips_workbench_metadata(tmp_path):
    service = PersistenceService(output_dir=str(tmp_path))
    storyboard = Storyboard(
        title="demo",
        config=_config(),
        frames=[
            StoryboardFrame(
                index=0,
                narration="第一格",
                image_prompt="prompt",
                frame_id="frame_0001",
                panel_id="frame_0001",
                prompt_plan_id="prompt_plan_1",
                selected_image_version_id="artifact_image_v0002",
                lock_policy="lock_image",
                stale_flags=["video_segment"],
                prompt_debug={"style_block": "comic"},
                character_ids=["char_1"],
                scene_id="scene_1",
                prop_ids=["prop_1"],
            )
        ],
    )

    await service.save_storyboard("task-1", storyboard)
    restored = await service.load_storyboard("task-1")

    assert restored.frames[0].frame_id == "frame_0001"
    assert restored.frames[0].prompt_plan_id == "prompt_plan_1"
    assert restored.frames[0].selected_image_version_id == "artifact_image_v0002"
    assert restored.frames[0].prompt_debug == {"style_block": "comic"}
    assert restored.frames[0].character_ids == ["char_1"]
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_storyboard_workbench_metadata.py -v`

Expected: fail because `storyboard_workbench` does not exist and `StoryboardFrame` lacks the new fields.

- [ ] **Step 3: Add storyboard workbench helpers**

```python
# pixelle_video/models/storyboard_workbench.py
from __future__ import annotations

from enum import Enum
from typing import Protocol


class FrameLockPolicy(str, Enum):
    NONE = "none"
    LOCK_TEXT = "lock_text"
    LOCK_PROMPT = "lock_prompt"
    LOCK_IMAGE = "lock_image"
    LOCK_ALL = "lock_all"


class FrameStaleFlag(str, Enum):
    PROMPT_PLAN = "prompt_plan"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO_SEGMENT = "video_segment"
    FINAL_VIDEO = "final_video"


class MutableFrameStaleState(Protocol):
    stale_flags: list[str]


def add_stale_flags(frame: MutableFrameStaleState, flags: list[FrameStaleFlag | str]) -> None:
    existing = list(getattr(frame, "stale_flags", []) or [])
    for flag in flags:
        value = flag.value if isinstance(flag, FrameStaleFlag) else str(flag)
        if value not in existing:
            existing.append(value)
    frame.stale_flags = existing


def mark_frame_stale_after_prompt_change(frame: MutableFrameStaleState) -> None:
    add_stale_flags(
        frame,
        [
            FrameStaleFlag.IMAGE,
            FrameStaleFlag.VIDEO_SEGMENT,
            FrameStaleFlag.FINAL_VIDEO,
        ],
    )


def mark_frame_stale_after_selected_image_change(frame: MutableFrameStaleState) -> None:
    add_stale_flags(
        frame,
        [
            FrameStaleFlag.VIDEO_SEGMENT,
            FrameStaleFlag.FINAL_VIDEO,
        ],
    )


__all__ = [
    "FrameLockPolicy",
    "FrameStaleFlag",
    "add_stale_flags",
    "mark_frame_stale_after_prompt_change",
    "mark_frame_stale_after_selected_image_change",
]
```

- [ ] **Step 4: Extend StoryboardFrame with optional workbench fields**

Modify `pixelle_video/models/storyboard.py` inside `@dataclass class StoryboardFrame` by adding these fields after `frame_source`:

```python
    # Workbench identity and version selection
    frame_id: Optional[str] = None
    panel_id: Optional[str] = None
    prompt_plan_id: Optional[str] = None
    selected_image_version_id: Optional[str] = None
    selected_audio_version_id: Optional[str] = None
    selected_segment_version_id: Optional[str] = None

    # Prompt plan debug projection
    base_image_prompt: Optional[str] = None
    final_image_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    prompt_debug: Dict[str, Any] = field(default_factory=dict)

    # Human-in-the-loop state
    lock_policy: str = "none"
    stale_flags: List[str] = field(default_factory=list)

    # Reserved SceneCast fields for Stage 2
    character_ids: List[str] = field(default_factory=list)
    scene_id: Optional[str] = None
    prop_ids: List[str] = field(default_factory=list)
```

Update `__post_init__` in the same class:

```python
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.frame_id is None:
            self.frame_id = f"frame_{self.index + 1:04d}"
        if self.panel_id is None:
            self.panel_id = self.frame_id
        self.prompt_debug = dict(self.prompt_debug or {})
        self.stale_flags = list(self.stale_flags or [])
        self.character_ids = list(self.character_ids or [])
        self.prop_ids = list(self.prop_ids or [])
```

- [ ] **Step 5: Persist and restore the new fields**

Modify `PersistenceService._frame_to_dict()` by adding:

```python
            "frame_id": frame.frame_id,
            "panel_id": frame.panel_id,
            "prompt_plan_id": frame.prompt_plan_id,
            "selected_image_version_id": frame.selected_image_version_id,
            "selected_audio_version_id": frame.selected_audio_version_id,
            "selected_segment_version_id": frame.selected_segment_version_id,
            "base_image_prompt": frame.base_image_prompt,
            "final_image_prompt": frame.final_image_prompt,
            "negative_prompt": frame.negative_prompt,
            "prompt_debug": frame.prompt_debug,
            "lock_policy": frame.lock_policy,
            "stale_flags": frame.stale_flags,
            "character_ids": frame.character_ids,
            "scene_id": frame.scene_id,
            "prop_ids": frame.prop_ids,
```

Modify `PersistenceService._dict_to_frame()` by adding matching keyword arguments:

```python
            frame_id=data.get("frame_id"),
            panel_id=data.get("panel_id"),
            prompt_plan_id=data.get("prompt_plan_id"),
            selected_image_version_id=data.get("selected_image_version_id"),
            selected_audio_version_id=data.get("selected_audio_version_id"),
            selected_segment_version_id=data.get("selected_segment_version_id"),
            base_image_prompt=data.get("base_image_prompt"),
            final_image_prompt=data.get("final_image_prompt"),
            negative_prompt=data.get("negative_prompt"),
            prompt_debug=data.get("prompt_debug") or {},
            lock_policy=data.get("lock_policy", "none"),
            stale_flags=data.get("stale_flags") or [],
            character_ids=data.get("character_ids") or [],
            scene_id=data.get("scene_id"),
            prop_ids=data.get("prop_ids") or [],
```

- [ ] **Step 6: Run the tests to verify pass**

Run: `pytest tests/test_storyboard_workbench_metadata.py tests/test_storyboard_snapshot_persistence.py -v`

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_storyboard_workbench_metadata.py pixelle_video/models/storyboard_workbench.py pixelle_video/models/storyboard.py pixelle_video/services/persistence.py
git commit -m "feat: 扩展分镜帧工作台元数据"
```

---

### Task 5: Local JSON Artifact Service

**Files:**
- Create: `pixelle_video/services/artifact_service.py`
- Test: `tests/test_artifact_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_artifact_service.py
import pytest

from pixelle_video.models.artifact import ArtifactType, ArtifactVersionStatus
from pixelle_video.services.artifact_service import LocalJsonArtifactService


@pytest.mark.asyncio
async def test_artifact_service_creates_versions_and_selects_one(tmp_path):
    service = LocalJsonArtifactService(output_dir=tmp_path)

    artifact = await service.get_or_create_artifact(
        task_id="task-1",
        project_id="project-1",
        artifact_type=ArtifactType.IMAGE,
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    first = await service.create_version(
        task_id="task-1",
        artifact_id=artifact.artifact_id,
        status=ArtifactVersionStatus.CANDIDATE,
        object_key="task-1/artifacts/images/frame_0001_v1.png",
    )
    second = await service.create_version(
        task_id="task-1",
        artifact_id=artifact.artifact_id,
        status=ArtifactVersionStatus.CANDIDATE,
        object_key="task-1/artifacts/images/frame_0001_v2.png",
    )

    selected = await service.select_version(
        task_id="task-1",
        artifact_id=artifact.artifact_id,
        artifact_version_id=second.artifact_version_id,
    )
    versions = await service.list_versions(task_id="task-1", artifact_id=artifact.artifact_id)

    assert selected.current_selected_version_id == second.artifact_version_id
    assert [version.version for version in versions] == [1, 2]
    assert versions[0].artifact_version_id == first.artifact_version_id
    assert versions[1].status == ArtifactVersionStatus.SELECTED


@pytest.mark.asyncio
async def test_artifact_service_rejects_selecting_foreign_version(tmp_path):
    service = LocalJsonArtifactService(output_dir=tmp_path)
    image = await service.get_or_create_artifact(
        task_id="task-1",
        project_id="project-1",
        artifact_type="image",
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    audio = await service.get_or_create_artifact(
        task_id="task-1",
        project_id="project-1",
        artifact_type="audio",
        logical_key="frame_0001_audio",
        frame_id="frame_0001",
    )
    audio_version = await service.create_version(
        task_id="task-1",
        artifact_id=audio.artifact_id,
        status="candidate",
    )

    with pytest.raises(ValueError, match="does not belong to artifact"):
        await service.select_version(
            task_id="task-1",
            artifact_id=image.artifact_id,
            artifact_version_id=audio_version.artifact_version_id,
        )
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_artifact_service.py -v`

Expected: fail with missing `artifact_service` module.

- [ ] **Step 3: Add the local JSON artifact service**

```python
# pixelle_video/services/artifact_service.py
from __future__ import annotations

import json
from pathlib import Path

from pixelle_video.models.artifact import (
    Artifact,
    ArtifactType,
    ArtifactVersion,
    ArtifactVersionStatus,
)


class LocalJsonArtifactService:
    def __init__(self, output_dir: str | Path = "output") -> None:
        self.output_dir = Path(output_dir)

    def get_registry_path(self, task_id: str) -> Path:
        return self.output_dir / task_id / "artifacts.json"

    async def get_or_create_artifact(
        self,
        *,
        task_id: str,
        project_id: str,
        artifact_type: ArtifactType | str,
        logical_key: str,
        frame_id: str | None = None,
    ) -> Artifact:
        registry = self._load_registry(task_id)
        candidate = Artifact.create(
            project_id=project_id,
            artifact_type=artifact_type,
            logical_key=logical_key,
            frame_id=frame_id,
        )
        existing = registry["artifacts"].get(candidate.artifact_id)
        if existing:
            return Artifact.from_dict(existing)
        registry["artifacts"][candidate.artifact_id] = candidate.to_dict()
        self._save_registry(task_id, registry)
        return candidate

    async def create_version(
        self,
        *,
        task_id: str,
        artifact_id: str,
        status: ArtifactVersionStatus | str,
        object_key: str | None = None,
        url: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        prompt: str | None = None,
        seed: int | None = None,
        payload: dict | None = None,
        metadata: dict | None = None,
    ) -> ArtifactVersion:
        registry = self._load_registry(task_id)
        if artifact_id not in registry["artifacts"]:
            raise ValueError(f"artifact not found: {artifact_id}")
        existing_versions = [
            ArtifactVersion.from_dict(version)
            for version in registry["versions"].values()
            if version["artifact_id"] == artifact_id
        ]
        next_version = max([version.version for version in existing_versions], default=0) + 1
        artifact_version = ArtifactVersion.create(
            artifact_id=artifact_id,
            version=next_version,
            status=status,
            object_key=object_key,
            url=url,
            provider_id=provider_id,
            model_id=model_id,
            prompt=prompt,
            seed=seed,
            payload=payload,
            metadata=metadata,
        )
        registry["versions"][artifact_version.artifact_version_id] = artifact_version.to_dict()
        self._save_registry(task_id, registry)
        return artifact_version

    async def list_versions(self, *, task_id: str, artifact_id: str) -> list[ArtifactVersion]:
        registry = self._load_registry(task_id)
        versions = [
            ArtifactVersion.from_dict(version)
            for version in registry["versions"].values()
            if version["artifact_id"] == artifact_id
        ]
        return sorted(versions, key=lambda version: version.version)

    async def list_frame_artifacts(
        self,
        *,
        task_id: str,
        frame_id: str,
    ) -> list[tuple[Artifact, list[ArtifactVersion]]]:
        registry = self._load_registry(task_id)
        frame_artifacts: list[tuple[Artifact, list[ArtifactVersion]]] = []
        for artifact_payload in registry["artifacts"].values():
            artifact = Artifact.from_dict(artifact_payload)
            if artifact.frame_id != frame_id:
                continue
            versions = await self.list_versions(
                task_id=task_id,
                artifact_id=artifact.artifact_id,
            )
            frame_artifacts.append((artifact, versions))
        return frame_artifacts

    async def select_version(
        self,
        *,
        task_id: str,
        artifact_id: str,
        artifact_version_id: str,
    ) -> Artifact:
        registry = self._load_registry(task_id)
        artifact_payload = registry["artifacts"].get(artifact_id)
        if artifact_payload is None:
            raise ValueError(f"artifact not found: {artifact_id}")
        version_payload = registry["versions"].get(artifact_version_id)
        if version_payload is None:
            raise ValueError(f"artifact version not found: {artifact_version_id}")
        version = ArtifactVersion.from_dict(version_payload)
        if version.artifact_id != artifact_id:
            raise ValueError("artifact version does not belong to artifact")

        for key, payload in list(registry["versions"].items()):
            current = ArtifactVersion.from_dict(payload)
            if current.artifact_id != artifact_id:
                continue
            new_status = (
                ArtifactVersionStatus.SELECTED
                if key == artifact_version_id
                else ArtifactVersionStatus.CANDIDATE
            )
            registry["versions"][key] = current.with_status(new_status).to_dict()

        artifact = Artifact.from_dict(artifact_payload).select_version(artifact_version_id)
        registry["artifacts"][artifact_id] = artifact.to_dict()
        self._save_registry(task_id, registry)
        return artifact

    def _load_registry(self, task_id: str) -> dict:
        path = self.get_registry_path(task_id)
        if not path.exists():
            return {"version": 1, "artifacts": {}, "versions": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_registry(self, task_id: str, registry: dict) -> None:
        path = self.get_registry_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = ["LocalJsonArtifactService"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_artifact_service.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_artifact_service.py pixelle_video/services/artifact_service.py
git commit -m "feat: 新增本地产物版本服务"
```

---

### Task 6: Storyboard Workbench Selection Service

**Files:**
- Create: `pixelle_video/services/storyboard_workbench.py`
- Test: `tests/test_storyboard_workbench_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storyboard_workbench_service.py
import pytest

from pixelle_video.models.artifact import ArtifactType
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.artifact_service import LocalJsonArtifactService
from pixelle_video.services.generation_trace import LocalJsonGenerationTraceService
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService


def _storyboard():
    return Storyboard(
        title="demo",
        config=StoryboardConfig(task_id="task-1", media_width=768, media_height=768),
        frames=[
            StoryboardFrame(
                index=0,
                narration="第一格",
                image_prompt="prompt",
                frame_id="frame_0001",
            )
        ],
    )


@pytest.mark.asyncio
async def test_select_image_version_updates_frame_and_marks_downstream_stale(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    artifact_service = LocalJsonArtifactService(output_dir=tmp_path)
    trace_service = LocalJsonGenerationTraceService(output_dir=tmp_path)
    service = StoryboardWorkbenchService(
        persistence=persistence,
        artifacts=artifact_service,
        trace=trace_service,
    )
    await persistence.save_storyboard("task-1", _storyboard())
    artifact = await artifact_service.get_or_create_artifact(
        task_id="task-1",
        project_id="task-1",
        artifact_type=ArtifactType.IMAGE,
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    version = await artifact_service.create_version(
        task_id="task-1",
        artifact_id=artifact.artifact_id,
        status="candidate",
        object_key="task-1/artifacts/images/frame_0001_v1.png",
    )

    updated_frame = await service.select_frame_image_version(
        task_id="task-1",
        frame_id="frame_0001",
        artifact_id=artifact.artifact_id,
        artifact_version_id=version.artifact_version_id,
    )
    restored = await persistence.load_storyboard("task-1")
    events = await trace_service.load_events("task-1")

    assert updated_frame.selected_image_version_id == version.artifact_version_id
    assert restored.frames[0].selected_image_version_id == version.artifact_version_id
    assert restored.frames[0].stale_flags == ["video_segment", "final_video"]
    assert events[-1].event_type == "artifact_selected"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_storyboard_workbench_service.py -v`

Expected: fail with missing `StoryboardWorkbenchService`.

- [ ] **Step 3: Add the selection service**

```python
# pixelle_video/services/storyboard_workbench.py
from __future__ import annotations

from pixelle_video.models.generation_event import GenerationEvent
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.models.storyboard_workbench import mark_frame_stale_after_selected_image_change
from pixelle_video.services.artifact_service import LocalJsonArtifactService
from pixelle_video.services.generation_trace import LocalJsonGenerationTraceService
from pixelle_video.services.persistence import PersistenceService


class StoryboardWorkbenchService:
    def __init__(
        self,
        *,
        persistence: PersistenceService | None = None,
        artifacts: LocalJsonArtifactService | None = None,
        trace: LocalJsonGenerationTraceService | None = None,
    ) -> None:
        self.persistence = persistence or PersistenceService()
        self.artifacts = artifacts or LocalJsonArtifactService(self.persistence.output_dir)
        self.trace = trace or LocalJsonGenerationTraceService(self.persistence.output_dir)

    async def select_frame_image_version(
        self,
        *,
        task_id: str,
        frame_id: str,
        artifact_id: str,
        artifact_version_id: str,
    ) -> StoryboardFrame:
        storyboard = await self.persistence.load_storyboard(task_id)
        if storyboard is None:
            raise ValueError(f"storyboard not found for task: {task_id}")

        frame = self._find_frame(storyboard.frames, frame_id)
        selected_artifact = await self.artifacts.select_version(
            task_id=task_id,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
        )
        frame.selected_image_version_id = selected_artifact.current_selected_version_id
        mark_frame_stale_after_selected_image_change(frame)
        await self.persistence.save_storyboard(task_id, storyboard)
        await self.trace.record_event(
            GenerationEvent.create(
                task_id=task_id,
                stage="storyboard.image.select",
                event_type="artifact_selected",
                frame_id=frame.frame_id,
                artifact_id=artifact_id,
                artifact_version_id=artifact_version_id,
                message="frame image version selected",
            )
        )
        return frame

    def _find_frame(self, frames: list[StoryboardFrame], frame_id: str) -> StoryboardFrame:
        for frame in frames:
            if frame.frame_id == frame_id or frame.panel_id == frame_id:
                return frame
        raise ValueError(f"frame not found: {frame_id}")


__all__ = ["StoryboardWorkbenchService"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_storyboard_workbench_service.py -v`

Expected: one test passes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_storyboard_workbench_service.py pixelle_video/services/storyboard_workbench.py
git commit -m "feat: 新增分镜图片版本选择服务"
```

---

### Task 7: PromptPlan Builder From StoryboardPlan And Generated Prompts

**Files:**
- Create: `pixelle_video/services/prompt_plan_service.py`
- Test: `tests/test_prompt_plan_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompt_plan_service.py
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.prompt_plan_service import build_prompt_plans


def _plan():
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                visual_goal="show first",
                prompt_intent="first intent",
                source_start=0,
                source_end=4,
                metadata={
                    "style_id": "style_comic",
                    "character_ids": ["char_1"],
                    "scene_id": "scene_1",
                    "prop_ids": ["prop_1"],
                },
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                visual_goal="show second",
                prompt_intent="second intent",
                source_start=4,
                source_end=8,
            ),
        ],
    )


def test_build_prompt_plans_preserves_frame_identity_and_reserved_assets():
    prompt_plans = build_prompt_plans(
        storyboard_plan=_plan(),
        final_prompts=["final prompt one", "final prompt two"],
        negative_prompt="blur",
        composer_version="stage1",
    )

    assert len(prompt_plans) == 2
    assert prompt_plans[0].panel_id == _plan().frames[0].frame_id
    assert prompt_plans[0].base_prompt == "first intent"
    assert prompt_plans[0].final_prompt == "final prompt one"
    assert prompt_plans[0].character_ids == ("char_1",)
    assert prompt_plans[0].scene_id == "scene_1"
    assert prompt_plans[1].base_prompt == "second intent"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_prompt_plan_service.py -v`

Expected: fail with missing `prompt_plan_service`.

- [ ] **Step 3: Add PromptPlan builder service**

```python
# pixelle_video/services/prompt_plan_service.py
from __future__ import annotations

from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.storyboard_plan import StoryboardPlan


def _metadata_list(metadata: dict, key: str) -> list[str]:
    value = metadata.get(key)
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def build_prompt_plans(
    *,
    storyboard_plan: StoryboardPlan,
    final_prompts: list[str],
    negative_prompt: str | None = None,
    composer_version: str | None = None,
) -> list[PromptPlan]:
    if len(final_prompts) != storyboard_plan.resolved_scene_count:
        raise ValueError("final prompt count must match storyboard frame count")

    prompt_plans: list[PromptPlan] = []
    for frame, final_prompt in zip(storyboard_plan.frames, final_prompts):
        metadata = dict(frame.metadata)
        prompt_plans.append(
            PromptPlan.create(
                panel_id=frame.frame_id,
                base_prompt=frame.prompt_intent,
                final_prompt=final_prompt,
                negative_prompt=negative_prompt,
                style_id=metadata.get("style_id"),
                world_id=metadata.get("world_id"),
                character_ids=_metadata_list(metadata, "character_ids"),
                scene_id=metadata.get("scene_id"),
                prop_ids=_metadata_list(metadata, "prop_ids"),
                composer_version=composer_version,
                debug_parts={
                    "source_text": frame.source_text,
                    "visual_goal": frame.visual_goal,
                    "shot_type": frame.shot_type,
                    "continuity_anchors": list(frame.continuity_anchors),
                },
            )
        )
    return prompt_plans


__all__ = ["build_prompt_plans"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_prompt_plan_service.py -v`

Expected: one test passes.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_plan_service.py pixelle_video/services/prompt_plan_service.py
git commit -m "feat: 新增提示词计划构建服务"
```

---

### Task 8: Storyboard Workbench API For Listing And Selecting Artifacts

**Files:**
- Create: `api/schemas/storyboard_workbench.py`
- Create: `api/routers/storyboard_workbench.py`
- Modify: `api/app.py`
- Test: `tests/test_storyboard_workbench_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storyboard_workbench_api.py
from types import SimpleNamespace

import pytest

from api.routers.storyboard_workbench import get_frame_artifacts, select_frame_image_version
from api.schemas.storyboard_workbench import SelectFrameImageVersionRequest
from pixelle_video.models.artifact import ArtifactType
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.artifact_service import LocalJsonArtifactService
from pixelle_video.services.generation_trace import LocalJsonGenerationTraceService
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService


def _service(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    artifacts = LocalJsonArtifactService(output_dir=tmp_path)
    trace = LocalJsonGenerationTraceService(output_dir=tmp_path)
    return StoryboardWorkbenchService(
        persistence=persistence,
        artifacts=artifacts,
        trace=trace,
    )


@pytest.mark.asyncio
async def test_get_frame_artifacts_returns_versions(monkeypatch, tmp_path):
    service = _service(tmp_path)
    await service.persistence.save_storyboard(
        "task-1",
        Storyboard(
            title="demo",
            config=StoryboardConfig(task_id="task-1", media_width=768, media_height=768),
            frames=[StoryboardFrame(index=0, narration="n", image_prompt="p", frame_id="frame_0001")],
        ),
    )
    artifact = await service.artifacts.get_or_create_artifact(
        task_id="task-1",
        project_id="task-1",
        artifact_type=ArtifactType.IMAGE,
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    version = await service.artifacts.create_version(
        task_id="task-1",
        artifact_id=artifact.artifact_id,
        status="candidate",
    )
    monkeypatch.setattr(
        "api.routers.storyboard_workbench.StoryboardWorkbenchService",
        lambda: service,
    )

    response = await get_frame_artifacts(task_id="task-1", frame_id="frame_0001")

    assert response.frame_id == "frame_0001"
    assert response.artifacts[0].artifact_id == artifact.artifact_id
    assert response.artifacts[0].versions[0].artifact_version_id == version.artifact_version_id


@pytest.mark.asyncio
async def test_select_frame_image_version_returns_updated_frame(monkeypatch, tmp_path):
    service = _service(tmp_path)
    await service.persistence.save_storyboard(
        "task-1",
        Storyboard(
            title="demo",
            config=StoryboardConfig(task_id="task-1", media_width=768, media_height=768),
            frames=[StoryboardFrame(index=0, narration="n", image_prompt="p", frame_id="frame_0001")],
        ),
    )
    artifact = await service.artifacts.get_or_create_artifact(
        task_id="task-1",
        project_id="task-1",
        artifact_type="image",
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    version = await service.artifacts.create_version(
        task_id="task-1",
        artifact_id=artifact.artifact_id,
        status="candidate",
    )
    monkeypatch.setattr(
        "api.routers.storyboard_workbench.StoryboardWorkbenchService",
        lambda: service,
    )

    response = await select_frame_image_version(
        task_id="task-1",
        frame_id="frame_0001",
        request=SelectFrameImageVersionRequest(
            artifact_id=artifact.artifact_id,
            artifact_version_id=version.artifact_version_id,
        ),
    )

    assert response.frame_id == "frame_0001"
    assert response.selected_image_version_id == version.artifact_version_id
    assert response.stale_flags == ["video_segment", "final_video"]
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_storyboard_workbench_api.py -v`

Expected: fail with missing API schema/router modules.

- [ ] **Step 3: Add API schemas**

```python
# api/schemas/storyboard_workbench.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArtifactVersionResponse(BaseModel):
    artifact_version_id: str
    version: int
    status: str
    object_key: str | None = None
    url: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    prompt: str | None = None
    seed: int | None = None
    payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ArtifactResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    logical_key: str
    frame_id: str | None = None
    current_selected_version_id: str | None = None
    versions: list[ArtifactVersionResponse] = Field(default_factory=list)


class FrameArtifactsResponse(BaseModel):
    task_id: str
    frame_id: str
    artifacts: list[ArtifactResponse] = Field(default_factory=list)


class SelectFrameImageVersionRequest(BaseModel):
    artifact_id: str
    artifact_version_id: str


class FrameSelectionResponse(BaseModel):
    task_id: str
    frame_id: str
    selected_image_version_id: str | None
    stale_flags: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Add API router**

```python
# api/routers/storyboard_workbench.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.storyboard_workbench import (
    ArtifactResponse,
    ArtifactVersionResponse,
    FrameArtifactsResponse,
    FrameSelectionResponse,
    SelectFrameImageVersionRequest,
)
from pixelle_video.models.artifact import Artifact
from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService

router = APIRouter(prefix="/storyboards", tags=["Storyboard Workbench"])


@router.get("/{task_id}/frames/{frame_id}/artifacts", response_model=FrameArtifactsResponse)
async def get_frame_artifacts(task_id: str, frame_id: str) -> FrameArtifactsResponse:
    service = StoryboardWorkbenchService()
    try:
        artifacts: list[ArtifactResponse] = []
        for artifact, versions in await service.artifacts.list_frame_artifacts(
            task_id=task_id,
            frame_id=frame_id,
        ):
            artifacts.append(
                ArtifactResponse(
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type.value,
                    logical_key=artifact.logical_key,
                    frame_id=artifact.frame_id,
                    current_selected_version_id=artifact.current_selected_version_id,
                    versions=[
                        ArtifactVersionResponse(**version.to_dict())
                        for version in versions
                    ],
                )
            )
        return FrameArtifactsResponse(task_id=task_id, frame_id=frame_id, artifacts=artifacts)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/frames/{frame_id}/select-image-version", response_model=FrameSelectionResponse)
async def select_frame_image_version(
    task_id: str,
    frame_id: str,
    request: SelectFrameImageVersionRequest,
) -> FrameSelectionResponse:
    service = StoryboardWorkbenchService()
    try:
        frame = await service.select_frame_image_version(
            task_id=task_id,
            frame_id=frame_id,
            artifact_id=request.artifact_id,
            artifact_version_id=request.artifact_version_id,
        )
        return FrameSelectionResponse(
            task_id=task_id,
            frame_id=frame.frame_id or frame_id,
            selected_image_version_id=frame.selected_image_version_id,
            stale_flags=frame.stale_flags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 5: Register the router**

Modify `api/app.py` imports:

```python
from api.routers.storyboard_workbench import router as storyboard_workbench_router
```

Modify router registration near other routers:

```python
app.include_router(storyboard_workbench_router, prefix=api_config.api_prefix)
```

- [ ] **Step 6: Run the tests to verify pass**

Run: `pytest tests/test_storyboard_workbench_api.py -v`

Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_storyboard_workbench_api.py api/schemas/storyboard_workbench.py api/routers/storyboard_workbench.py api/app.py
git commit -m "feat: 新增分镜工作台产物接口"
```

---

### Task 9: Frame Image Regeneration Task

**Files:**
- Modify: `api/tasks/models.py`
- Create or modify: `pixelle_video/services/storyboard_workbench.py`
- Modify: `api/routers/storyboard_workbench.py`
- Modify: `api/schemas/storyboard_workbench.py`
- Test: `tests/test_storyboard_frame_regeneration.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storyboard_frame_regeneration.py
from types import SimpleNamespace

import pytest

from api.tasks.models import TaskType
from pixelle_video.models.artifact import ArtifactType
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.artifact_service import LocalJsonArtifactService
from pixelle_video.services.generation_trace import LocalJsonGenerationTraceService
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService


def test_task_type_includes_frame_image_regeneration():
    assert TaskType.FRAME_IMAGE_REGENERATION.value == "frame_image_regeneration"


@pytest.mark.asyncio
async def test_regenerate_frame_image_creates_candidate_artifact(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    artifacts = LocalJsonArtifactService(output_dir=tmp_path)
    trace = LocalJsonGenerationTraceService(output_dir=tmp_path)
    service = StoryboardWorkbenchService(
        persistence=persistence,
        artifacts=artifacts,
        trace=trace,
    )
    await persistence.save_storyboard(
        "task-1",
        Storyboard(
            title="demo",
            config=StoryboardConfig(
                task_id="task-1",
                media_width=768,
                media_height=768,
                media_workflow="selfhost/image_z_image_turbo.json",
            ),
            frames=[
                StoryboardFrame(
                    index=0,
                    narration="n",
                    image_prompt="prompt",
                    final_image_prompt="final prompt",
                    frame_id="frame_0001",
                )
            ],
        ),
    )

    class _FakeMedia:
        async def __call__(self, **kwargs):
            assert kwargs["prompt"] == "final prompt"
            assert kwargs["media_type"] == "image"
            return SimpleNamespace(
                url=str(tmp_path / "generated.png"),
                media_type="image",
                is_image=True,
                is_video=False,
            )

    fake_core = SimpleNamespace(media=_FakeMedia())
    (tmp_path / "generated.png").write_bytes(b"image")

    version = await service.regenerate_frame_image(
        task_id="task-1",
        frame_id="frame_0001",
        pixelle_video=fake_core,
        provider_id="comfyui",
        model_id="z-image",
    )
    artifact = await artifacts.get_or_create_artifact(
        task_id="task-1",
        project_id="task-1",
        artifact_type=ArtifactType.IMAGE,
        logical_key="frame_0001_image",
        frame_id="frame_0001",
    )
    versions = await artifacts.list_versions(task_id="task-1", artifact_id=artifact.artifact_id)
    events = await trace.load_events("task-1")

    assert version.status.value == "candidate"
    assert versions[0].artifact_version_id == version.artifact_version_id
    assert events[-1].event_type == "artifact_created"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_storyboard_frame_regeneration.py -v`

Expected: fail because `FRAME_IMAGE_REGENERATION` and `regenerate_frame_image` do not exist.

- [ ] **Step 3: Add the task type**

Modify `api/tasks/models.py`:

```python
class TaskType(str, Enum):
    """Task type"""
    VIDEO_GENERATION = "video_generation"
    FRAME_IMAGE_REGENERATION = "frame_image_regeneration"
```

- [ ] **Step 4: Add regeneration service method**

Append to `StoryboardWorkbenchService`:

```python
    async def regenerate_frame_image(
        self,
        *,
        task_id: str,
        frame_id: str,
        pixelle_video,
        provider_id: str | None = None,
        model_id: str | None = None,
    ):
        storyboard = await self.persistence.load_storyboard(task_id)
        if storyboard is None:
            raise ValueError(f"storyboard not found for task: {task_id}")
        frame = self._find_frame(storyboard.frames, frame_id)
        prompt = frame.final_image_prompt or frame.image_prompt
        if not prompt:
            raise ValueError("frame has no prompt for image regeneration")

        await self.trace.record_event(
            GenerationEvent.create(
                task_id=task_id,
                stage="storyboard.image.regenerate",
                event_type="provider_request",
                frame_id=frame.frame_id,
                provider_id=provider_id,
                message="frame image regeneration requested",
                payload={"prompt": prompt},
            )
        )
        media_result = await pixelle_video.media(
            prompt=prompt,
            workflow=storyboard.config.media_workflow,
            media_type="image",
            width=storyboard.config.media_width,
            height=storyboard.config.media_height,
            index=frame.index + 1,
        )
        artifact = await self.artifacts.get_or_create_artifact(
            task_id=task_id,
            project_id=task_id,
            artifact_type="image",
            logical_key=f"{frame.frame_id}_image",
            frame_id=frame.frame_id,
        )
        version = await self.artifacts.create_version(
            task_id=task_id,
            artifact_id=artifact.artifact_id,
            status="candidate",
            url=str(media_result.url),
            provider_id=provider_id,
            model_id=model_id,
            prompt=prompt,
            metadata={"media_type": getattr(media_result, "media_type", "image")},
        )
        await self.trace.record_event(
            GenerationEvent.create(
                task_id=task_id,
                stage="storyboard.image.regenerate",
                event_type="artifact_created",
                frame_id=frame.frame_id,
                artifact_id=artifact.artifact_id,
                artifact_version_id=version.artifact_version_id,
                provider_id=provider_id,
                message="frame image candidate created",
            )
        )
        return version
```

- [ ] **Step 5: Add API schema and endpoint**

Modify `api/schemas/storyboard_workbench.py`:

```python
class RegenerateFrameImageRequest(BaseModel):
    provider_id: str | None = None
    model_id: str | None = None


class RegenerateFrameImageResponse(BaseModel):
    task_id: str
    message: str = "Frame image regeneration task created"
```

Modify `api/routers/storyboard_workbench.py` imports:

```python
from api.schemas.storyboard_workbench import RegenerateFrameImageRequest, RegenerateFrameImageResponse
from api.tasks import TaskType, task_manager
from pixelle_video.services.generation_coordinator import build_generation_fingerprint
```

Add endpoint:

```python
@router.post("/{task_id}/frames/{frame_id}/regenerate-image", response_model=RegenerateFrameImageResponse)
async def regenerate_frame_image(
    task_id: str,
    frame_id: str,
    request: RegenerateFrameImageRequest,
    pixelle_video,
) -> RegenerateFrameImageResponse:
    generation_fingerprint = build_generation_fingerprint(
        text=f"{task_id}:{frame_id}:image",
        pipeline="storyboard_frame_image_regeneration",
        params=request.model_dump(exclude_none=True),
    )
    outcome = await task_manager.reserve_or_reuse_generation_task(
        task_type=TaskType.FRAME_IMAGE_REGENERATION,
        generation_fingerprint=generation_fingerprint,
        request_params={
            "task_id": task_id,
            "frame_id": frame_id,
            **request.model_dump(exclude_none=True),
            "generation_fingerprint": generation_fingerprint,
        },
    )
    if outcome.created and getattr(task_manager, "execution_mode", "embedded") == "embedded":
        async def execute():
            version = await StoryboardWorkbenchService().regenerate_frame_image(
                task_id=task_id,
                frame_id=frame_id,
                pixelle_video=pixelle_video,
                provider_id=request.provider_id,
                model_id=request.model_id,
            )
            return version.to_dict()

        await task_manager.execute_task(task_id=outcome.task.task_id, coro_func=execute)
    return RegenerateFrameImageResponse(task_id=outcome.task.task_id)
```

When implementing this endpoint, use the project dependency pattern from `api/routers/video.py` by adding `pixelle_video: PixelleVideoDep` instead of leaving the untyped parameter. The code block above shows the execution body; the actual function signature must be:

```python
async def regenerate_frame_image(
    task_id: str,
    frame_id: str,
    request: RegenerateFrameImageRequest,
    pixelle_video: PixelleVideoDep,
) -> RegenerateFrameImageResponse:
```

- [ ] **Step 6: Run focused tests**

Run: `pytest tests/test_storyboard_frame_regeneration.py tests/test_worker_execution.py -v`

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_storyboard_frame_regeneration.py api/tasks/models.py api/schemas/storyboard_workbench.py api/routers/storyboard_workbench.py pixelle_video/services/storyboard_workbench.py
git commit -m "feat: 新增分镜图片重抽任务"
```

---

### Task 10: Raw Generation Parameter Deprecation Markers

**Files:**
- Modify: `api/schemas/video.py`
- Test: `tests/test_raw_generation_parameter_policy.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_raw_generation_parameter_policy.py
from api.schemas.video import VideoGenerateRequest


def test_raw_generation_fields_are_marked_deprecated_in_schema():
    schema = VideoGenerateRequest.model_json_schema()
    properties = schema["properties"]

    for field_name in [
        "tts_workflow",
        "ref_audio",
        "media_workflow",
        "frame_template",
        "prompt_prefix",
        "bgm_path",
    ]:
        assert properties[field_name]["deprecated"] is True
        assert "legacy" in properties[field_name]["description"].lower()
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_raw_generation_parameter_policy.py -v`

Expected: fail because the fields are not marked deprecated.

- [ ] **Step 3: Mark raw parameters as legacy/deprecated without removing them**

Modify the `Field(...)` declarations in `api/schemas/video.py`:

```python
    tts_workflow: Optional[str] = Field(
        None,
        description=(
            "Legacy App/API field: TTS workflow key. Future public APIs must use "
            "voice_id or voice_preset_id resolved by backend policy."
        ),
        deprecated=True,
    )
    ref_audio: Optional[str] = Field(
        None,
        description=(
            "Legacy App/API field: reference audio path. Future public APIs must use "
            "voice_asset_id resolved by backend policy."
        ),
        deprecated=True,
    )
```

Apply the same pattern to:

```python
    media_workflow: Optional[str] = Field(
        None,
        description=(
            "Legacy App/API field: raw media workflow key. Future public APIs must use "
            "workflow_preset_id or provider_preset_id resolved by backend policy."
        ),
        deprecated=True,
    )
```

```python
    frame_template: Optional[str] = Field(
        None,
        description=(
            "Legacy App/API field: raw template path. Future public APIs must use "
            "template_id resolved by backend policy."
        ),
        deprecated=True,
    )
```

```python
    prompt_prefix: Optional[str] = Field(
        None,
        description=(
            "Legacy App/API field: raw image style prefix. Future public APIs must use "
            "style_id or style_preset_id resolved by backend policy."
        ),
        deprecated=True,
    )
```

```python
    bgm_path: Optional[str] = Field(
        None,
        description=(
            "Legacy App/API field: raw background music path. Future public APIs must use "
            "bgm_id resolved by backend policy."
        ),
        deprecated=True,
    )
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_raw_generation_parameter_policy.py tests/test_video_api.py::test_generate_video_sync_passes_storyboard_controls_to_video_core -v`

Expected: both selected tests pass and existing raw fields still work for compatibility.

- [ ] **Step 5: Commit**

```bash
git add tests/test_raw_generation_parameter_policy.py api/schemas/video.py
git commit -m "feat: 标记生成接口原始参数为兼容字段"
```

---

## Stage 1B Verification Checklist

Run these commands after all tasks are implemented:

```bash
pytest \
  tests/test_artifact_models.py \
  tests/test_generation_trace_service.py \
  tests/test_prompt_plan_model.py \
  tests/test_storyboard_workbench_metadata.py \
  tests/test_artifact_service.py \
  tests/test_storyboard_workbench_service.py \
  tests/test_prompt_plan_service.py \
  tests/test_storyboard_workbench_api.py \
  tests/test_storyboard_frame_regeneration.py \
  tests/test_raw_generation_parameter_policy.py \
  -v
```

Expected: all selected Stage 1B tests pass.

Run compatibility tests:

```bash
pytest \
  tests/test_storyboard_plan_model.py \
  tests/test_image_prompt_composer.py \
  tests/test_storyboard_snapshot_persistence.py \
  tests/test_video_api.py \
  tests/test_worker_execution.py \
  -v
```

Expected: all selected compatibility tests pass.

## Implementation Notes

- Execute the Stage 1A text/image-prompt plan before using this plan for production code. If Stage 1A is not implemented yet, only the pure contract tasks in this plan may proceed.
- Do not remove existing `prompt_prefix`, `media_workflow`, `frame_template`, `bgm_path`, `ref_audio`, or `tts_workflow` behavior in Stage 1B. Mark them legacy/deprecated only.
- Do not make FlowGram part of this plan.
- Do not introduce database migrations in Stage 1B. Local JSON/JSONL services are acceptable because they are hidden behind service classes.
- Do not directly manipulate `output/{task_id}/artifacts.json` outside `LocalJsonArtifactService`.
- Do not directly manipulate `output/{task_id}/trace/events.jsonl` outside `LocalJsonGenerationTraceService`.
- Keep `StoryboardFrame.index` zero-based in the current runtime model. Keep `StoryboardPlanFrame.index` one-based as it already is.
- Use `frame_id` for workbench identity. Use `index` only for ordering and existing render compatibility.
- Use Superpowers skills as execution gates, not as replacement architecture sources. The architecture source is the master plan plus Stage 1 subplans listed in Planning Authority.
- Follow TDD for every production-code task. If a listed failing test cannot fail for the expected reason, stop and revise the task before implementing.
- Do not use `git worktree`; AGENTS.md forbids worktree-based workflows in this repository.
- Keep every commit atomic. Do not include `_runtime/` or review documents unless the user explicitly asks.

## Spec Coverage Self-Review

- Stage 1B workbench core is covered by Tasks 1 through 9.
- Artifact and ArtifactVersion split is covered by Tasks 1 and 5.
- GenerationTrace first-class recording is covered by Tasks 2, 6, and 9.
- PromptPlan with reserved SceneCast fields is covered by Tasks 3 and 7.
- Frame lock and stale flags are covered by Tasks 4 and 6.
- Candidate image selection is covered by Tasks 5, 6, and 8.
- Frame image regeneration is covered by Task 9.
- Raw parameter migration begins with deprecation metadata in Task 10.
- FlowGram, SaaS, ProviderCapability, and Quality Evaluation are intentionally out of scope for this Stage 1B plan.
