import pytest

from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.services.layered_template_service import LayeredTemplateService


def _preview_spec() -> LayeredTemplateSpec:
    return LayeredTemplateSpec.from_dict(
        {
            "version": "layered_template.v1",
            "template_id": "preview-demo",
            "template_name": "Preview Demo",
            "template_type": "image",
            "canvas_width": 1080,
            "canvas_height": 1920,
            "media_width": 900,
            "media_height": 1200,
            "safe_area": {"x": 80, "y": 120, "width": 920, "height": 1680, "unit": "px"},
            "layers": [
                {
                    "id": "bg",
                    "type": "background",
                    "name": "Background",
                    "rect": {"x": 0, "y": 0, "width": 1080, "height": 1920, "unit": "px"},
                    "z_index": 0,
                    "opacity": 1,
                    "rotation": 0,
                    "locked": True,
                    "source": {"kind": "color", "ref": "#101820", "metadata": {}},
                    "style": {},
                    "role": None,
                },
                {
                    "id": "media",
                    "type": "generated_media",
                    "name": "Generated Media",
                    "rect": {"x": 90, "y": 260, "width": 900, "height": 1200, "unit": "px"},
                    "z_index": 10,
                    "opacity": 1,
                    "rotation": 0,
                    "locked": False,
                    "source": {
                        "kind": "generated_media",
                        "ref": "generated://preview",
                        "metadata": {},
                    },
                    "style": {},
                    "role": None,
                },
                {
                    "id": "body",
                    "type": "text",
                    "name": "Body",
                    "rect": {"x": 120, "y": 1480, "width": 840, "height": 120, "unit": "px"},
                    "z_index": 20,
                    "opacity": 0.9,
                    "rotation": 0,
                    "locked": False,
                    "source": {
                        "kind": "asset",
                        "ref": "text-source",
                        "metadata": {"text": "<b data-note='safe'>Body</b>"},
                    },
                    "style": {"font_size": 36, "color": "#FFFFFF"},
                    "role": None,
                },
                {
                    "id": "title",
                    "type": "text",
                    "name": "Title",
                    "rect": {"x": 110, "y": 90, "width": 860, "height": 180, "unit": "px"},
                    "z_index": 30,
                    "opacity": 1,
                    "rotation": 0,
                    "locked": False,
                    "source": None,
                    "style": {"font_size": 72, "color": "#FFEBCD"},
                    "role": "title",
                },
                {
                    "id": "caption",
                    "type": "text",
                    "name": "Caption",
                    "rect": {"x": 120, "y": 1640, "width": 840, "height": 140, "unit": "px"},
                    "z_index": 30,
                    "opacity": 1,
                    "rotation": 0,
                    "locked": False,
                    "source": None,
                    "style": {"font_size": 42, "color": "#FFFFFF"},
                    "role": "caption",
                },
            ],
            "metadata": {"ignored_for_fingerprint": "one"},
        }
    )


def test_render_preview_html_orders_layers_and_escapes_user_text():
    html = LayeredTemplateService().render_preview_html(
        spec=_preview_spec(),
        title_text="<script>alert('title')</script>",
        caption_text="<img src=x data-note='safe'>",
        text_rendering={"template_params": {"must": "not leak"}},
    )

    assert html.index('data-layer-id="bg"') < html.index('data-layer-id="media"')
    assert html.index('data-layer-id="body"') < html.index('data-layer-id="title"')
    assert html.index('data-layer-id="title"') < html.index('data-layer-id="caption"')
    assert "&lt;script&gt;alert(&#x27;title&#x27;)&lt;/script&gt;" in html
    assert "&lt;img src=x data-note=&#x27;safe&#x27;&gt;" in html
    assert "&lt;b data-note=&#x27;safe&#x27;&gt;Body&lt;/b&gt;" in html
    assert "<script" not in html.lower()
    assert "onclick=" not in html.lower()
    assert " onerror=" not in html.lower()
    assert "template_params" not in html


def test_render_preview_html_role_layers_use_text_rendering_style_contract():
    html = LayeredTemplateService().render_preview_html(
        spec=_preview_spec(),
        title_text="Title",
        caption_text="Caption",
        text_rendering={
            "title_style": {
                "font_size": 96,
                "primary_color": "#ABCDEF",
                "alignment": "right",
            },
            "caption_style": {
                "font_size": 44,
                "primary_color": "#123456",
                "alignment": "left",
            },
        },
    )

    assert 'data-layer-id="title"' in html
    assert "font-size:96px;color:#ABCDEF;text-align:right;justify-content:flex-end;" in html
    assert "font-size:44px;color:#123456;text-align:left;justify-content:flex-start;" in html


def test_render_preview_html_merges_partial_role_style_with_contract_defaults():
    html = LayeredTemplateService().render_preview_html(
        spec=_preview_spec(),
        title_text="Title",
        caption_text="Caption",
        text_rendering={
            "title_style": {"font_size": 96},
            "caption_style": {"alignment": "right"},
        },
    )

    assert "font-size:96px;color:#FFFFFF;text-align:center;justify-content:center;" in html
    assert "font-size:48px;color:#FFFFFF;text-align:right;justify-content:flex-end;" in html


def test_render_preview_html_never_uses_role_layer_style_as_text_contract():
    spec_payload = _preview_spec().to_dict()
    for layer in spec_payload["layers"]:
        if layer["role"] == "title":
            layer["style"] = {
                "font_size": 13,
                "color": "#ABCDEF",
                "alignment": "left",
            }

    html = LayeredTemplateService().render_preview_html(
        spec=spec_payload,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "font-size:13px;color:#ABCDEF;text-align:left;" not in html
    assert "font-size:48px;color:#FFFFFF;text-align:center;" in html


def test_render_preview_html_accepts_complete_zero_layer_legacy_spec():
    spec = LayeredTemplateSpec.from_dict(
        {
            "version": "layered_template.v1",
            "template_id": "legacy",
            "template_name": "Legacy",
            "template_type": "image",
            "canvas_width": 1920,
            "canvas_height": 1080,
            "media_width": 1920,
            "media_height": 1080,
            "safe_area": {"x": 0, "y": 0, "width": 1920, "height": 1080, "unit": "px"},
            "layers": [],
            "metadata": {"source_kind": "legacy_html"},
        }
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "width:1920px;" in html
    assert "height:1080px;" in html
    assert "legacy_html" not in html


def test_render_preview_html_blocks_remote_asset_urls():
    spec_payload = _preview_spec().to_dict()
    media_layer = spec_payload["layers"][1]
    media_layer["type"] = "image"
    media_layer["source"] = {
        "kind": "asset",
        "ref": "https://tracker.example.test/pixel.png",
        "metadata": {},
    }

    html = LayeredTemplateService().render_preview_html(
        spec=spec_payload,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "https://tracker.example.test" not in html
    assert "<img" not in html
    assert "image</div>" in html


def test_render_preview_html_allows_repository_asset_keys_only():
    spec_payload = _preview_spec().to_dict()
    media_layer = spec_payload["layers"][1]
    media_layer["type"] = "image"
    media_layer["source"] = {
        "kind": "asset",
        "ref": "assets/user_demo/image.png",
        "metadata": {},
    }

    html = LayeredTemplateService().render_preview_html(
        spec=spec_payload,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert '<img alt="" src="assets/user_demo/image.png">' in html


def test_render_preview_html_blocks_percent_encoded_asset_traversal():
    spec_payload = _preview_spec().to_dict()
    media_layer = spec_payload["layers"][1]
    media_layer["type"] = "image"
    media_layer["source"] = {
        "kind": "asset",
        "ref": "assets/%2e%2e/secrets.png",
        "metadata": {},
    }

    html = LayeredTemplateService().render_preview_html(
        spec=spec_payload,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "%2e%2e" not in html
    assert "<img" not in html


def test_render_preview_html_rejects_invalid_gradient_source():
    spec_payload = _preview_spec().to_dict()
    background_layer = spec_payload["layers"][0]
    background_layer["source"] = {
        "kind": "gradient",
        "ref": " , ",
        "metadata": {},
    }

    html = LayeredTemplateService().render_preview_html(
        spec=spec_payload,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "linear-gradient(180deg, , )" not in html
    assert "background:#000000;" in html


def test_render_preview_html_uses_canvas_and_px_layer_geometry():
    html = LayeredTemplateService().render_preview_html(
        spec=_preview_spec(),
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "width:1080px;" in html
    assert "height:1920px;" in html
    assert "aspect-ratio:1080 / 1920;" in html
    assert "left:90px;" in html
    assert "top:260px;" in html
    assert "width:900px;" in html
    assert "height:1200px;" in html


def test_service_normalizes_validates_and_fingerprints_spec():
    service = LayeredTemplateService()
    spec = _preview_spec()
    normalized = service.normalize_spec(spec.to_dict())

    assert normalized == spec
    assert service.validate_spec(normalized) == normalized
    assert service.fingerprint(normalized) == service.fingerprint(spec.to_dict())
    changed_metadata = LayeredTemplateSpec.from_dict(
        {**spec.to_dict(), "metadata": {"ignored_for_fingerprint": "two"}}
    )
    assert service.fingerprint(changed_metadata) == service.fingerprint(spec)


def test_service_rejects_duplicate_layer_ids():
    spec_payload = _preview_spec().to_dict()
    spec_payload["layers"][1]["id"] = spec_payload["layers"][0]["id"]

    with pytest.raises(ValueError, match="duplicate layer id"):
        LayeredTemplateService().validate_spec(spec_payload)
