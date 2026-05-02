from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from api.config import APIConfig


def test_api_config_defaults_use_non_comfyui_local_port():
    config = APIConfig()

    assert config.port == 8001


def test_platform_context_ignores_blank_api_base_url_env(monkeypatch):
    import importlib

    import pixelle_video.platform_context as platform_context

    monkeypatch.setenv("PIXELLE_API_BASE_URL", "")
    monkeypatch.setenv("PIXELLE_API_PORT", "8011")

    reloaded = importlib.reload(platform_context)
    try:
        assert reloaded.DEFAULT_API_BASE_URL == "http://localhost:8011/api"
    finally:
        monkeypatch.delenv("PIXELLE_API_BASE_URL", raising=False)
        monkeypatch.delenv("PIXELLE_API_PORT", raising=False)
        importlib.reload(platform_context)


def test_dev_platform_dependencies_mount_workbench_services_and_repositories(tmp_path):
    from api.platform_dependencies import configure_platform_dependencies
    from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService
    from pixelle_video.storage.dev_repositories import FilesystemDevStoryboardWorkbenchStateStore

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
    assert isinstance(app.state.storyboard_workbench_state_store, FilesystemDevStoryboardWorkbenchStateStore)
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


def test_web_session_pixelle_video_mounts_storyboard_workbench_dependencies(monkeypatch, tmp_path):
    from api import dependencies as api_dependencies
    from api.config import api_config
    from web.state import session as web_session
    from web.state.async_runtime import shutdown_all_async_runtimes

    monkeypatch.setattr(api_config, "artifact_base_path", str(tmp_path / "output"))
    api_dependencies._platform_dependencies = None
    web_session._PIXELLE_VIDEO_SESSIONS.clear()
    monkeypatch.setattr(web_session, "get_current_session_key", lambda: "test_web_session")
    monkeypatch.setattr(web_session, "register_async_cleanup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(web_session, "session_exists", lambda _session_key: True)

    core = None
    try:
        core = web_session.get_pixelle_video()

        dependencies = api_dependencies.get_or_create_platform_dependencies()
        for attr_name in (
            "artifact_repository",
            "artifact_object_store",
            "trace_repository",
            "prompt_plan_repository",
            "storyboard_workbench_state_store",
            "storyboard_workbench_service",
        ):
            assert getattr(core, attr_name) is getattr(dependencies, attr_name)
    finally:
        if core is not None:
            web_session.run_async(core.cleanup())
        web_session._PIXELLE_VIDEO_SESSIONS.clear()
        shutdown_all_async_runtimes()
        api_dependencies._platform_dependencies = None


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


@pytest.mark.asyncio
async def test_dev_platform_dependencies_share_workbench_artifacts_between_instances(tmp_path):
    from api.platform_dependencies import build_platform_dependencies
    from pixelle_video.models.artifact import Artifact, ArtifactVersion
    from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState

    config = APIConfig(runtime_profile="dev", artifact_base_path=str(tmp_path / "output"))
    writer = build_platform_dependencies(config)
    reader = build_platform_dependencies(config)

    await writer.artifact_repository.create_artifact(
        "workspace_1",
        Artifact(
            artifact_id="artifact_1",
            workspace_id="workspace_1",
            artifact_type="storyboard_frame_image",
            frame_id="frame_1",
            source_prompt_plan_id="prompt_1",
        ).to_dict(),
    )
    await writer.artifact_repository.create_artifact_version(
        "workspace_1",
        "artifact_1",
        ArtifactVersion(
            version_id="version_1",
            artifact_id="artifact_1",
            workspace_id="workspace_1",
            frame_id="frame_1",
            source_prompt_plan_id="prompt_1",
            storage_key="artifacts/workspace_1/0123456789abcdef0123456789abcdef.png",
            status="selected",
        ).to_dict(),
    )
    await writer.storyboard_workbench_state_store.save_frame_state(
        "workspace_1",
        "storyboard_1",
        "frame_1",
        StoryboardFrameWorkbenchState(
            frame_id="frame_1",
            prompt_plan_id="prompt_1",
            selected_image_artifact_id="artifact_1",
            selected_image_version_id="version_1",
            candidate_image_version_ids=("version_1",),
        ).to_dict(),
    )

    versions = await reader.artifact_repository.list_artifact_versions(
        "workspace_1",
        "artifact_1",
    )
    assert len(versions) == 1
    version = versions[0]
    assert isinstance(version.pop("created_at"), str)
    assert version == {
        "version_id": "version_1",
        "artifact_id": "artifact_1",
        "workspace_id": "workspace_1",
        "frame_id": "frame_1",
        "source_prompt_plan_id": "prompt_1",
        "storage_key": "artifacts/workspace_1/0123456789abcdef0123456789abcdef.png",
        "status": "selected",
        "provider": None,
        "provider_metadata": {},
        "width": None,
        "height": None,
        "trace_event_id": None,
        "metadata": {},
    }
    state = await reader.storyboard_workbench_state_store.load_frame_state(
        "workspace_1",
        "storyboard_1",
        "frame_1",
    )
    assert state is not None
    assert state["selected_image_artifact_id"] == "artifact_1"
    assert state["selected_image_version_id"] == "version_1"

    object_path = (
        tmp_path
        / "output"
        / "_objects"
        / "artifacts"
        / "workspace_1"
        / "0123456789abcdef0123456789abcdef.png"
    )
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"png")
    candidates = await reader.storyboard_workbench_service.list_image_candidates(
        workspace_id="workspace_1",
        artifact_id="artifact_1",
    )

    assert len(candidates) == 1
    assert candidates[0].version_id == "version_1"
    assert candidates[0].url == (
        "/api/files/artifacts/workspace_1/0123456789abcdef0123456789abcdef.png"
    )
