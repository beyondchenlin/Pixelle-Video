from pathlib import Path

import pytest

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository


def _demo_spec() -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="preset-demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(),
        metadata={},
    )


def _asset_spec(ref: str) -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="preset-demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(
            TemplateLayer(
                id="image-1",
                type="image",
                name="Image",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=1,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="asset", ref=ref),
                style={},
            ),
        ),
        metadata={},
    )


def _thumbnail_key(repo: TemplatePresetRepository, tmp_path: Path, preset_id: str) -> str:
    source_path = tmp_path / f"{preset_id}.png"
    source_path.write_bytes(b"thumbnail")
    return repo.persist_thumbnail(source_path=source_path, preset_id=preset_id)


def test_repository_saves_loads_and_touches_last_used(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-demo"),
    )

    repo.save(preset)
    loaded = repo.get("user-demo")
    repo.touch_last_used("user-demo", "2026-05-02T09:30:00Z")

    assert loaded is not None
    assert loaded.name == "My Demo"
    assert repo.get("user-demo").last_used_at == "2026-05-02T09:30:00Z"
    assert (tmp_path / "presets.json").exists()


def test_repository_delete_removes_preset_without_affecting_others(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    first = TemplatePreset(
        preset_id="user-first",
        name="First",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-first"),
    )
    second = TemplatePreset(
        preset_id="user-second",
        name="Second",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=LayeredTemplateSpec.from_dict(
            {**_demo_spec().to_dict(), "template_id": "preset-second", "template_name": "Second"}
        ),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-second"),
    )

    repo.save(first)
    repo.save(second)

    assert repo.delete("user-first") is True
    assert repo.delete("user-missing") is False
    assert repo.get("user-first") is None
    assert repo.get("user-second") is not None
    assert [preset.preset_id for preset in repo.list_all()] == ["user-second"]


def test_repository_rejects_asset_layers_without_repository_keys(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_asset_spec("C:/temp/demo.png"),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-demo"),
    )

    with pytest.raises(ValueError, match="asset layers must reference repository asset keys"):
        repo.save(preset)


def test_repository_rejects_missing_repository_asset_key(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_asset_spec("assets/user_demo/missing.png"),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-demo"),
    )

    with pytest.raises(ValueError, match="asset key does not exist"):
        repo.save(preset)


def test_repository_rejects_asset_key_path_traversal(tmp_path: Path):
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"outside")
    repo = TemplatePresetRepository(root=tmp_path / "repo")
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_asset_spec("assets/../../outside.png"),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-demo"),
    )

    with pytest.raises(ValueError, match="asset key does not exist"):
        repo.save(preset)


def test_repository_persist_asset_copies_file_into_repository(tmp_path: Path):
    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"png-bytes")
    repo = TemplatePresetRepository(root=tmp_path / "repo")

    storage_key = repo.persist_asset(source_path=source_path, preset_id="user:demo")
    copied_path = repo.root / storage_key

    assert storage_key.startswith("assets/user_demo/")
    assert copied_path.exists()
    assert copied_path.read_bytes() == b"png-bytes"


def test_repository_persist_thumbnail_copies_file_into_repository(tmp_path: Path):
    source_path = tmp_path / "thumbnail.png"
    source_path.write_bytes(b"thumbnail-bytes")
    repo = TemplatePresetRepository(root=tmp_path / "repo")

    storage_key = repo.persist_thumbnail(source_path=source_path, preset_id="user:demo")
    copied_path = repo.root / storage_key

    assert storage_key.startswith("thumbnails/user_demo/")
    assert copied_path.exists()
    assert copied_path.read_bytes() == b"thumbnail-bytes"


def test_repository_rejects_user_preset_without_persisted_thumbnail(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
    )

    with pytest.raises(ValueError, match="user presets must reference persisted thumbnails"):
        repo.save(preset)


def test_repository_rejects_missing_repository_thumbnail_key(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
        thumbnail_ref="thumbnails/user_demo/missing.png",
    )

    with pytest.raises(ValueError, match="thumbnail key does not exist"):
        repo.save(preset)


def test_repository_rejects_thumbnail_key_path_traversal(tmp_path: Path):
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"outside")
    repo = TemplatePresetRepository(root=tmp_path / "repo")
    preset = TemplatePreset(
        preset_id="user-demo",
        name="My Demo",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
        thumbnail_ref="thumbnails/../../outside.png",
    )

    with pytest.raises(ValueError, match="thumbnail key does not exist"):
        repo.save(preset)


def test_repository_list_recent_sorts_by_last_used_descending(tmp_path: Path):
    repo = TemplatePresetRepository(root=tmp_path)
    first = TemplatePreset(
        preset_id="user-first",
        name="First",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_demo_spec(),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-first"),
    )
    second = TemplatePreset(
        preset_id="user-second",
        name="Second",
        source="user",
        orientation="portrait",
        template_type="image",
        spec=LayeredTemplateSpec.from_dict(
            {**_demo_spec().to_dict(), "template_id": "preset-second", "template_name": "Second"}
        ),
        thumbnail_ref=_thumbnail_key(repo, tmp_path, "user-second"),
    )

    repo.save(first)
    repo.save(second)
    repo.touch_last_used("user-first", "2026-05-02T09:00:00Z")
    repo.touch_last_used("user-second", "2026-05-02T10:00:00Z")

    assert [preset.preset_id for preset in repo.list_recent(limit=5)] == [
        "user-second",
        "user-first",
    ]
