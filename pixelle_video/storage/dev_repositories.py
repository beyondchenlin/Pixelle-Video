from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pixelle_video.models.artifact import Artifact, ArtifactVersion
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.generation_event import GenerationEvent
from pixelle_video.models.llm_interaction_trace import LLMInteractionTrace
from pixelle_video.models.prompt_plan import PromptPlanBundle
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.models.stale_dependency import DependencyEdge, StaleMark
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.storage.resilient_json_store import (
    load_json_with_quarantine,
    save_json_atomic,
)

JsonPayload = dict[str, object]


def _copy_payload(payload: Mapping[str, object]) -> JsonPayload:
    return deepcopy(dict(payload))


@dataclass
class InMemoryArtifactRepository:
    artifacts: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    versions: dict[tuple[str, str, str], dict[str, object]] = field(default_factory=dict)
    failed_artifacts: list[tuple[str, str, dict[str, object]]] = field(default_factory=list)

    async def create_artifact(
        self,
        workspace_id: str,
        artifact: Mapping[str, object],
    ) -> dict[str, object]:
        payload = Artifact.from_dict(artifact).to_dict()
        if payload["workspace_id"] != workspace_id:
            raise ValueError("artifact workspace_id does not match repository workspace")
        key = (workspace_id, payload["artifact_id"])
        existing = self.artifacts.get(key)
        if existing is not None:
            if existing["frame_id"] != payload["frame_id"] or existing["source_prompt_plan_id"] != payload["source_prompt_plan_id"]:
                raise ValueError("artifact identity conflicts with existing artifact")
            return _copy_payload(existing)
        self.artifacts[key] = _copy_payload(payload)
        return _copy_payload(payload)

    async def create_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version: Mapping[str, object],
    ) -> dict[str, object]:
        payload = ArtifactVersion.from_dict(version).to_dict()
        if payload["workspace_id"] != workspace_id or payload["artifact_id"] != artifact_id:
            raise ValueError("artifact version identity does not match repository request")
        key = (workspace_id, artifact_id, payload["version_id"])
        if key in self.versions:
            raise ValueError("artifact version already exists")
        self.versions[key] = _copy_payload(payload)
        artifact_key = (workspace_id, artifact_id)
        artifact = self.artifacts.get(artifact_key)
        if artifact is not None:
            candidates = list(artifact.get("candidate_version_ids") or [])
            if payload["version_id"] not in candidates:
                candidates.append(payload["version_id"])
            artifact["candidate_version_ids"] = candidates
        return _copy_payload(payload)

    async def select_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version_id: str,
    ) -> dict[str, object]:
        version_key = (workspace_id, artifact_id, version_id)
        if version_key not in self.versions:
            raise ValueError("artifact version was not found")
        artifact_key = (workspace_id, artifact_id)
        artifact = self.artifacts.get(artifact_key)
        if artifact is not None:
            candidates = list(artifact.get("candidate_version_ids") or [])
            if version_id not in candidates:
                candidates.append(version_id)
            artifact["candidate_version_ids"] = candidates
            artifact["selected_version_id"] = version_id
        for (
            stored_workspace_id,
            stored_artifact_id,
            _stored_version_id,
        ), version in self.versions.items():
            if stored_workspace_id == workspace_id and stored_artifact_id == artifact_id:
                version["status"] = "candidate"
        self.versions[version_key]["status"] = "selected"
        return {"artifact_id": artifact_id, "selected_version_id": version_id}

    async def list_artifact_versions(
        self,
        workspace_id: str,
        artifact_id: str,
    ) -> list[dict[str, object]]:
        return [
            _copy_payload(version)
            for (stored_workspace_id, stored_artifact_id, _), version in self.versions.items()
            if stored_workspace_id == workspace_id and stored_artifact_id == artifact_id
        ]

    async def mark_artifact_failed(
        self,
        workspace_id: str,
        artifact_id: str,
        failure: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(failure)
        self.failed_artifacts.append((workspace_id, artifact_id, payload))
        return payload


@dataclass
class InMemoryTraceRepository:
    llm_interactions: list[dict[str, object]] = field(default_factory=list)
    generation_events: list[dict[str, object]] = field(default_factory=list)

    async def append_llm_interaction(
        self,
        workspace_id: str,
        trace: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(trace)
        self.llm_interactions.append({"workspace_id": workspace_id, "trace": payload})
        return payload

    async def list_llm_interactions(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        results = [
            _copy_payload(item["trace"])
            for item in self.llm_interactions
            if item["workspace_id"] == workspace_id
        ]
        active_filters = {str(key): value for key, value in (filters or {}).items() if value is not None}
        if not active_filters:
            return results
        return [
            trace
            for trace in results
            if all(_trace_filter_matches(trace, key, value) for key, value in active_filters.items())
        ]

    async def append_generation_event(
        self,
        workspace_id: str,
        event: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(event)
        self.generation_events.append({"workspace_id": workspace_id, "event": payload})
        return payload

    async def list_generation_events(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        results = [
            _copy_payload(item["event"])
            for item in self.generation_events
            if item["workspace_id"] == workspace_id
        ]
        active_filters = {str(key): value for key, value in (filters or {}).items() if value is not None}
        if not active_filters:
            return results
        return [
            event
            for event in results
            if all(event.get(key) == value for key, value in active_filters.items())
        ]


@dataclass
class InMemoryPromptPlanRepository:
    bundles: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    stale_marks: list[tuple[str, str, dict[str, object]]] = field(default_factory=list)

    async def save_prompt_plan_bundle(
        self,
        workspace_id: str,
        bundle: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(bundle)
        storyboard_id = str(payload.get("storyboard_plan_id") or payload.get("storyboard_id") or "").strip()
        if not storyboard_id:
            prompt_plans = payload.get("prompt_plans")
            if isinstance(prompt_plans, list) and prompt_plans:
                first_plan = prompt_plans[0]
                if isinstance(first_plan, Mapping):
                    storyboard_id = str(first_plan.get("storyboard_plan_id") or "").strip()
        if not storyboard_id:
            raise ValueError("prompt plan bundle must include storyboard identity")
        self.bundles[(workspace_id, storyboard_id)] = payload
        return _copy_payload(payload)

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, object]]:
        bundle = self.bundles.get((workspace_id, storyboard_id))
        if bundle is None:
            return []
        prompt_plans = bundle.get("prompt_plans")
        if not isinstance(prompt_plans, list):
            return []
        return [_copy_payload(plan) for plan in prompt_plans if isinstance(plan, Mapping)]

    async def mark_prompt_plan_stale(
        self,
        workspace_id: str,
        prompt_plan_id: str,
        reason: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        payload = _copy_payload(reason or {})
        payload["prompt_plan_id"] = prompt_plan_id
        self.stale_marks.append((workspace_id, prompt_plan_id, payload))
        return payload


@dataclass
class InMemoryAssetBibleRepository:
    asset_bibles: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)

    async def save_asset_bible(
        self,
        workspace_id: str,
        asset_bible: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(asset_bible)
        self.asset_bibles[(workspace_id, str(payload["asset_bible_id"]))] = payload
        return _copy_payload(payload)

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> dict[str, object] | None:
        payload = self.asset_bibles.get((workspace_id, asset_bible_id))
        return _copy_payload(payload) if payload is not None else None

    async def list_asset_bibles(
        self,
        workspace_id: str,
        project_id: str,
    ) -> list[dict[str, object]]:
        return [
            _copy_payload(payload)
            for (stored_workspace_id, _), payload in self.asset_bibles.items()
            if stored_workspace_id == workspace_id and payload.get("project_id") == project_id
        ]

    async def save_scene_cast(
        self,
        workspace_id: str,
        scene_cast: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(scene_cast)
        self.scene_casts[(workspace_id, str(payload["scene_cast_id"]))] = payload
        return _copy_payload(payload)

    async def load_scene_cast(
        self,
        workspace_id: str,
        scene_cast_id: str,
    ) -> dict[str, object] | None:
        payload = self.scene_casts.get((workspace_id, scene_cast_id))
        return _copy_payload(payload) if payload is not None else None

    async def list_scene_casts(
        self,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> list[dict[str, object]]:
        return [
            _copy_payload(payload)
            for (stored_workspace_id, _), payload in self.scene_casts.items()
            if stored_workspace_id == workspace_id
            and payload.get("project_id") == project_id
            and payload.get("asset_bible_id") == asset_bible_id
        ]

    async def delete_scene_cast(
        self,
        workspace_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> None:
        self.scene_casts.pop((workspace_id, scene_cast_id), None)


@dataclass
class InMemoryDependencyEdgeRepository:
    edges: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)

    async def save_dependency_edge(
        self,
        workspace_id: str,
        edge: Mapping[str, object],
    ) -> dict[str, object]:
        payload = _copy_payload(edge)
        self.edges[(workspace_id, str(payload["edge_id"]))] = payload
        return _copy_payload(payload)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        project_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, object]]:
        return [
            _copy_payload(edge)
            for (stored_workspace_id, _), edge in self.edges.items()
            if stored_workspace_id == workspace_id
            and edge.get("project_id") == project_id
            and edge.get("upstream_type") == upstream_type
            and edge.get("upstream_id") == upstream_id
        ]


@dataclass
class InMemoryStaleMarkRepository:
    marks: dict[tuple[str, str, str, str, str, str, str, str], dict[str, object]] = field(default_factory=dict)

    async def mark_stale(
        self,
        workspace_id: str,
        mark: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        payload = _copy_payload(mark)
        key = (
            workspace_id,
            str(payload["project_id"]),
            str(payload["target_type"]),
            str(payload["target_id"]),
            str(payload["reason_code"]),
            str(payload["upstream_type"]),
            str(payload["upstream_id"]),
            str(payload["upstream_version"]),
        )
        if key in self.marks:
            return _copy_payload(self.marks[key]), False
        self.marks[key] = payload
        return _copy_payload(payload), True

    async def list_stale_marks(
        self,
        workspace_id: str,
        project_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, object]]:
        return [
            _copy_payload(mark)
            for key, mark in self.marks.items()
            if key[0] == workspace_id
            and key[1] == project_id
            and key[2] == target_type
            and key[3] == target_id
        ]


@dataclass
class InMemoryStoryboardWorkbenchStateStore:
    states: dict[tuple[str, str, str], dict[str, object]] = field(default_factory=dict)

    async def load_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
    ) -> dict[str, object] | None:
        payload = self.states.get((workspace_id, storyboard_id, frame_id))
        return _copy_payload(payload) if payload is not None else None

    async def save_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        state: Mapping[str, object],
    ) -> dict[str, object]:
        payload = StoryboardFrameWorkbenchState.from_dict(state).to_dict()
        if payload["frame_id"] != frame_id:
            raise ValueError("workbench state frame_id does not match repository request")
        self.states[(workspace_id, storyboard_id, frame_id)] = payload
        return _copy_payload(payload)


class _JsonFileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, name: str, default: Any) -> Any:
        path = self._path(name)
        return load_json_with_quarantine(path, default)

    def save(self, name: str, payload: Any) -> None:
        path = self._path(name)
        save_json_atomic(path, payload, ensure_ascii=False, indent=2, sort_keys=True)

    def update(self, name: str, default: Any, updater: Callable[[Any], Any]) -> Any:
        payload = self.load(name, default)
        result = updater(payload)
        self.save(name, payload)
        return result

    def _path(self, name: str) -> Path:
        if "/" in name or "\\" in name or name in {"", ".", ".."}:
            raise ValueError("store name must be a local JSON file name")
        return self.root / name


@dataclass
class FilesystemDevArtifactRepository:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def create_artifact(
        self,
        workspace_id: str,
        artifact: Mapping[str, object],
    ) -> JsonPayload:
        payload = Artifact.from_dict(artifact).to_dict()
        if payload["workspace_id"] != workspace_id:
            raise ValueError("artifact workspace_id does not match repository workspace")

        def updater(index: dict[str, Any]) -> JsonPayload:
            artifacts = _payload_map(index, "artifacts")
            key = _artifact_key(workspace_id, payload["artifact_id"])
            existing = artifacts.get(key)
            if isinstance(existing, Mapping):
                if (
                    existing["frame_id"] != payload["frame_id"]
                    or existing["source_prompt_plan_id"] != payload["source_prompt_plan_id"]
                ):
                    raise ValueError("artifact identity conflicts with existing artifact")
                return _copy_payload(existing)
            artifacts[key] = _copy_payload(payload)
            return _copy_payload(payload)

        return self._store.update("artifacts.json", {}, updater)

    async def create_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version: Mapping[str, object],
    ) -> JsonPayload:
        payload = ArtifactVersion.from_dict(version).to_dict()
        if payload["workspace_id"] != workspace_id or payload["artifact_id"] != artifact_id:
            raise ValueError("artifact version identity does not match repository request")

        def updater(index: dict[str, Any]) -> JsonPayload:
            versions = _payload_map(index, "versions")
            key = _artifact_version_key(workspace_id, artifact_id, payload["version_id"])
            if key in versions:
                raise ValueError("artifact version already exists")
            versions[key] = _copy_payload(payload)
            artifacts = _payload_map(index, "artifacts")
            artifact = artifacts.get(_artifact_key(workspace_id, artifact_id))
            if isinstance(artifact, dict):
                candidates = list(artifact.get("candidate_version_ids") or [])
                if payload["version_id"] not in candidates:
                    candidates.append(payload["version_id"])
                artifact["candidate_version_ids"] = candidates
            return _copy_payload(payload)

        return self._store.update("artifacts.json", {}, updater)

    async def select_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version_id: str,
    ) -> JsonPayload:
        def updater(index: dict[str, Any]) -> JsonPayload:
            versions = _payload_map(index, "versions")
            version_key = _artifact_version_key(workspace_id, artifact_id, version_id)
            if version_key not in versions:
                raise ValueError("artifact version was not found")
            artifact = _payload_map(index, "artifacts").get(
                _artifact_key(workspace_id, artifact_id),
            )
            if isinstance(artifact, dict):
                candidates = list(artifact.get("candidate_version_ids") or [])
                if version_id not in candidates:
                    candidates.append(version_id)
                artifact["candidate_version_ids"] = candidates
                artifact["selected_version_id"] = version_id
            key_prefix = f"{workspace_id}\t{artifact_id}\t"
            for key, version in versions.items():
                if key.startswith(key_prefix) and isinstance(version, dict):
                    version["status"] = "candidate"
            versions[version_key]["status"] = "selected"
            return {"artifact_id": artifact_id, "selected_version_id": version_id}

        return self._store.update("artifacts.json", {}, updater)

    async def list_artifact_versions(
        self,
        workspace_id: str,
        artifact_id: str,
    ) -> list[JsonPayload]:
        index = self._store.load("artifacts.json", {})
        versions = _payload_map(index, "versions")
        prefix = f"{workspace_id}\t{artifact_id}\t"
        return [
            _copy_payload(ArtifactVersion.from_dict(version).to_dict())
            for key, version in versions.items()
            if key.startswith(prefix) and isinstance(version, Mapping)
        ]

    async def mark_artifact_failed(
        self,
        workspace_id: str,
        artifact_id: str,
        failure: Mapping[str, object],
    ) -> JsonPayload:
        payload = _copy_payload(failure)

        def updater(index: dict[str, Any]) -> JsonPayload:
            failures = index.setdefault("failed_artifacts", [])
            if not isinstance(failures, list):
                raise ValueError("failed_artifacts store must be a list")
            failures.append(
                {
                    "workspace_id": workspace_id,
                    "artifact_id": artifact_id,
                    "failure": payload,
                },
            )
            return payload

        return self._store.update("artifacts.json", {}, updater)


@dataclass
class FilesystemDevTraceRepository:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def append_llm_interaction(
        self,
        workspace_id: str,
        trace: Mapping[str, object],
    ) -> JsonPayload:
        payload = LLMInteractionTrace.from_dict(trace).to_dict()

        def updater(index: dict[str, Any]) -> JsonPayload:
            interactions = _payload_list(index, "llm_interactions")
            interactions.append({"workspace_id": workspace_id, "trace": payload})
            return _copy_payload(payload)

        return self._store.update("traces.json", {}, updater)

    async def list_llm_interactions(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[JsonPayload]:
        index = self._store.load("traces.json", {})
        results = [
            _copy_payload(item["trace"])
            for item in _payload_list(index, "llm_interactions")
            if isinstance(item, Mapping) and item.get("workspace_id") == workspace_id
        ]
        active_filters = {str(key): value for key, value in (filters or {}).items() if value is not None}
        if not active_filters:
            return results
        return [
            trace
            for trace in results
            if all(_trace_filter_matches(trace, key, value) for key, value in active_filters.items())
        ]

    async def append_generation_event(
        self,
        workspace_id: str,
        event: Mapping[str, object],
    ) -> JsonPayload:
        payload = GenerationEvent.from_dict(event).to_dict()

        def updater(index: dict[str, Any]) -> JsonPayload:
            events = _payload_list(index, "generation_events")
            events.append({"workspace_id": workspace_id, "event": payload})
            return _copy_payload(payload)

        return self._store.update("traces.json", {}, updater)

    async def list_generation_events(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[JsonPayload]:
        index = self._store.load("traces.json", {})
        results = [
            _copy_payload(item["event"])
            for item in _payload_list(index, "generation_events")
            if isinstance(item, Mapping) and item.get("workspace_id") == workspace_id
        ]
        active_filters = {str(key): value for key, value in (filters or {}).items() if value is not None}
        if not active_filters:
            return results
        return [
            event
            for event in results
            if all(event.get(key) == value for key, value in active_filters.items())
        ]


@dataclass
class FilesystemDevPromptPlanRepository:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def save_prompt_plan_bundle(
        self,
        workspace_id: str,
        bundle: Mapping[str, object],
    ) -> JsonPayload:
        payload = PromptPlanBundle.from_dict(bundle).to_dict()
        storyboard_id = _resolve_prompt_plan_storyboard_id(payload)

        def updater(index: dict[str, Any]) -> JsonPayload:
            _payload_map(index, "bundles")[_prompt_plan_bundle_key(workspace_id, storyboard_id)] = payload
            return _copy_payload(payload)

        return self._store.update("prompt_plans.json", {}, updater)

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[JsonPayload]:
        index = self._store.load("prompt_plans.json", {})
        bundle = _payload_map(index, "bundles").get(
            _prompt_plan_bundle_key(workspace_id, storyboard_id),
        )
        if not isinstance(bundle, Mapping):
            return []
        prompt_plans = bundle.get("prompt_plans")
        if not isinstance(prompt_plans, list):
            return []
        return [_copy_payload(plan) for plan in prompt_plans if isinstance(plan, Mapping)]

    async def mark_prompt_plan_stale(
        self,
        workspace_id: str,
        prompt_plan_id: str,
        reason: Mapping[str, object] | None = None,
    ) -> JsonPayload:
        payload = _copy_payload(reason or {})
        payload["prompt_plan_id"] = prompt_plan_id

        def updater(index: dict[str, Any]) -> JsonPayload:
            marks = _payload_list(index, "stale_marks")
            marks.append(
                {
                    "workspace_id": workspace_id,
                    "prompt_plan_id": prompt_plan_id,
                    "reason": payload,
                },
            )
            return _copy_payload(payload)

        return self._store.update("prompt_plans.json", {}, updater)


@dataclass
class FilesystemDevAssetBibleRepository:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def save_asset_bible(
        self,
        workspace_id: str,
        asset_bible: Mapping[str, object],
    ) -> JsonPayload:
        payload = AssetBible.from_dict(asset_bible).to_dict()
        if payload["workspace_id"] != workspace_id:
            raise ValueError("asset bible workspace_id does not match repository workspace")

        def updater(index: dict[str, Any]) -> JsonPayload:
            _payload_map(index, "asset_bibles")[
                _asset_bible_key(workspace_id, payload["asset_bible_id"])
            ] = payload
            return _copy_payload(payload)

        return self._store.update("assets.json", {}, updater)

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> JsonPayload | None:
        index = self._store.load("assets.json", {})
        payload = _payload_map(index, "asset_bibles").get(
            _asset_bible_key(workspace_id, asset_bible_id),
        )
        return _copy_payload(payload) if isinstance(payload, Mapping) else None

    async def list_asset_bibles(
        self,
        workspace_id: str,
        project_id: str,
    ) -> list[JsonPayload]:
        index = self._store.load("assets.json", {})
        return [
            _copy_payload(payload)
            for key, payload in _payload_map(index, "asset_bibles").items()
            if key.startswith(f"{workspace_id}\t")
            and isinstance(payload, Mapping)
            and payload.get("project_id") == project_id
        ]

    async def save_scene_cast(
        self,
        workspace_id: str,
        scene_cast: Mapping[str, object],
    ) -> JsonPayload:
        payload = SceneCast.from_dict(scene_cast).to_dict()
        if payload["workspace_id"] != workspace_id:
            raise ValueError("scene cast workspace_id does not match repository workspace")

        def updater(index: dict[str, Any]) -> JsonPayload:
            _payload_map(index, "scene_casts")[
                _scene_cast_key(workspace_id, payload["scene_cast_id"])
            ] = payload
            return _copy_payload(payload)

        return self._store.update("assets.json", {}, updater)

    async def load_scene_cast(
        self,
        workspace_id: str,
        scene_cast_id: str,
    ) -> JsonPayload | None:
        index = self._store.load("assets.json", {})
        payload = _payload_map(index, "scene_casts").get(
            _scene_cast_key(workspace_id, scene_cast_id),
        )
        return _copy_payload(payload) if isinstance(payload, Mapping) else None

    async def list_scene_casts(
        self,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> list[JsonPayload]:
        index = self._store.load("assets.json", {})
        return [
            _copy_payload(payload)
            for key, payload in _payload_map(index, "scene_casts").items()
            if key.startswith(f"{workspace_id}\t")
            and isinstance(payload, Mapping)
            and payload.get("project_id") == project_id
            and payload.get("asset_bible_id") == asset_bible_id
        ]

    async def delete_scene_cast(
        self,
        workspace_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> None:
        def updater(index: dict[str, Any]) -> None:
            _payload_map(index, "scene_casts").pop(
                _scene_cast_key(workspace_id, scene_cast_id), None
            )

        self._store.update("assets.json", {}, updater)


@dataclass
class FilesystemDevDependencyEdgeRepository:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def save_dependency_edge(
        self,
        workspace_id: str,
        edge: Mapping[str, object],
    ) -> JsonPayload:
        payload = DependencyEdge.from_dict(edge).to_dict()
        if payload["workspace_id"] != workspace_id:
            raise ValueError("dependency edge workspace_id does not match repository workspace")

        def updater(index: dict[str, Any]) -> JsonPayload:
            _payload_map(index, "edges")[_dependency_edge_key(workspace_id, payload["edge_id"])] = payload
            return _copy_payload(payload)

        return self._store.update("dependencies.json", {}, updater)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        project_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[JsonPayload]:
        index = self._store.load("dependencies.json", {})
        return [
            _copy_payload(edge)
            for key, edge in _payload_map(index, "edges").items()
            if key.startswith(f"{workspace_id}\t")
            and isinstance(edge, Mapping)
            and edge.get("project_id") == project_id
            and edge.get("upstream_type") == upstream_type
            and edge.get("upstream_id") == upstream_id
        ]


@dataclass
class FilesystemDevStaleMarkRepository:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def mark_stale(
        self,
        workspace_id: str,
        mark: Mapping[str, object],
    ) -> tuple[JsonPayload, bool]:
        payload = StaleMark.from_dict(mark).to_dict()
        if payload["workspace_id"] != workspace_id:
            raise ValueError("stale mark workspace_id does not match repository workspace")
        key = _stale_mark_key(payload)

        def updater(index: dict[str, Any]) -> tuple[JsonPayload, bool]:
            marks = _payload_map(index, "marks")
            existing = marks.get(key)
            if isinstance(existing, Mapping):
                return _copy_payload(existing), False
            marks[key] = payload
            return _copy_payload(payload), True

        return self._store.update("stale_marks.json", {}, updater)

    async def list_stale_marks(
        self,
        workspace_id: str,
        project_id: str,
        target_type: str,
        target_id: str,
    ) -> list[JsonPayload]:
        index = self._store.load("stale_marks.json", {})
        return [
            _copy_payload(mark)
            for key, mark in _payload_map(index, "marks").items()
            if key.startswith(f"{workspace_id}\t{project_id}\t{target_type}\t{target_id}\t")
            and isinstance(mark, Mapping)
        ]


@dataclass
class FilesystemDevStoryboardWorkbenchStateStore:
    root: str | Path

    def __post_init__(self) -> None:
        self._store = _JsonFileStore(self.root)

    async def load_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
    ) -> JsonPayload | None:
        index = self._store.load("storyboard_workbench_states.json", {})
        payload = _payload_map(index, "states").get(
            _frame_state_key(workspace_id, storyboard_id, frame_id),
        )
        return _copy_payload(payload) if isinstance(payload, Mapping) else None

    async def save_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        state: Mapping[str, object],
    ) -> JsonPayload:
        payload = StoryboardFrameWorkbenchState.from_dict(state).to_dict()
        if payload["frame_id"] != frame_id:
            raise ValueError("workbench state frame_id does not match repository request")

        def updater(index: dict[str, Any]) -> JsonPayload:
            _payload_map(index, "states")[_frame_state_key(workspace_id, storyboard_id, frame_id)] = payload
            return _copy_payload(payload)

        return self._store.update("storyboard_workbench_states.json", {}, updater)


def _payload_map(index: dict[str, Any], name: str) -> dict[str, Any]:
    payload = index.setdefault(name, {})
    if not isinstance(payload, dict):
        raise ValueError(f"{name} store must be a mapping")
    return payload


def _payload_list(index: dict[str, Any], name: str) -> list[Any]:
    payload = index.setdefault(name, [])
    if not isinstance(payload, list):
        raise ValueError(f"{name} store must be a list")
    return payload


def _artifact_key(workspace_id: str, artifact_id: object) -> str:
    return f"{workspace_id}\t{artifact_id}"


def _artifact_version_key(workspace_id: str, artifact_id: str, version_id: object) -> str:
    return f"{workspace_id}\t{artifact_id}\t{version_id}"


def _prompt_plan_bundle_key(workspace_id: str, storyboard_id: str) -> str:
    return f"{workspace_id}\t{storyboard_id}"


def _asset_bible_key(workspace_id: str, asset_bible_id: object) -> str:
    return f"{workspace_id}\t{asset_bible_id}"


def _scene_cast_key(workspace_id: str, scene_cast_id: object) -> str:
    return f"{workspace_id}\t{scene_cast_id}"


def _dependency_edge_key(workspace_id: str, edge_id: object) -> str:
    return f"{workspace_id}\t{edge_id}"


def _frame_state_key(workspace_id: str, storyboard_id: str, frame_id: str) -> str:
    return f"{workspace_id}\t{storyboard_id}\t{frame_id}"


def _stale_mark_key(payload: Mapping[str, object]) -> str:
    return "\t".join(
        str(payload[field_name])
        for field_name in (
            "workspace_id",
            "project_id",
            "target_type",
            "target_id",
            "reason_code",
            "upstream_type",
            "upstream_id",
            "upstream_version",
        )
    )


def _resolve_prompt_plan_storyboard_id(payload: Mapping[str, object]) -> str:
    storyboard_id = str(payload.get("storyboard_plan_id") or payload.get("storyboard_id") or "").strip()
    if not storyboard_id:
        prompt_plans = payload.get("prompt_plans")
        if isinstance(prompt_plans, list) and prompt_plans:
            first_plan = prompt_plans[0]
            if isinstance(first_plan, Mapping):
                storyboard_id = str(first_plan.get("storyboard_plan_id") or "").strip()
    if not storyboard_id:
        raise ValueError("prompt plan bundle must include storyboard identity")
    return storyboard_id


def _trace_filter_matches(trace: Mapping[str, Any], key: str, value: object) -> bool:
    if trace.get(key) == value:
        return True
    context = trace.get("context")
    return isinstance(context, Mapping) and context.get(key) == value


__all__ = [
    "FilesystemDevArtifactRepository",
    "FilesystemDevAssetBibleRepository",
    "FilesystemDevDependencyEdgeRepository",
    "FilesystemDevPromptPlanRepository",
    "FilesystemDevStaleMarkRepository",
    "FilesystemDevStoryboardWorkbenchStateStore",
    "FilesystemDevTraceRepository",
    "InMemoryArtifactRepository",
    "InMemoryAssetBibleRepository",
    "InMemoryDependencyEdgeRepository",
    "InMemoryPromptPlanRepository",
    "InMemoryStaleMarkRepository",
    "InMemoryStoryboardWorkbenchStateStore",
    "InMemoryTraceRepository",
]
