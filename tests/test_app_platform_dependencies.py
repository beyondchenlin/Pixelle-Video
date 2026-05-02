from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from api.config import APIConfig


def test_dev_platform_dependencies_mount_workbench_services_and_repositories(tmp_path):
    from api.platform_dependencies import configure_platform_dependencies
    from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService
    from pixelle_video.storage.dev_repositories import InMemoryStoryboardWorkbenchStateStore

    app = FastAPI()
    dependencies = configure_platform_dependencies(
        app,
        APIConfig(runtime_profile="dev", artifact_base_path=str(tmp_path / "output")),
    )

    assert app.state.artifact_repository is dependencies.artifact_repository
    assert app.state.artifact_object_store is dependencies.artifact_object_store
    assert app.state.trace_repository is dependencies.trace_repository
    assert app.state.prompt_plan_repository is dependencies.prompt_plan_repository
    assert app.state.asset_bible_repository is dependencies.asset_bible_repository
    assert app.state.dependency_edge_repository is dependencies.dependency_edge_repository
    assert app.state.stale_mark_repository is dependencies.stale_mark_repository
    assert isinstance(app.state.storyboard_workbench_state_store, InMemoryStoryboardWorkbenchStateStore)
    assert isinstance(app.state.storyboard_workbench_service, StoryboardWorkbenchService)


def test_platform_dependencies_reject_missing_production_repository_adapters(tmp_path):
    from api.platform_dependencies import configure_platform_dependencies

    app = FastAPI()

    with pytest.raises(RuntimeError, match="production repository adapters are not implemented"):
        configure_platform_dependencies(
            app,
            APIConfig(
                runtime_profile="production",
                task_backend="postgres",
                postgres_dsn="postgresql+asyncpg://u:p@db:5432/pixelle",
                redis_url="redis://redis:6379/0",
                artifact_backend="s3",
                artifact_object_store_endpoint_url="https://s3.example.test",
                artifact_object_store_bucket="pixelle-prod",
                artifact_base_path=str(tmp_path / "output"),
            ),
        )


def test_platform_dependencies_attach_same_objects_to_core(tmp_path):
    from api.platform_dependencies import configure_platform_dependencies
    from pixelle_video.service import PixelleVideoCore

    app = FastAPI()
    core = PixelleVideoCore()
    dependencies = configure_platform_dependencies(
        app,
        APIConfig(runtime_profile="dev", artifact_base_path=str(tmp_path / "output")),
        core=core,
    )

    for attr_name in (
        "artifact_repository",
        "artifact_object_store",
        "trace_repository",
        "prompt_plan_repository",
        "storyboard_workbench_state_store",
    ):
        assert getattr(core, attr_name) is getattr(dependencies, attr_name)

    assert Path(tmp_path / "output" / "_objects").is_dir()


def test_api_app_lifespan_mounts_storyboard_workbench_dependencies(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import api.app as api_app
    import api.dependencies as dependencies_module

    monkeypatch.setattr(api_app.api_config, "artifact_base_path", str(tmp_path / "output"))
    dependencies_module._platform_dependencies = None

    with TestClient(api_app.app) as client:
        assert hasattr(client.app.state, "storyboard_workbench_service")
        assert hasattr(client.app.state, "storyboard_workbench_state_store")
        assert hasattr(client.app.state, "artifact_repository")
        assert dependencies_module.get_or_create_platform_dependencies().artifact_repository is (
            client.app.state.artifact_repository
        )
        assert dependencies_module.get_or_create_platform_dependencies().artifact_object_store is (
            client.app.state.artifact_object_store
        )


def test_in_memory_artifact_repository_keeps_single_selected_version():
    from pixelle_video.models.artifact import Artifact, ArtifactVersion
    from pixelle_video.storage.dev_repositories import InMemoryArtifactRepository

    async def run_scenario():
        repository = InMemoryArtifactRepository()
        await repository.create_artifact(
            "workspace_1",
            Artifact(
                artifact_id="artifact_1",
                workspace_id="workspace_1",
                artifact_type="storyboard_frame_image",
                frame_id="frame_1",
                source_prompt_plan_id="prompt_1",
            ).to_dict(),
        )
        for version_id in ("version_1", "version_2"):
            await repository.create_artifact_version(
                "workspace_1",
                "artifact_1",
                ArtifactVersion(
                    version_id=version_id,
                    artifact_id="artifact_1",
                    workspace_id="workspace_1",
                    frame_id="frame_1",
                    source_prompt_plan_id="prompt_1",
                    storage_key=f"artifacts/workspace_1/{version_id}.png",
                    status="candidate",
                ).to_dict(),
            )

        await repository.select_artifact_version("workspace_1", "artifact_1", "version_1")
        await repository.select_artifact_version("workspace_1", "artifact_1", "version_2")

        return await repository.list_artifact_versions("workspace_1", "artifact_1")

    import asyncio

    versions = asyncio.run(run_scenario())
    statuses = {version["version_id"]: version["status"] for version in versions}

    assert statuses == {"version_1": "candidate", "version_2": "selected"}
