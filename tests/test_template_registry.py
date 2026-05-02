from pathlib import Path

import pytest

from pixelle_video.models.layered_template import (
    LAYERED_TEMPLATE_VERSION,
    LayeredTemplateSpec,
    RectSpec,
)
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository
from pixelle_video.services.template_registry import TemplateRegistry


def _user_spec(template_id: str, name: str) -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version=LAYERED_TEMPLATE_VERSION,
        template_id=template_id,
        template_name=name,
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=0, y=0, width=1080, height=1920),
        layers=(),
        metadata={"source_kind": "user"},
    )


def _user_preset(preset_id: str, name: str) -> TemplatePreset:
    return TemplatePreset(
        preset_id=preset_id,
        name=name,
        source="user",
        orientation="portrait",
        template_type="image",
        spec=_user_spec(preset_id, name),
    )


def _write_template(root: Path, relative_path: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html></html>", encoding="utf-8")


def test_registry_merges_system_and_user_presets_into_single_card_shape(tmp_path: Path):
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "1080x1920/image_default.html")
    repository = TemplatePresetRepository(tmp_path / "repository")
    user = repository.save(_user_preset("user:demo", "User Demo"))
    registry = TemplateRegistry(
        preset_repository=repository,
        templates_root=templates_root,
    )

    presets = registry.list_all()

    assert all(isinstance(preset, TemplatePreset) for preset in presets)
    assert [preset.source for preset in presets] == ["system", "user"]
    assert presets[1] == user


def test_registry_builds_complete_non_editable_spec_for_legacy_system_templates(
    tmp_path: Path,
):
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "1920x1080/image_landscape_minimal.html")
    registry = TemplateRegistry(
        preset_repository=TemplatePresetRepository(tmp_path / "repository"),
        templates_root=templates_root,
    )

    [preset] = registry.list_system()

    assert preset.editable is False
    assert preset.spec is not None
    assert preset.spec.layers == ()
    assert preset.spec.version == LAYERED_TEMPLATE_VERSION
    assert preset.spec.template_id == preset.preset_id
    assert preset.spec.metadata["source_kind"] == "legacy_html"
    assert (
        preset.spec.metadata["legacy_template_path"]
        == "1920x1080/image_landscape_minimal.html"
    )
    assert preset.orientation == "landscape"
    assert preset.template_type == "image"
    assert (preset.spec.canvas_width, preset.spec.canvas_height) == (1920, 1080)


def test_registry_recent_returns_touched_user_presets_only_with_limit(
    tmp_path: Path,
):
    repository = TemplatePresetRepository(tmp_path / "repository")
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "1080x1920/image_default.html")
    for index in range(6):
        repository.save(_user_preset(f"user:{index}", f"User {index}"))
        repository.touch_last_used(f"user:{index}")
    registry = TemplateRegistry(
        preset_repository=repository,
        templates_root=templates_root,
    )

    recent = registry.list_recent(limit=3)

    assert [preset.preset_id for preset in recent] == ["user:5", "user:4", "user:3"]
    assert {preset.source for preset in recent} == {"recent"}


def test_registry_mark_used_updates_user_preset_but_noops_for_system_preset(
    tmp_path: Path,
):
    repository = TemplatePresetRepository(tmp_path / "repository")
    user = repository.save(_user_preset("user:demo", "User Demo"))
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "1080x1920/image_default.html")
    registry = TemplateRegistry(
        preset_repository=repository,
        templates_root=templates_root,
    )
    system = registry.list_system()[0]

    assert user.last_used_at is None
    registry.mark_used(system.preset_id)
    assert repository.get(user.preset_id).last_used_at is None

    registry.mark_used(user.preset_id)
    assert repository.get(user.preset_id).last_used_at is not None


def test_registry_get_returns_system_or_user_preset(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path / "repository")
    user = repository.save(_user_preset("user:demo", "User Demo"))
    templates_root = tmp_path / "templates"
    _write_template(templates_root, "1080x1920/image_default.html")
    registry = TemplateRegistry(
        preset_repository=repository,
        templates_root=templates_root,
    )
    system = registry.list_system()[0]

    assert registry.get(system.preset_id) == system
    assert registry.get(user.preset_id) == user

    with pytest.raises(KeyError):
        registry.get("missing")
