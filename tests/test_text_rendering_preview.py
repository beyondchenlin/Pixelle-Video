from web.components.text_rendering_preview import (
    build_text_rendering_preview_spec,
    preview_spec_fingerprint,
    render_preview_html,
)


def test_build_text_rendering_preview_spec_derives_from_contracts_only():
    spec = build_text_rendering_preview_spec(
        template_id="image_landscape_minimal",
        render_backend="hyperframes",
        canvas_width=1280,
        canvas_height=720,
        media_width=960,
        media_height=540,
        media_placement={"anchor": "center", "scale_percent": 85},
        preview_media_ref="artifacts/demo.png",
        title_text="契约标题",
        caption_text="契约字幕",
        title_style={
            "font_size": 76,
            "primary_color": "#171410",
            "preview_title_text": "不应进入规格",
        },
        caption_style={
            "font_size": 42,
            "primary_color": "#2C3E50",
            "preview_caption_text": "不应进入规格",
        },
        text_rendering={"preview_media_ref": "ignored", "raw": {"leak": True}},
    )

    assert spec.template_id == "image_landscape_minimal"
    assert spec.render_backend == "hyperframes"
    assert spec.canvas_width == 1280
    assert spec.canvas_height == 720
    assert spec.media_width == 960
    assert spec.media_height == 540
    assert spec.media_placement == {"anchor": "center", "scale_percent": 85}
    assert spec.preview_media_ref == "artifacts/demo.png"
    assert spec.title_text == "契约标题"
    assert spec.caption_text == "契约字幕"
    assert spec.title_style["font_size"] == 76
    assert spec.caption_style["font_size"] == 42
    assert "preview_title_text" not in spec.title_style
    assert "preview_caption_text" not in spec.caption_style
    assert spec.title_region["width"] == 0.44
    assert spec.caption_safe_area["width"] == 0.64
    assert "text_rendering" not in spec.__dict__


def test_preview_spec_fingerprint_is_deterministic_and_excludes_itself():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="legacy",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1440,
        media_placement={"anchor": "center"},
        title_text="标题",
        caption_text="字幕",
        title_style={"font_size": 84},
        caption_style={"font_size": 42},
    )

    assert spec.fingerprint == preview_spec_fingerprint(spec)
    assert preview_spec_fingerprint({**spec.__dict__, "fingerprint": "changed"}) == spec.fingerprint


def test_render_preview_html_contains_image_title_and_caption_layers():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        media_placement={"anchor": "center"},
        preview_media_ref='artifacts/demo.png" onerror="alert(1)',
        title_text="<script>alert('title')</script>",
        caption_text="<b>caption</b>",
        title_style={"font_size": 84, "primary_color": "#2C3E50"},
        caption_style={"font_size": 42, "primary_color": "#FFFFFF"},
        text_rendering={"raw_secret": "must-not-leak"},
    )

    html = render_preview_html(spec)

    assert 'data-layer="media"' in html
    assert 'data-layer="title"' in html
    assert 'data-layer="caption"' in html
    assert "&lt;script&gt;alert(&#x27;title&#x27;)&lt;/script&gt;" in html
    assert "&lt;b&gt;caption&lt;/b&gt;" in html
    assert "onerror" not in html
    assert "raw_secret" not in html
    assert "text_rendering" not in html
