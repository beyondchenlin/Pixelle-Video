# Stage 1B Stale Dependency Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-backed Stage 1B stale propagation mechanism that records public-ID dependency edges and idempotently marks downstream SceneCast, PromptPlan, image artifact, video segment, and final video objects stale when upstream AssetBible, SceneCast, or PromptPlan versions change.

**Architecture:** Add small immutable domain models for dependency edges and stale marks, repository protocols for edge lookup and idempotent stale writes, and a focused propagation service that contains no FastAPI, filesystem, provider, or Stage 2 projection persistence logic. The service accepts explicit upstream change events, resolves downstream public-ID edges, writes auditable stale marks, and returns a deterministic propagation summary.

**Tech Stack:** Python dataclasses, repository Protocols, pytest, existing Pixelle domain model conventions, existing public ID validation patterns.

---

## Planning Authority

This plan implements the Stage 1B stale mechanism only. It is governed by:

- `docs/superpowers/specs/2026-05-01-stage1b-stale-dependency-propagation-design.md`
- `docs/pixelle_video_full_planning_md/14_ARTIFACT_TRACE_REGENERATION_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md`
- `docs/superpowers/specs/2026-05-01-stage2-prompt-plan-projection-design.md`
- `docs/superpowers/plans/2026-05-01-stage2-prompt-plan-projection-implementation.md`

Repository rule for this implementation:

```text
Keep changes atomic and narrow. Use Chinese commit messages when committing during implementation. Do not mix Stage 2 projection persistence, main generation provider routing, or unrelated UI changes into this branch of work.
```

## File Structure

- Create `pixelle_video/models/stale_dependency.py`: immutable `DependencyEdge`, `StaleMark`, `UpstreamChangeEvent`, and `StalePropagationSummary` models with public-ID and path/URL rejection.
- Create `tests/test_stale_dependency_models.py`: model contract tests for round trips, immutability, timestamp/version fields, and blocked local path / URL / workflow path values.
- Create `pixelle_video/repositories/stale_dependencies.py`: `DependencyEdgeRepository` and `StaleMarkRepository` protocols.
- Create `tests/test_stale_dependency_repository_contract.py`: in-memory fake repository behavior tests proving idempotent stale writes.
- Create `pixelle_video/services/stale_dependency_propagation.py`: propagation service and typed errors.
- Create `tests/test_stale_dependency_propagation.py`: service TDD tests for AssetBible, SceneCast, PromptPlan propagation, lock semantics, idempotency, and audit fields.
- Modify `pixelle_video/repositories/artifacts.py`: add `mark_artifact_stale()` only if the implementation chooses artifact repository compatibility in addition to `StaleMarkRepository`; the preferred path is to keep artifact stale in `StaleMarkRepository`.
- Modify `pixelle_video/repositories/prompt_plans.py`: keep existing `mark_prompt_plan_stale()` as compatibility; do not make the propagation service depend on this single-type method.

## Task 1: Stale Dependency Domain Models

**Files:**
- Create: `pixelle_video/models/stale_dependency.py`
- Test: `tests/test_stale_dependency_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_stale_dependency_models.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.stale_dependency import (
    DependencyEdge,
    StaleMark,
    StalePropagationSummary,
    UpstreamChangeEvent,
)


def test_dependency_edge_round_trips_with_public_ids_only():
    edge = DependencyEdge(
        edge_id="dep_edge_001",
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_3",
        downstream_type="scene_cast",
        downstream_id="cast_frame_0001",
        relation="scene_cast.references_asset_bible",
        metadata={"storyboard_plan_id": "storyboard_plan_1", "frame_id": "frame_0001"},
    )

    payload = edge.to_dict()

    assert DependencyEdge.from_dict(payload) == edge
    assert payload["upstream_id"] == "bible_demo"
    assert payload["downstream_id"] == "cast_frame_0001"
    assert "D:\\" not in str(payload)
    assert "workflows/" not in str(payload)
    assert "https://" not in str(payload)
    with pytest.raises(FrozenInstanceError):
        edge.downstream_id = "changed"
    with pytest.raises(TypeError):
        edge.metadata["frame_id"] = "changed"


def test_stale_mark_records_reason_upstream_version_and_timestamp():
    mark = StaleMark(
        stale_id="stale_001",
        workspace_id="workspace_1",
        target_type="prompt_plan",
        target_id="prompt_plan_001",
        reason_code="scene_cast_changed",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_4",
        marked_at="2026-05-01T10:03:00Z",
        metadata={"lock_policy": "locked_prompt"},
    )

    payload = mark.to_dict()

    assert StaleMark.from_dict(payload) == mark
    assert payload["reason_code"] == "scene_cast_changed"
    assert payload["upstream_version"] == "scene_cast_rev_4"
    assert payload["marked_at"] == "2026-05-01T10:03:00Z"
    assert payload["metadata"] == {"lock_policy": "locked_prompt"}


def test_upstream_change_event_rejects_non_public_identity_values():
    with pytest.raises(ValueError, match="public ID"):
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="asset_bible",
            upstream_id=r"D:\demo1\Pixelle\bible.json",
            upstream_version="asset_bible_rev_4",
            reason_code="asset_bible_changed",
        )

    with pytest.raises(ValueError, match="public ID"):
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="https://provider.example/jobs/123",
            reason_code="prompt_plan_changed",
        )


def test_dependency_edge_rejects_workflow_path_as_public_contract():
    with pytest.raises(ValueError, match="public ID"):
        DependencyEdge(
            edge_id="dep_edge_bad",
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_1",
            downstream_type="image_artifact",
            downstream_id="workflows/selfhost/storyboard.json",
            relation="image_artifact.generated_from_prompt_plan",
        )


def test_dependency_edge_rejects_relative_path_as_public_contract():
    with pytest.raises(ValueError, match="public ID"):
        DependencyEdge(
            edge_id="dep_edge_bad",
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_1",
            downstream_type="image_artifact",
            downstream_id="output/frame_0001.png",
            relation="image_artifact.generated_from_prompt_plan",
        )


def test_summary_counts_are_non_negative_and_round_trip():
    summary = StalePropagationSummary(
        workspace_id="workspace_1",
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_4",
        visited_edge_count=3,
        stale_created_count=2,
        stale_existing_count=1,
        marked_target_ids=("cast_frame_0001", "prompt_plan_001"),
    )

    assert StalePropagationSummary.from_dict(summary.to_dict()) == summary

    with pytest.raises(ValueError, match="non-negative"):
        StalePropagationSummary(
            workspace_id="workspace_1",
            upstream_type="asset_bible",
            upstream_id="bible_demo",
            upstream_version="asset_bible_rev_4",
            visited_edge_count=-1,
            stale_created_count=0,
            stale_existing_count=0,
        )
```

- [ ] **Step 2: Run model tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_models.py
```

Expected: FAIL because `pixelle_video.models.stale_dependency` does not exist.

- [ ] **Step 3: Implement the model module**

Create `pixelle_video/models/stale_dependency.py` with immutable dataclasses:

```python
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any


ALLOWED_DEPENDENCY_TYPES = {
    "asset_bible",
    "scene_cast",
    "prompt_plan",
    "image_artifact",
    "video_segment",
    "final_video",
}


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DependencyEdge:
    edge_id: str
    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    downstream_type: str
    downstream_id: str
    relation: str
    created_at: str = field(default_factory=utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", _public_id("edge_id", self.edge_id))
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _public_id("project_id", self.project_id))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "downstream_type", _dependency_type("downstream_type", self.downstream_type))
        object.__setattr__(self, "downstream_id", _public_id("downstream_id", self.downstream_id))
        object.__setattr__(self, "relation", _relation("relation", self.relation))
        object.__setattr__(self, "created_at", _required_text("created_at", self.created_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "downstream_type": self.downstream_type,
            "downstream_id": self.downstream_id,
            "relation": self.relation,
            "created_at": self.created_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DependencyEdge":
        _require_mapping("DependencyEdge", payload)
        return cls(
            edge_id=payload.get("edge_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            downstream_type=payload.get("downstream_type", ""),
            downstream_id=payload.get("downstream_id", ""),
            relation=payload.get("relation", ""),
            created_at=payload.get("created_at", ""),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class StaleMark:
    stale_id: str
    workspace_id: str
    target_type: str
    target_id: str
    reason_code: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    marked_at: str = field(default_factory=utc_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "stale_id", _public_id("stale_id", self.stale_id))
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "target_type", _dependency_type("target_type", self.target_type))
        object.__setattr__(self, "target_id", _public_id("target_id", self.target_id))
        object.__setattr__(self, "reason_code", _relation("reason_code", self.reason_code))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "marked_at", _required_text("marked_at", self.marked_at))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stale_id": self.stale_id,
            "workspace_id": self.workspace_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason_code": self.reason_code,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "marked_at": self.marked_at,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StaleMark":
        _require_mapping("StaleMark", payload)
        return cls(
            stale_id=payload.get("stale_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            target_type=payload.get("target_type", ""),
            target_id=payload.get("target_id", ""),
            reason_code=payload.get("reason_code", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            marked_at=payload.get("marked_at", ""),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class UpstreamChangeEvent:
    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _public_id("project_id", self.project_id))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "reason_code", _relation("reason_code", self.reason_code))

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UpstreamChangeEvent":
        _require_mapping("UpstreamChangeEvent", payload)
        return cls(
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            reason_code=payload.get("reason_code", ""),
        )


@dataclass(frozen=True)
class StalePropagationSummary:
    workspace_id: str
    upstream_type: str
    upstream_id: str
    upstream_version: str
    visited_edge_count: int
    stale_created_count: int
    stale_existing_count: int
    marked_target_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_id", _public_id("workspace_id", self.workspace_id))
        object.__setattr__(self, "upstream_type", _dependency_type("upstream_type", self.upstream_type))
        object.__setattr__(self, "upstream_id", _public_id("upstream_id", self.upstream_id))
        object.__setattr__(self, "upstream_version", _public_id("upstream_version", self.upstream_version))
        object.__setattr__(self, "visited_edge_count", _non_negative("visited_edge_count", self.visited_edge_count))
        object.__setattr__(self, "stale_created_count", _non_negative("stale_created_count", self.stale_created_count))
        object.__setattr__(self, "stale_existing_count", _non_negative("stale_existing_count", self.stale_existing_count))
        object.__setattr__(
            self,
            "marked_target_ids",
            tuple(_public_id("marked_target_id", target_id) for target_id in self.marked_target_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "upstream_version": self.upstream_version,
            "visited_edge_count": self.visited_edge_count,
            "stale_created_count": self.stale_created_count,
            "stale_existing_count": self.stale_existing_count,
            "marked_target_ids": list(self.marked_target_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StalePropagationSummary":
        _require_mapping("StalePropagationSummary", payload)
        return cls(
            workspace_id=payload.get("workspace_id", ""),
            upstream_type=payload.get("upstream_type", ""),
            upstream_id=payload.get("upstream_id", ""),
            upstream_version=payload.get("upstream_version", ""),
            visited_edge_count=payload.get("visited_edge_count", 0),
            stale_created_count=payload.get("stale_created_count", 0),
            stale_existing_count=payload.get("stale_existing_count", 0),
            marked_target_ids=tuple(payload.get("marked_target_ids") or ()),
        )


def _require_mapping(name: str, payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(f"{name} payload must be a mapping")


def _required_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _public_id(field_name: str, value: object) -> str:
    text = _required_text(field_name, value)
    lowered = text.lower()
    if (
        ":\\" in text
        or "://" in text
        or "\\" in text
        or "/" in text
        or text.startswith("/")
        or ".." in text
        or lowered.startswith("workflows/")
    ):
        raise ValueError(f"{field_name} must be a public ID, not a path, URL, or workflow path")
    return text


def _dependency_type(field_name: str, value: object) -> str:
    text = _required_text(field_name, value)
    if text not in ALLOWED_DEPENDENCY_TYPES:
        raise ValueError(f"{field_name} must be one of {sorted(ALLOWED_DEPENDENCY_TYPES)}")
    return text


def _relation(field_name: str, value: object) -> str:
    text = _required_text(field_name, value)
    if ":" in text or "/" in text or "\\" in text or ".." in text:
        raise ValueError(f"{field_name} must be a safe relation or reason code")
    return text


def _non_negative(field_name: str, value: object) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(_json_safe_copy(value))


def _json_safe_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(value))
```

- [ ] **Step 4: Run model tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_models.py
```

Expected: all tests in `tests/test_stale_dependency_models.py` pass.

- [ ] **Step 5: Commit model task**

Example commit for the later implementation session:

```powershell
git add pixelle_video/models/stale_dependency.py tests/test_stale_dependency_models.py
git commit -m "feat: 建立 stale 依赖领域模型"
```

## Task 2: Repository Protocols And Idempotent Contract

**Files:**
- Create: `pixelle_video/repositories/stale_dependencies.py`
- Test: `tests/test_stale_dependency_repository_contract.py`

- [ ] **Step 1: Write the repository contract tests**

Create `tests/test_stale_dependency_repository_contract.py`:

```python
from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.stale_dependency import DependencyEdge, StaleMark
from pixelle_video.repositories.stale_dependencies import (
    DependencyEdgeRepository,
    StaleMarkRepository,
)


@dataclass
class InMemoryDependencyEdgeRepository:
    edges: list[dict[str, Any]] = field(default_factory=list)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges.append(dict(edge))
        return dict(edge)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, Any]]:
        return [
            edge
            for edge in self.edges
            if edge["workspace_id"] == workspace_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class InMemoryStaleMarkRepository:
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

    async def list_stale_marks(
        self,
        workspace_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, Any]]:
        return [
            mark
            for key, mark in self.marks.items()
            if key[0] == workspace_id and key[1] == target_type and key[2] == target_id
        ]


def test_fake_repositories_satisfy_protocols():
    edge_repository = InMemoryDependencyEdgeRepository()
    stale_repository = InMemoryStaleMarkRepository()

    assert isinstance(edge_repository, DependencyEdgeRepository)
    assert isinstance(stale_repository, StaleMarkRepository)


@pytest.mark.asyncio
async def test_dependency_edge_repository_lists_downstream_edges_by_public_upstream():
    repository = InMemoryDependencyEdgeRepository()
    edge = DependencyEdge(
        edge_id="dep_edge_001",
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_3",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )

    await repository.save_dependency_edge("workspace_1", edge.to_dict())

    assert await repository.list_downstream_edges("workspace_1", "scene_cast", "cast_frame_0001") == [edge.to_dict()]
    assert await repository.list_downstream_edges("workspace_1", "asset_bible", "bible_demo") == []


@pytest.mark.asyncio
async def test_stale_mark_repository_is_idempotent_for_same_reason_and_upstream_version():
    repository = InMemoryStaleMarkRepository()
    mark = StaleMark(
        stale_id="stale_001",
        workspace_id="workspace_1",
        target_type="prompt_plan",
        target_id="prompt_plan_001",
        reason_code="scene_cast_changed",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_4",
        marked_at="2026-05-01T10:03:00Z",
    )

    first, first_created = await repository.mark_stale("workspace_1", mark.to_dict())
    second, second_created = await repository.mark_stale("workspace_1", mark.to_dict())

    assert first == second
    assert first_created is True
    assert second_created is False
    assert len(await repository.list_stale_marks("workspace_1", "prompt_plan", "prompt_plan_001")) == 1
```

- [ ] **Step 2: Run repository tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_repository_contract.py
```

Expected: FAIL because `pixelle_video.repositories.stale_dependencies` does not exist.

- [ ] **Step 3: Implement repository protocols**

Create `pixelle_video/repositories/stale_dependencies.py`:

```python
from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class DependencyEdgeRepository(Protocol):
    async def save_dependency_edge(
        self,
        workspace_id: str,
        edge: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, object]]:
        raise NotImplementedError


@runtime_checkable
class StaleMarkRepository(Protocol):
    async def mark_stale(
        self,
        workspace_id: str,
        mark: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        raise NotImplementedError

    async def list_stale_marks(
        self,
        workspace_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, object]]:
        raise NotImplementedError
```

The boolean returned by `mark_stale()` must mean `created`: `True` for a new audit record and `False` for an idempotent existing record.

- [ ] **Step 4: Run repository tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_repository_contract.py
```

Expected: all tests in `tests/test_stale_dependency_repository_contract.py` pass.

- [ ] **Step 5: Commit repository task**

Example commit for the later implementation session:

```powershell
git add pixelle_video/repositories/stale_dependencies.py tests/test_stale_dependency_repository_contract.py
git commit -m "feat: 增加 stale 依赖仓储契约"
```

## Task 3: Propagation Service For AssetBible And SceneCast Changes

**Files:**
- Create: `pixelle_video/services/stale_dependency_propagation.py`
- Test: `tests/test_stale_dependency_propagation.py`

- [ ] **Step 1: Write service tests for AssetBible and SceneCast propagation**

Create `tests/test_stale_dependency_propagation.py` with repository fakes from Task 2 and these tests:

```python
from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.stale_dependency import DependencyEdge, UpstreamChangeEvent
from pixelle_video.services.stale_dependency_propagation import (
    StaleDependencyPropagationService,
)


@dataclass
class InMemoryDependencyEdgeRepository:
    edges: list[dict[str, Any]] = field(default_factory=list)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges.append(dict(edge))
        return dict(edge)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, Any]]:
        return [
            edge
            for edge in self.edges
            if edge["workspace_id"] == workspace_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class InMemoryStaleMarkRepository:
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

    async def list_stale_marks(
        self,
        workspace_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, Any]]:
        return [
            mark
            for key, mark in self.marks.items()
            if key[0] == workspace_id and key[1] == target_type and key[2] == target_id
        ]


async def seed_edge(repository: InMemoryDependencyEdgeRepository, **overrides: Any) -> None:
    payload = {
        "edge_id": f"dep_edge_{len(repository.edges) + 1}",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "upstream_type": "asset_bible",
        "upstream_id": "bible_demo",
        "upstream_version": "asset_bible_rev_3",
        "downstream_type": "scene_cast",
        "downstream_id": "cast_frame_0001",
        "relation": "scene_cast.references_asset_bible",
    }
    payload.update(overrides)
    await repository.save_dependency_edge("workspace_1", DependencyEdge(**payload).to_dict())


@pytest.mark.asyncio
async def test_asset_bible_change_marks_scene_cast_prompt_plan_and_image_artifact_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(edges)
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_2",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="asset_bible",
            upstream_id="bible_demo",
            upstream_version="asset_bible_rev_4",
            reason_code="asset_bible_changed",
        )
    )

    assert summary.visited_edge_count == 3
    assert summary.stale_created_count == 3
    assert summary.stale_existing_count == 0
    assert set(summary.marked_target_ids) == {
        "cast_frame_0001",
        "prompt_plan_001",
        "image_artifact_001",
    }
    assert stale.marks[
        (
            "workspace_1",
            "prompt_plan",
            "prompt_plan_001",
            "asset_bible_changed_via_scene_cast",
            "asset_bible",
            "bible_demo",
            "asset_bible_rev_4",
        )
    ]["upstream_version"] == "asset_bible_rev_4"


@pytest.mark.asyncio
async def test_scene_cast_change_marks_prompt_plan_and_image_artifact_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_2",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="scene_cast",
            upstream_id="cast_frame_0001",
            upstream_version="scene_cast_rev_3",
            reason_code="scene_cast_changed",
        )
    )

    assert summary.visited_edge_count == 2
    assert summary.stale_created_count == 2
    assert set(summary.marked_target_ids) == {"prompt_plan_001", "image_artifact_001"}


@pytest.mark.asyncio
async def test_direct_edge_on_current_upstream_version_is_not_marked_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_3",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_current",
        relation="prompt_plan.uses_scene_cast",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="scene_cast",
            upstream_id="cast_frame_0001",
            upstream_version="scene_cast_rev_3",
            reason_code="scene_cast_changed",
        )
    )

    assert summary.visited_edge_count == 0
    assert summary.stale_created_count == 0
    assert summary.stale_existing_count == 0
    assert summary.marked_target_ids == ()
    assert stale.marks == {}
```

- [ ] **Step 2: Run service tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py
```

Expected: FAIL because `pixelle_video.services.stale_dependency_propagation` does not exist.

- [ ] **Step 3: Implement propagation service for recursive downstream marking**

Create `pixelle_video/services/stale_dependency_propagation.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from pixelle_video.models.stale_dependency import (
    DependencyEdge,
    StaleMark,
    StalePropagationSummary,
    UpstreamChangeEvent,
)
from pixelle_video.repositories.stale_dependencies import (
    DependencyEdgeRepository,
    StaleMarkRepository,
)


class StaleDependencyPropagationError(ValueError):
    pass


class StaleDependencyRepositoryNotConfiguredError(StaleDependencyPropagationError):
    pass


@dataclass(frozen=True)
class StaleDependencyPropagationService:
    edge_repository: DependencyEdgeRepository | None
    stale_repository: StaleMarkRepository | None

    def __post_init__(self) -> None:
        if self.edge_repository is None:
            raise StaleDependencyRepositoryNotConfiguredError("dependency edge repository is not configured")
        if self.stale_repository is None:
            raise StaleDependencyRepositoryNotConfiguredError("stale mark repository is not configured")

    async def propagate_upstream_change(self, event: UpstreamChangeEvent) -> StalePropagationSummary:
        visited_edge_keys: set[tuple[str, str, str]] = set()
        marked_target_ids: list[str] = []
        created_count = 0
        existing_count = 0
        queue: list[tuple[str, str, str]] = [
            (event.upstream_type, event.upstream_id, event.reason_code)
        ]

        while queue:
            upstream_type, upstream_id, reason_code = queue.pop(0)
            is_direct_event_upstream = upstream_type == event.upstream_type and upstream_id == event.upstream_id
            edges = await self.edge_repository.list_downstream_edges(
                event.workspace_id,
                upstream_type,
                upstream_id,
            )
            for payload in edges:
                edge = DependencyEdge.from_dict(payload)
                edge_key = (edge.upstream_type, edge.upstream_id, edge.downstream_id)
                if edge_key in visited_edge_keys:
                    continue
                if is_direct_event_upstream and edge.upstream_version == event.upstream_version:
                    continue
                visited_edge_keys.add(edge_key)
                mark = StaleMark(
                    stale_id=(
                        f"stale_{edge.downstream_type}_{edge.downstream_id}_"
                        f"{event.upstream_type}_{event.upstream_id}_{event.upstream_version}"
                    ),
                    workspace_id=event.workspace_id,
                    target_type=edge.downstream_type,
                    target_id=edge.downstream_id,
                    reason_code=_reason_for(edge.downstream_type, reason_code),
                    upstream_type=event.upstream_type,
                    upstream_id=event.upstream_id,
                    upstream_version=event.upstream_version,
                    metadata={"via_relation": edge.relation},
                )
                _, created = await self.stale_repository.mark_stale(event.workspace_id, mark.to_dict())
                if created:
                    created_count += 1
                else:
                    existing_count += 1
                marked_target_ids.append(edge.downstream_id)
                queue.append((edge.downstream_type, edge.downstream_id, mark.reason_code))

        return StalePropagationSummary(
            workspace_id=event.workspace_id,
            upstream_type=event.upstream_type,
            upstream_id=event.upstream_id,
            upstream_version=event.upstream_version,
            visited_edge_count=len(visited_edge_keys),
            stale_created_count=created_count,
            stale_existing_count=existing_count,
            marked_target_ids=tuple(dict.fromkeys(marked_target_ids)),
        )
```

Implement `_reason_for()` with explicit mappings:

```python
def _reason_for(downstream_type: str, incoming_reason: str) -> str:
    mapping = {
        ("scene_cast", "asset_bible_changed"): "asset_bible_changed",
        ("prompt_plan", "asset_bible_changed"): "asset_bible_changed_via_scene_cast",
        ("image_artifact", "asset_bible_changed_via_scene_cast"): "asset_bible_changed_via_prompt_plan",
        ("prompt_plan", "scene_cast_changed"): "scene_cast_changed",
        ("image_artifact", "scene_cast_changed"): "scene_cast_changed_via_prompt_plan",
    }
    return mapping.get((downstream_type, incoming_reason), incoming_reason)
```

- [ ] **Step 4: Run AssetBible and SceneCast service tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py
```

Expected: the AssetBible and SceneCast propagation tests pass.

- [ ] **Step 5: Commit propagation task**

Example commit for the later implementation session:

```powershell
git add pixelle_video/services/stale_dependency_propagation.py tests/test_stale_dependency_propagation.py
git commit -m "feat: 实现 stale 依赖传播服务"
```

## Task 4: PromptPlan To Image, Segment, Final Video Propagation

**Files:**
- Modify: `tests/test_stale_dependency_propagation.py`
- Modify: `pixelle_video/services/stale_dependency_propagation.py`

- [ ] **Step 1: Add failing tests for PromptPlan propagation**

Append to `tests/test_stale_dependency_propagation.py`:

```python
@pytest.mark.asyncio
async def test_prompt_plan_change_marks_image_artifact_video_segment_and_final_video_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    await seed_edge(
        edges,
        upstream_type="image_artifact",
        upstream_id="image_artifact_001",
        upstream_version="image_artifact_rev_1",
        downstream_type="video_segment",
        downstream_id="video_segment_001",
        relation="video_segment.uses_image_artifact",
    )
    await seed_edge(
        edges,
        upstream_type="video_segment",
        upstream_id="video_segment_001",
        upstream_version="video_segment_rev_1",
        downstream_type="final_video",
        downstream_id="final_video_001",
        relation="final_video.uses_video_segment",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_6",
            reason_code="prompt_plan_changed",
        )
    )

    assert summary.visited_edge_count == 3
    assert summary.stale_created_count == 3
    assert set(summary.marked_target_ids) == {
        "image_artifact_001",
        "video_segment_001",
        "final_video_001",
    }
    assert stale.marks[
        (
            "workspace_1",
            "video_segment",
            "video_segment_001",
            "prompt_plan_changed_via_image_artifact",
            "prompt_plan",
            "prompt_plan_001",
            "prompt_plan_rev_6",
        )
    ]["reason_code"] == "prompt_plan_changed_via_image_artifact"
    assert stale.marks[
        (
            "workspace_1",
            "final_video",
            "final_video_001",
            "prompt_plan_changed_via_video_segment",
            "prompt_plan",
            "prompt_plan_001",
            "prompt_plan_rev_6",
        )
    ]["reason_code"] == "prompt_plan_changed_via_video_segment"
```

- [ ] **Step 2: Run the new test to verify RED if mappings are incomplete**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py::test_prompt_plan_change_marks_image_artifact_video_segment_and_final_video_stale
```

Expected: FAIL because Task 3 only implemented AssetBible / SceneCast mappings; video segment and final video reasons still fall back to the incoming reason.

- [ ] **Step 3: Complete reason mapping and queue propagation**

Update `_reason_for()` in `pixelle_video/services/stale_dependency_propagation.py` so these mappings are present:

```python
("image_artifact", "prompt_plan_changed"): "prompt_plan_changed"
("video_segment", "prompt_plan_changed"): "prompt_plan_changed_via_image_artifact"
("video_segment", "prompt_plan_changed_via_image_artifact"): "prompt_plan_changed_via_image_artifact"
("final_video", "prompt_plan_changed_via_image_artifact"): "prompt_plan_changed_via_video_segment"
```

Keep the service generic and edge-driven. Do not import HyperFrames, ComfyUI, provider routing, or Stage 2 projection services.

- [ ] **Step 4: Run propagation tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py
```

Expected: all propagation tests pass.

- [ ] **Step 5: Commit PromptPlan propagation task**

Example commit for the later implementation session:

```powershell
git add pixelle_video/services/stale_dependency_propagation.py tests/test_stale_dependency_propagation.py
git commit -m "feat: 支持 PromptPlan stale 下游传播"
```

## Task 5: Lock Semantics And Idempotent Audit

**Files:**
- Modify: `tests/test_stale_dependency_propagation.py`
- Modify: `pixelle_video/services/stale_dependency_propagation.py`

- [ ] **Step 1: Add failing lock and idempotency tests**

Append to `tests/test_stale_dependency_propagation.py`:

```python
@pytest.mark.asyncio
async def test_lock_policy_does_not_block_stale_marking():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
        metadata={"lock_policy": "locked_artifact"},
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_6",
            reason_code="prompt_plan_changed",
        )
    )

    assert summary.stale_created_count == 1
    mark = next(iter(stale.marks.values()))
    assert mark["target_id"] == "image_artifact_001"
    assert mark["metadata"]["lock_policy"] == "locked_artifact"
    assert mark["metadata"]["auto_rewrite_allowed"] is False


@pytest.mark.asyncio
async def test_repeating_same_upstream_version_is_idempotent_and_auditable():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_2",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)
    event = UpstreamChangeEvent(
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_3",
        reason_code="scene_cast_changed",
    )

    first = await service.propagate_upstream_change(event)
    second = await service.propagate_upstream_change(event)

    assert first.stale_created_count == 1
    assert first.stale_existing_count == 0
    assert second.stale_created_count == 0
    assert second.stale_existing_count == 1
    assert len(stale.marks) == 1
    mark = next(iter(stale.marks.values()))
    assert mark["reason_code"] == "scene_cast_changed"
    assert mark["upstream_version"] == "scene_cast_rev_3"
    assert mark["marked_at"].endswith("Z")
```

- [ ] **Step 2: Run lock/idempotency tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py::test_lock_policy_does_not_block_stale_marking tests/test_stale_dependency_propagation.py::test_repeating_same_upstream_version_is_idempotent_and_auditable
```

Expected: FAIL if lock metadata is not copied or idempotent counters are incorrect.

- [ ] **Step 3: Preserve lock metadata without enabling rewrites**

In `StaleDependencyPropagationService`, when building `StaleMark.metadata`, copy `lock_policy` from `edge.metadata` if present and set:

```python
"auto_rewrite_allowed": False
```

Do not add any method that rewrites `PromptPlan`, replaces artifact versions, invokes generation, or mutates selected versions.

- [ ] **Step 4: Run all propagation tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py
```

Expected: all propagation tests pass.

- [ ] **Step 5: Commit lock/idempotency task**

Example commit for the later implementation session:

```powershell
git add pixelle_video/services/stale_dependency_propagation.py tests/test_stale_dependency_propagation.py
git commit -m "feat: 保留 stale 标记的锁定审计语义"
```

## Task 6: Boundary Guard Tests

**Files:**
- Modify: `tests/test_stale_dependency_propagation.py`
- Test: existing Stage 2 projection tests

- [ ] **Step 1: Add boundary assertions**

Append to `tests/test_stale_dependency_propagation.py`:

```python
def test_stale_service_module_does_not_import_stage2_projection_or_provider_routing():
    import inspect
    import pixelle_video.services.stale_dependency_propagation as module

    source = inspect.getsource(module)

    assert "stage2_projection" not in source
    assert "asset_prompt_plan_composer" not in source
    assert "comfyui" not in source.lower()
    assert "provider routing" not in source.lower()
    assert "workflow_path" not in source
    assert "save_prompt_plan_bundle" not in source
```

- [ ] **Step 2: Run boundary tests**

Run:

```powershell
python -m pytest -q tests/test_stale_dependency_propagation.py::test_stale_service_module_does_not_import_stage2_projection_or_provider_routing
```

Expected: PASS. If it fails, remove the Stage 2 projection, provider, workflow, or prompt-plan persistence coupling from the stale service.

- [ ] **Step 3: Re-run Stage 2 projection tests to ensure no coupling regression**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py tests/test_stage2_projection_pipeline_ui.py
```

Expected: all selected Stage 2 projection tests pass. The stale implementation must not require Stage 2 projection persistence or change preview-only behavior.

- [ ] **Step 4: Commit boundary guard task**

Example commit for the later implementation session:

```powershell
git add tests/test_stale_dependency_propagation.py
git commit -m "test: 锁定 stale 机制阶段边界"
```

## Verification Commands

Run targeted tests:

```powershell
python -m pytest -q tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_propagation.py
```

Expected: all Stage 1B stale tests pass.

Run related regression tests:

```powershell
python -m pytest -q tests/test_prompt_plan_model.py tests/test_artifact_models.py tests/test_scene_cast_model.py tests/test_asset_bible_models.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py
```

Expected: existing PromptPlan, Artifact, SceneCast, AssetBible, and Stage 2 projection tests pass.

Run lint on touched Python files:

```powershell
python -m ruff check pixelle_video/models/stale_dependency.py pixelle_video/repositories/stale_dependencies.py pixelle_video/services/stale_dependency_propagation.py tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_propagation.py
```

Expected: no lint errors.

Run boundary search:

```powershell
rg -n "D:\\\\|://|workflows/|workflow_path|provider_url|save_prompt_plan_bundle|stage2_projection|asset_prompt_plan_composer" pixelle_video/models/stale_dependency.py pixelle_video/repositories/stale_dependencies.py pixelle_video/services/stale_dependency_propagation.py tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_propagation.py
```

Expected: only negative test fixtures or boundary assertions contain blocked strings; production code must not expose local paths, workflow paths, provider URLs, Stage 2 projection persistence calls, or provider routing.

## Commit Message Examples

Use Chinese commit messages during implementation:

```powershell
git commit -m "feat: 建立 stale 依赖领域模型"
git commit -m "feat: 增加 stale 依赖仓储契约"
git commit -m "feat: 实现 stale 依赖传播服务"
git commit -m "feat: 支持 PromptPlan stale 下游传播"
git commit -m "feat: 保留 stale 标记的锁定审计语义"
git commit -m "test: 锁定 stale 机制阶段边界"
```

This planning task itself does not commit or push.

## Plan Self-Review

- Spec coverage: AssetBible、SceneCast、PromptPlan 三类上游变更传播均有任务与测试；public ID、lock、幂等、审计和阶段边界均有测试或边界命令覆盖。
- Placeholder scan: 本计划不包含未定占位、待办占位或延后补写占位。
- Type consistency: `DependencyEdge`、`StaleMark`、`UpstreamChangeEvent`、`StalePropagationSummary` 在模型、仓储和服务任务中字段名保持一致。
- Scope control: 计划不接入 Stage 2 projection persistence，不导入 `asset_prompt_plan_composer`，不调用 `save_prompt_plan_bundle()`，不接入 provider routing，不触发生成。
