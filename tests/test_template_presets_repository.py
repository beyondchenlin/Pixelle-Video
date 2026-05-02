import json
import re
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
    thumbnail_ref: str | None = None,
) -> TemplatePreset:
    return TemplatePreset(
        preset_id=preset_id,
        name=name,
        source="user",
        orientation="portrait",
        template_type="image",
        spec=spec or _spec(template_id=preset_id, name=name),
        thumbnail_ref=thumbnail_ref,
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

    assert key.startswith("assets/user_Demo_Preset-")
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


@pytest.mark.parametrize(
    "asset_ref",
    [
        "assets/../outside.png",
        "assets/user_demo/../../outside.png",
        "assets\\user_demo\\source.png",
        "/assets/user_demo/source.png",
    ],
)
def test_repository_rejects_asset_refs_that_escape_repository(
    tmp_path: Path,
    asset_ref: str,
):
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
        source=LayerSourceSpec(kind="asset", ref=asset_ref),
        style={},
    )

    with pytest.raises(ValueError, match="repository-owned"):
        repository.save(_preset(spec=_spec(layers=(layer,))))


def test_repository_rejects_cross_preset_and_dangling_asset_refs(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    source = tmp_path / "upload.png"
    source.write_bytes(b"image")
    owned_key = repository.persist_asset(source, "user:demo")
    cross_preset_key = repository.persist_asset(source, "user:other")
    dangling_key = "assets/user_demo/missing.png"

    for asset_ref in (cross_preset_key, dangling_key):
        layer = TemplateLayer(
            id="image-1",
            type="image",
            name="Image",
            rect=RectSpec(x=0, y=0, width=100, height=100),
            z_index=1,
            opacity=1.0,
            rotation=0.0,
            locked=False,
            source=LayerSourceSpec(kind="asset", ref=asset_ref),
            style={},
        )

        with pytest.raises(ValueError, match="repository-owned"):
            repository.save(_preset("user:demo", spec=_spec(layers=(layer,))))

    assert owned_key.startswith("assets/user_demo-")


def test_repository_asset_namespace_does_not_collide_after_safe_name_normalization(
    tmp_path: Path,
):
    repository = TemplatePresetRepository(tmp_path)
    source = tmp_path / "upload.png"
    source.write_bytes(b"image")
    owner_key = repository.persist_asset(source, "user:a/b")
    colliding_safe_name_key = repository.persist_asset(source, "user:a?b")

    assert Path(owner_key).parent != Path(colliding_safe_name_key).parent

    layer = TemplateLayer(
        id="image-1",
        type="image",
        name="Image",
        rect=RectSpec(x=0, y=0, width=100, height=100),
        z_index=1,
        opacity=1.0,
        rotation=0.0,
        locked=False,
        source=LayerSourceSpec(kind="asset", ref=owner_key),
        style={},
    )

    with pytest.raises(ValueError, match="repository-owned"):
        repository.save(_preset("user:a?b", spec=_spec(layers=(layer,))))


def test_repository_validates_thumbnail_ref_as_repository_owned_asset(
    tmp_path: Path,
):
    repository = TemplatePresetRepository(tmp_path)
    thumbnail = tmp_path / "thumbnail.png"
    thumbnail.write_bytes(b"thumbnail")
    owned_thumbnail = repository.persist_asset(thumbnail, "user:demo")

    saved = repository.save(_preset("user:demo", thumbnail_ref=owned_thumbnail))

    assert saved.thumbnail_ref == owned_thumbnail

    with pytest.raises(ValueError, match="thumbnail_ref"):
        repository.save(_preset("user:bad", thumbnail_ref="assets/../thumbnail.png"))


def test_repository_rejects_invalid_manifest_schema(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    (tmp_path / "presets.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest"):
        repository.list_all()

    (tmp_path / "presets.json").write_text(
        json.dumps({"version": 999, "presets": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest version"):
        repository.list_all()

    (tmp_path / "presets.json").write_text(
        json.dumps({"presets": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest version"):
        repository.list_all()

    (tmp_path / "presets.json").write_text(
        json.dumps({"version": 1, "presets": {}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="presets"):
        repository.list_all()

    (tmp_path / "presets.json").write_text(
        json.dumps({"version": 1}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="presets"):
        repository.list_all()

    (tmp_path / "presets.json").write_text(
        json.dumps({"version": 1, "presets": [{}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="preset record"):
        repository.list_all()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("preset_id", 42),
        ("name", 42),
        ("source", 42),
        ("orientation", 42),
        ("template_type", 42),
        ("thumbnail_ref", 42),
        ("editable", "true"),
        ("created_at", 42),
        ("updated_at", 42),
        ("last_used_at", 42),
    ],
)
def test_repository_rejects_invalid_manifest_preset_record_field_types(
    tmp_path: Path,
    field: str,
    value,
):
    repository = TemplatePresetRepository(tmp_path)
    repository.save(_preset())
    valid_payload = json.loads((tmp_path / "presets.json").read_text(encoding="utf-8"))[
        "presets"
    ][0]
    invalid_payload = {
        **valid_payload,
        field: value,
    }

    (tmp_path / "presets.json").write_text(
        json.dumps({"version": 1, "presets": [invalid_payload]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=field):
        repository.list_all()


def test_repository_rejects_invalid_manifest_preset_record_spec(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    repository.save(_preset())
    valid_payload = json.loads((tmp_path / "presets.json").read_text(encoding="utf-8"))[
        "presets"
    ][0]
    invalid_spec_payload = {
        **valid_payload,
        "spec": {"version": "layered_template.v1"},
    }
    (tmp_path / "presets.json").write_text(
        json.dumps({"version": 1, "presets": [invalid_spec_payload]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="spec"):
        repository.list_all()


def test_repository_rejects_invalid_manifest_nested_spec_field_types(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    layer = TemplateLayer(
        id="title-1",
        type="text",
        name="Title",
        rect=RectSpec(x=0, y=0, width=100, height=50),
        z_index=1,
        opacity=1.0,
        rotation=0.0,
        locked=False,
        source=None,
        style={},
        role="title",
    )
    repository.save(_preset(spec=_spec(layers=(layer,))))
    valid_payload = json.loads((tmp_path / "presets.json").read_text(encoding="utf-8"))[
        "presets"
    ][0]
    cases = [
        ("spec.template_id", lambda spec: spec.__setitem__("template_id", 42)),
        ("spec.canvas_width", lambda spec: spec.__setitem__("canvas_width", "1080")),
        ("spec.safe_area.x", lambda spec: spec["safe_area"].__setitem__("x", "0")),
        ("spec.safe_area.x", lambda spec: spec["safe_area"].__setitem__("x", True)),
        (
            "spec.safe_area.x",
            lambda spec: spec["safe_area"].__setitem__("x", 10**400),
        ),
        ("spec.layers", lambda spec: spec.__setitem__("layers", {})),
        ("spec.layers[0].id", lambda spec: spec["layers"][0].__setitem__("id", 42)),
        (
            "spec.layers[0].z_index",
            lambda spec: spec["layers"][0].__setitem__("z_index", "1"),
        ),
        (
            "spec.layers[0].locked",
            lambda spec: spec["layers"][0].__setitem__("locked", "false"),
        ),
        (
            "spec.layers[0].style",
            lambda spec: spec["layers"][0].__setitem__("style", []),
        ),
    ]

    for field, mutate in cases:
        invalid_payload = json.loads(json.dumps(valid_payload))
        mutate(invalid_payload["spec"])
        (tmp_path / "presets.json").write_text(
            json.dumps({"version": 1, "presets": [invalid_payload]}),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match=re.escape(field)):
            repository.list_all()


def test_repository_cleans_temporary_manifest_on_atomic_replace_failure(
    tmp_path: Path,
    monkeypatch,
):
    repository = TemplatePresetRepository(tmp_path)

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(
        "pixelle_video.repositories.template_presets.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="simulated replace failure"):
        repository.save(_preset())

    assert list(tmp_path.glob("presets.json.*.tmp")) == []


def test_repository_cleans_temporary_manifest_on_atomic_write_failure(
    tmp_path: Path,
    monkeypatch,
):
    repository = TemplatePresetRepository(tmp_path)

    def fail_write_text(_self, *_args, **_kwargs):
        _self.parent.mkdir(parents=True, exist_ok=True)
        _self.write_bytes(b"partial")
        raise OSError("simulated write failure")

    monkeypatch.setattr(
        "pixelle_video.repositories.template_presets.Path.write_text",
        fail_write_text,
    )

    with pytest.raises(OSError, match="simulated write failure"):
        repository.save(_preset())

    assert list(tmp_path.glob("presets.json.*.tmp")) == []


def test_repository_accepts_repository_owned_asset_refs(tmp_path: Path):
    repository = TemplatePresetRepository(tmp_path)
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    asset_key = repository.persist_asset(source, "user:demo")
    layer = TemplateLayer(
        id="image-1",
        type="image",
        name="Image",
        rect=RectSpec(x=0, y=0, width=100, height=100),
        z_index=1,
        opacity=1.0,
        rotation=0.0,
        locked=False,
        source=LayerSourceSpec(kind="asset", ref=asset_key),
        style={},
    )

    saved = repository.save(_preset(spec=_spec(layers=(layer,))))

    assert saved.spec.layers[0].source.ref == asset_key
