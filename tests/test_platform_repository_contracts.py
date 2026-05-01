import inspect
from os import PathLike
from typing import Mapping

import pytest

import pixelle_video.repositories.artifacts as artifacts
import pixelle_video.repositories.assets as assets
import pixelle_video.repositories.prompt_plans as prompt_plans
import pixelle_video.repositories.trace as trace
from pixelle_video.storage.artifact_object_store import FilesystemDevArtifactObjectStore


def assert_protocol_exposes_async_methods(protocol: type, method_names: set[str]) -> None:
    for method_name in method_names:
        assert hasattr(protocol, method_name)
        assert inspect.iscoroutinefunction(getattr(protocol, method_name))


def assert_signature(
    method: object,
    parameter_names: list[str],
    parameter_annotations: dict[str, object],
    return_annotation: object,
) -> None:
    signature = inspect.signature(method)

    assert list(signature.parameters) == parameter_names
    for parameter_name, annotation in parameter_annotations.items():
        assert signature.parameters[parameter_name].annotation == annotation
    assert signature.return_annotation == return_annotation


def test_repository_protocols_expose_required_methods():
    assert_protocol_exposes_async_methods(
        trace.TraceRepository,
        {
            "append_llm_interaction",
            "list_llm_interactions",
            "append_generation_event",
            "list_generation_events",
        },
    )
    assert_protocol_exposes_async_methods(
        artifacts.ArtifactRepository,
        {
            "create_artifact",
            "create_artifact_version",
            "select_artifact_version",
            "list_artifact_versions",
            "mark_artifact_failed",
        },
    )
    assert_protocol_exposes_async_methods(
        artifacts.ArtifactObjectStore,
        {
            "put_file",
            "get_file_url",
            "exists",
        },
    )
    assert_protocol_exposes_async_methods(
        assets.AssetBibleRepository,
        {
            "save_asset_bible",
            "load_asset_bible",
            "list_asset_bibles",
            "save_scene_cast",
            "load_scene_cast",
            "list_scene_casts",
        },
    )
    assert_protocol_exposes_async_methods(
        prompt_plans.PromptPlanRepository,
        {
            "save_prompt_plan_bundle",
            "load_prompt_plans_by_storyboard",
            "mark_prompt_plan_stale",
        },
    )


def test_repository_protocols_expose_required_signatures():
    assert_signature(
        trace.TraceRepository.append_llm_interaction,
        ["self", "workspace_id", "trace"],
        {"trace": Mapping[str, object]},
        dict[str, object],
    )
    assert_signature(
        trace.TraceRepository.list_llm_interactions,
        ["self", "workspace_id", "filters"],
        {"filters": Mapping[str, object] | None},
        list[dict[str, object]],
    )
    assert_signature(
        artifacts.ArtifactRepository.create_artifact,
        ["self", "workspace_id", "artifact"],
        {"artifact": Mapping[str, object]},
        dict[str, object],
    )
    assert_signature(
        artifacts.ArtifactRepository.create_artifact_version,
        ["self", "workspace_id", "artifact_id", "version"],
        {"version": Mapping[str, object]},
        dict[str, object],
    )
    assert_signature(
        artifacts.ArtifactObjectStore.put_file,
        ["self", "workspace_id", "source_path", "metadata"],
        {
            "source_path": str | PathLike[str],
            "metadata": Mapping[str, object] | None,
        },
        artifacts.StoredArtifactFile,
    )
    assert_signature(
        assets.AssetBibleRepository.save_asset_bible,
        ["self", "workspace_id", "asset_bible"],
        {"asset_bible": Mapping[str, object]},
        dict[str, object],
    )
    assert_signature(
        assets.AssetBibleRepository.list_asset_bibles,
        ["self", "workspace_id", "project_id"],
        {},
        list[dict[str, object]],
    )
    assert_signature(
        assets.AssetBibleRepository.list_scene_casts,
        ["self", "workspace_id", "project_id", "asset_bible_id"],
        {},
        list[dict[str, object]],
    )
    assert_signature(
        prompt_plans.PromptPlanRepository.save_prompt_plan_bundle,
        ["self", "workspace_id", "bundle"],
        {"bundle": Mapping[str, object]},
        dict[str, object],
    )


def test_artifact_object_store_result_contract_requires_storage_key():
    stored_file = artifacts.StoredArtifactFile(storage_key="artifacts/workspace/file.png")

    assert stored_file.storage_key == "artifacts/workspace/file.png"
    assert stored_file.url is None


@pytest.mark.asyncio
async def test_filesystem_dev_artifact_object_store_uses_storage_keys_and_urls(tmp_path):
    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"png")
    store = FilesystemDevArtifactObjectStore(
        root=tmp_path / "objects",
        base_url="https://cdn.example.test/assets",
    )

    stored_file = await store.put_file("workspace_1", source_path)

    assert stored_file.storage_key.startswith("artifacts/workspace_1/")
    assert stored_file.storage_key.endswith(".png")
    assert "\\" not in stored_file.storage_key
    assert str(tmp_path) not in stored_file.storage_key
    assert stored_file.url == f"https://cdn.example.test/assets/{stored_file.storage_key}"
    assert await store.exists(stored_file.storage_key) is True
    assert await store.get_file_url(stored_file.storage_key) == stored_file.url


@pytest.mark.asyncio
async def test_filesystem_dev_artifact_object_store_uses_single_extension_and_default_url(tmp_path):
    source_path = tmp_path / "source.preview.png"
    source_path.write_bytes(b"png")
    store = FilesystemDevArtifactObjectStore(root=tmp_path / "objects")

    with pytest.raises(ValueError, match="extension"):
        await store.put_file("workspace_1", source_path)

    safe_source_path = tmp_path / "source.png"
    safe_source_path.write_bytes(b"png")
    stored_file = await store.put_file("workspace_1", safe_source_path)

    assert stored_file.storage_key.count(".") == 1
    assert stored_file.url == f"/{stored_file.storage_key}"
    assert await store.get_file_url(stored_file.storage_key) == stored_file.url


@pytest.mark.asyncio
async def test_filesystem_dev_artifact_object_store_rejects_missing_local_file_uri(tmp_path):
    store = FilesystemDevArtifactObjectStore(root=tmp_path / "objects")
    missing_key = "artifacts/workspace_1/0123456789abcdef0123456789abcdef.png"

    with pytest.raises(FileNotFoundError, match="artifact object was not found"):
        await store.get_local_file_uri(missing_key)


@pytest.mark.asyncio
async def test_filesystem_dev_artifact_object_store_rejects_invalid_keys(tmp_path):
    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"png")
    store = FilesystemDevArtifactObjectStore(root=tmp_path / "objects", base_url="/api/files")

    with pytest.raises(ValueError, match="workspace_id"):
        await store.put_file("../escape", source_path)

    for storage_key in [
        "../escape.png",
        "/artifacts/workspace/file.png",
        "artifacts/workspace/../file.png",
        "artifacts/workspace/file.png/extra",
        "artifacts/workspace/C:\\temp\\file.png",
        "output/workspace/file.png",
    ]:
        with pytest.raises(ValueError, match="artifact storage key"):
            await store.get_file_url(storage_key)
        assert await store.exists(storage_key) is False
