from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.routers.health import HealthResponse
from api.runtime_context import build_api_runtime_context, get_api_runtime_context
from pixelle_video.utils.configured_path import resolve_configured_path
from pixelle_video.utils.project_identity import (
    build_path_id,
    build_project_root_id,
    is_launch_id,
    is_path_id,
    is_project_root_id,
    new_launch_id,
)


def test_project_root_id_is_stable_for_equivalent_paths(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()

    assert build_project_root_id(tmp_path) == build_project_root_id(nested / "..")


def test_project_root_id_distinguishes_different_roots(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert build_project_root_id(first) != build_project_root_id(second)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "invalid",
        "pixelle-root-v1:" + ("g" * 64),
        "pixelle-root-v1:" + ("0" * 63),
        "pixelle-root-v2:" + ("0" * 64),
    ],
)
def test_project_root_id_validation_rejects_malformed_values(value: object) -> None:
    assert is_project_root_id(value) is False


def test_project_root_id_validation_accepts_generated_value(tmp_path: Path) -> None:
    assert is_project_root_id(build_project_root_id(tmp_path)) is True


def test_launch_id_is_unique_and_follows_the_versioned_contract() -> None:
    first = new_launch_id()
    second = new_launch_id()

    assert is_launch_id(first) is True
    assert is_launch_id(second) is True
    assert first != second


@pytest.mark.parametrize(
    "value",
    [None, "", "invalid", "pixelle-launch-v1:" + ("0" * 31)],
)
def test_launch_id_validation_rejects_malformed_values(value: object) -> None:
    assert is_launch_id(value) is False


def test_configured_path_id_supports_a_not_yet_created_target(tmp_path: Path) -> None:
    target = tmp_path / "not-created" / "output"

    assert is_path_id(build_path_id(target)) is True
    assert not target.exists()


def test_configured_path_id_rejects_cwd_dependent_relative_paths() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        build_path_id("output")


def test_project_root_id_rejects_missing_or_non_directory_roots(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("content", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        build_project_root_id(tmp_path / "missing")
    with pytest.raises(NotADirectoryError):
        build_project_root_id(file_path)


def test_api_runtime_distinguishes_checkout_code_from_configured_project_data(
    tmp_path: Path,
) -> None:
    checkout_root = tmp_path / "checkout"
    project_root = tmp_path / "project-data"
    checkout_root.mkdir()
    project_root.mkdir()

    context = build_api_runtime_context(project_root, checkout_root=checkout_root)

    assert context.checkout_root == checkout_root
    assert context.project_root == project_root
    assert context.checkout_root_id != context.project_root_id


def test_api_runtime_rejects_an_invalid_launch_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PIXELLE_LAUNCH_ID"):
        build_api_runtime_context(tmp_path, checkout_root=tmp_path, launch_id="invalid")


def test_relative_configured_paths_are_anchored_to_project_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    unrelated_cwd = tmp_path / "unrelated"
    project_root.mkdir()
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    resolved = resolve_configured_path(
        "output/custom",
        project_root=project_root,
        setting_name="TEST_PATH",
    )

    assert resolved == project_root / "output" / "custom"
    assert not (unrelated_cwd / "output").exists()


def test_configured_paths_preserve_absolute_storage_and_reject_relative_escape(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    external_root = tmp_path / "external"
    project_root.mkdir()

    assert resolve_configured_path(
        external_root,
        project_root=project_root,
        setting_name="TEST_PATH",
    ) == external_root
    with pytest.raises(ValueError, match="inside the project root"):
        resolve_configured_path(
            "../escape",
            project_root=project_root,
            setting_name="TEST_PATH",
        )


def test_api_runtime_resolves_custom_output_root_without_creating_it(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    checkout_root = tmp_path / "checkout"
    external_output = tmp_path / "external" / "output"
    project_root.mkdir()
    checkout_root.mkdir()

    context = build_api_runtime_context(
        project_root,
        checkout_root=checkout_root,
        output_root=external_output,
    )

    assert context.output_root == external_output
    assert is_path_id(context.output_root_id) is True
    assert not external_output.exists()


def test_health_exposes_only_opaque_runtime_fingerprints() -> None:
    context = get_api_runtime_context()
    payload = HealthResponse().model_dump()
    serialized = json.dumps(payload)

    assert payload["checkout_root_id"] == context.checkout_root_id
    assert payload["project_root_id"] == context.project_root_id
    assert payload["output_root_id"] == context.output_root_id
    assert payload["launch_id"] == context.launch_id
    assert is_project_root_id(payload["checkout_root_id"]) is True
    assert is_project_root_id(payload["project_root_id"]) is True
    assert is_path_id(payload["output_root_id"]) is True
    assert str(context.checkout_root) not in serialized
    assert str(context.project_root) not in serialized
