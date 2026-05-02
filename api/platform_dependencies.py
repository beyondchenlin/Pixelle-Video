from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from api.config import APIConfig
from pixelle_video.services.artifact_dependency_integration import (
    ArtifactDependencyWriteService,
)
from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService
from pixelle_video.storage.artifact_object_store import FilesystemDevArtifactObjectStore
from pixelle_video.storage.dev_repositories import (
    FilesystemDevArtifactRepository,
    FilesystemDevAssetBibleRepository,
    FilesystemDevDependencyEdgeRepository,
    FilesystemDevPromptPlanRepository,
    FilesystemDevStaleMarkRepository,
    FilesystemDevStoryboardWorkbenchStateStore,
    FilesystemDevTraceRepository,
)


@dataclass(frozen=True)
class PlatformDependencies:
    artifact_repository: FilesystemDevArtifactRepository
    artifact_object_store: FilesystemDevArtifactObjectStore
    trace_repository: FilesystemDevTraceRepository
    prompt_plan_repository: FilesystemDevPromptPlanRepository
    asset_bible_repository: FilesystemDevAssetBibleRepository
    dependency_edge_repository: FilesystemDevDependencyEdgeRepository
    stale_mark_repository: FilesystemDevStaleMarkRepository
    storyboard_workbench_state_store: FilesystemDevStoryboardWorkbenchStateStore
    storyboard_workbench_service: StoryboardWorkbenchService


def configure_platform_dependencies(
    app: FastAPI,
    config: APIConfig,
    *,
    core: Any | None = None,
) -> PlatformDependencies:
    dependencies = build_platform_dependencies(config)
    attach_platform_dependencies(app.state, dependencies)
    if core is not None:
        attach_platform_dependencies(core, dependencies)
    return dependencies


def build_platform_dependencies(config: APIConfig) -> PlatformDependencies:
    if config.runtime_profile == "production":
        raise RuntimeError("production repository adapters are not implemented")
    platform_root = f"{config.artifact_base_path}/_platform"
    artifact_repository = FilesystemDevArtifactRepository(f"{platform_root}/artifacts")
    artifact_object_store = FilesystemDevArtifactObjectStore(
        root=f"{config.artifact_base_path}/_objects",
        base_url=config.artifact_base_url,
    )
    trace_repository = FilesystemDevTraceRepository(f"{platform_root}/traces")
    prompt_plan_repository = FilesystemDevPromptPlanRepository(f"{platform_root}/prompt_plans")
    asset_bible_repository = FilesystemDevAssetBibleRepository(f"{platform_root}/assets")
    dependency_edge_repository = FilesystemDevDependencyEdgeRepository(f"{platform_root}/dependencies")
    stale_mark_repository = FilesystemDevStaleMarkRepository(f"{platform_root}/stale_marks")
    storyboard_workbench_state_store = FilesystemDevStoryboardWorkbenchStateStore(
        f"{platform_root}/storyboard_workbench"
    )
    workbench_service = StoryboardWorkbenchService(
        artifact_repository=artifact_repository,
        object_store=artifact_object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=prompt_plan_repository,
        artifact_dependency_service=ArtifactDependencyWriteService(
            edge_repository=dependency_edge_repository,
        ),
    )
    dependencies = PlatformDependencies(
        artifact_repository=artifact_repository,
        artifact_object_store=artifact_object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=prompt_plan_repository,
        asset_bible_repository=asset_bible_repository,
        dependency_edge_repository=dependency_edge_repository,
        stale_mark_repository=stale_mark_repository,
        storyboard_workbench_state_store=storyboard_workbench_state_store,
        storyboard_workbench_service=workbench_service,
    )
    return dependencies


def attach_platform_dependencies(target: Any, dependencies: PlatformDependencies) -> None:
    for attr_name in PlatformDependencies.__dataclass_fields__:
        setattr(target, attr_name, getattr(dependencies, attr_name))


def attach_existing_platform_dependencies(app: FastAPI, core: Any) -> None:
    for attr_name in PlatformDependencies.__dataclass_fields__:
        value = getattr(app.state, attr_name, None)
        if value is not None:
            setattr(core, attr_name, value)


__all__ = [
    "attach_existing_platform_dependencies",
    "PlatformDependencies",
    "attach_platform_dependencies",
    "build_platform_dependencies",
    "configure_platform_dependencies",
]
