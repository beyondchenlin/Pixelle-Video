import pytest

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
    layered_template_fingerprint,
)
from pixelle_video.models.template_preset import TemplatePreset


def _demo_spec(**overrides):
    payload = {
        "version": "layered_template.v1",
        "template_id": "preset-demo",
        "template_name": "Demo",
        "template_type": "image",
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 1080,
        "media_height": 1920,
        "safe_area": RectSpec(x=64, y=64, width=952, height=1792),
        "layers": (),
        "metadata": {},
    }
    payload.update(overrides)
    return LayeredTemplateSpec(**payload)


def test_layered_template_spec_round_trips_to_dict():
    spec = _demo_spec(
        layers=(
            TemplateLayer(
                id="bg-1",
                type="background",
                name="Background",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="color", ref="#F6F1E8"),
                style={"background_color": "#F6F1E8"},
                role=None,
            ),
        ),
        metadata={"source": "user"},
    )

    payload = spec.to_dict()

    assert payload["template_id"] == "preset-demo"
    assert payload["layers"][0]["source"]["kind"] == "color"
    assert LayeredTemplateSpec.from_dict(payload) == spec


def test_template_layer_enabled_defaults_true_and_round_trips_false():
    layer = TemplateLayer.from_dict(
        {
            "id": "hidden-logo",
            "type": "image",
            "name": "Hidden Logo",
            "rect": {"x": 0, "y": 0, "width": 320, "height": 240, "unit": "px"},
            "z_index": 10,
            "opacity": 1.0,
            "rotation": 0.0,
            "locked": False,
            "source": None,
            "style": {},
            "enabled": False,
        }
    )

    assert layer.enabled is False
    assert layer.to_dict()["enabled"] is False
    legacy_layer = TemplateLayer.from_dict(
        {
            "id": "legacy-logo",
            "type": "image",
            "name": "Legacy Logo",
            "rect": {"x": 0, "y": 0, "width": 320, "height": 240, "unit": "px"},
            "z_index": 10,
            "opacity": 1.0,
            "rotation": 0.0,
            "locked": False,
            "source": None,
            "style": {},
        }
    )
    assert legacy_layer.enabled is True
    assert "enabled" not in legacy_layer.to_dict()


def test_layered_template_fingerprint_ignores_non_visual_metadata():
    base = _demo_spec(metadata={"updated_at": "2026-05-02T08:00:00Z"})
    changed = LayeredTemplateSpec.from_dict(
        {**base.to_dict(), "metadata": {"updated_at": "2026-05-02T09:00:00Z"}}
    )

    assert layered_template_fingerprint(base) == layered_template_fingerprint(changed)


def test_layered_template_fingerprint_changes_for_visual_fields():
    base = _demo_spec(canvas_width=1080)
    changed = LayeredTemplateSpec.from_dict({**base.to_dict(), "canvas_width": 1280})

    assert layered_template_fingerprint(base) != layered_template_fingerprint(changed)


@pytest.mark.parametrize("opacity", [-0.1, 1.1])
def test_template_layer_rejects_invalid_opacity(opacity):
    with pytest.raises(ValueError, match="opacity"):
        TemplateLayer(
            id="title-1",
            type="text",
            name="Title",
            rect=RectSpec(x=0, y=0, width=100, height=50),
            z_index=1,
            opacity=opacity,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
            role="title",
        )


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0, 50),
        (100, -1),
    ],
)
def test_rect_spec_rejects_non_positive_size(width, height):
    with pytest.raises(ValueError, match="width and height"):
        TemplateLayer(
            id="bad-rect",
            type="image",
            name="Bad Rect",
            rect=RectSpec(x=0, y=0, width=width, height=height),
            z_index=1,
            opacity=1.0,
            rotation=0.0,
            locked=False,
            source=None,
            style={},
        )


def test_template_preset_requires_full_spec():
    with pytest.raises(TypeError):
        TemplatePreset(
            preset_id="user:demo",
            name="Demo",
            source="user",
            orientation="portrait",
            template_type="image",
            spec=None,
        )
