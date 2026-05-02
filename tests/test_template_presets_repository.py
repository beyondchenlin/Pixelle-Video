import json
from pathlib import Path

import pytest

from pixelle_video.models.layered_template import (
    LAYERED_TEMPLATE_VERSION,
    LayerSourceSpec,
    LayeredTemplateSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository


def _spec(
    *,
    template_id: str = "user-demo",
    name: str = "User Demo",
    layers: tuple[TemplateLayer, ...] = (),
) -> LayeredTemplateSpec:
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
        layers=layers,
        metadata={"source_kind": "user"},
    )


def _preset(
    preset_id: str = "user:demo",
    *,
    name: str = "User Demo",
    spec: LayeredTemplateSpec | None = None,
) -> TemplatePreset:
    return TemplatePreset(
        preset_id=preset_id,
        name=name,
        source="user",
        orientation="portrait",
        template_type="image",
        spec=spec or _spec(template_id=preset_id, name=name),
    )


def test_repository_saves_reads_and_lists_json_backed_presets(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    preset = _preset()

    saved = repository.save(preset)
    loaded = repository.get("user:demo")

    assert loaded == saved
    assert repository.list_all() == [saved]
    assert saved.created_at is not None
    assert saved.updated_at is not None
    manifest = json.loads((tmp_path / "presets.json").read_text(encoding="utf-8"))
    assert manifest["presets"][0]["preset_id"] == "user:demo"
    assert manifest["presets"][0]["spec"]["version"] == LAYERED_TEMPLATE_VERSION


def test_repository_touch_last_used_updates_recent_order_and_limit(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    for index in range(6):
        repository.save(_preset(f"user:{index}", name=f"Preset {index}"))

    for index in range(6):
        repository.touch_last_used(f"user:{index}")

    recent = repository.list_recent(limit=5)

    assert [preset.preset_id for preset in recent] == [
        "user:5",
        "user:4",
        "user:3",
        "user:2",
        "user:1",
    ]
    assert all(preset.last_used_at is not None for preset in recent)


def test_repository_touch_unknown_preset_raises_key_error(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)

    with pytest.raises(KeyError):
        repository.touch_last_used("system:1080x1920/image_default.html")


def test_repository_persists_assets_under_repository_owned_key(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    source = tmp_path / "uploads" / "Cover Image.PNG"
    source.parent.mkdir()
    source.write_bytes(b"image-bytes")

    key = repository.persist_asset(source, "user:Demo Preset")

    assert key.startswith("assets/user_Demo_Preset/")
    assert key.endswith(".PNG")
    assert "/" in key
    assert (tmp_path / Path(key)).read_bytes() == b"image-bytes"


def test_repository_rejects_asset_layers_not_owned_by_repository(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    layer = TemplateLayer(
        id="image-1",
        type="image",
        name="Image",
        rect=RectSpec(x=0, y=0, width=100, height=100),
        z_index=1,
        opacity=1.0,
        rotation=0.0,
        locked=False,
        source=LayerSourceSpec(kind="asset", ref="C:/tmp/source.png"),
        style={},
    )

    with pytest.raises(ValueError, match="assets/"):
        repository.save(_preset(spec=_spec(layers=(layer,))))


def test_repository_accepts_repository_owned_asset_refs(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    layer = TemplateLayer(
        id="image-1",
        type="image",
        name="Image",
        rect=RectSpec(x=0, y=0, width=100, height=100),
        z_index=1,
        opacity=1.0,
        rotation=0.0,
        locked=False,
        source=LayerSourceSpec(kind="asset", ref="assets/user_demo/source.png"),
        style={},
    )

    saved = repository.save(_preset(spec=_spec(layers=(layer,))))

    assert saved.spec.layers[0].source.ref == "assets/user_demo/source.png"
