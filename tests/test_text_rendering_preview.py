from web.components.text_rendering_preview import (
    build_text_rendering_preview_spec,
    preview_spec_fingerprint,
    render_preview_html,
)


def test_build_text_rendering_preview_spec_derives_from_contracts_only():
    spec = build_text_rendering_preview_spec(
        template_id="image_landscape_minimal",
        render_backend=None,
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
    assert spec.render_backend is None
    assert spec.canvas_width == 1280
    assert spec.canvas_height == 720
    assert spec.media_width == 960
    assert spec.media_height == 540
    assert spec.media_placement == {"anchor": "center", "scale_percent": 85}
    assert spec.preview_media_ref == "artifacts/demo.png"
    assert spec.placeholder_media is False
    assert spec.title_text == "契约标题"
    assert spec.caption_text == "契约字幕"
    assert spec.title_style["font_size"] == 76
    assert spec.caption_style["font_size"] == 42
    assert "preview_title_text" not in spec.title_style
    assert "preview_caption_text" not in spec.caption_style
    assert spec.template_title_region["width"] == 0.44
    assert spec.template_caption_safe_area["width"] == 0.64
    assert "text_rendering" not in spec.__dict__


def test_build_text_rendering_preview_spec_marks_placeholder_media_when_ref_missing():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="legacy",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1440,
        media_placement={"anchor": "center"},
        title_style={},
        caption_style={},
    )

    assert spec.preview_media_ref is None
    assert spec.placeholder_media is True


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


def test_render_preview_html_uses_media_placement_for_media_box_percentages():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1000,
        canvas_height=500,
        media_width=500,
        media_height=500,
        media_placement={"anchor": "bottom_right", "scale_percent": 50},
        preview_media_ref="artifacts/demo.png",
        title_text="Title",
        caption_text="Caption",
        title_style={},
        caption_style={},
    )

    html = render_preview_html(spec)

    assert "left:75.000%;" in html
    assert "top:50.000%;" in html
    assert "width:25.000%;" in html
    assert "height:50.000%;" in html


def test_render_preview_html_sanitizes_style_values():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        media_placement={"anchor": "center"},
        title_text="Title",
        caption_text="Caption",
        title_style={
            "font_size": "99999",
            "primary_color": "#fff;position:fixed",
            "stroke_color": "url(javascript:alert(1))",
            "stroke_width": "999",
            "background_color": "expression(alert(1))",
            "background_opacity": "99",
        },
        caption_style={
            "font_size": "not-a-number",
            "primary_color": "red;left:0",
            "stroke_color": "#123456",
            "stroke_width": "-9",
            "background_color": "#ABC",
            "background_opacity": "-1",
        },
    )

    html = render_preview_html(spec)

    assert "#fff;position:fixed" not in html
    assert "url(javascript:alert(1))" not in html
    assert "expression(alert(1))" not in html
    assert "red;left:0" not in html
    assert "font-size:240px;" in html
    assert "font-size:42px;" in html
    assert "color:#FFFFFF;" in html
    assert "color:#123456;" not in html
    assert "background:transparent;" in html
    assert "-webkit-text-stroke:16px #000000;" in html
    assert "-webkit-text-stroke:0px #123456;" in html


def test_render_preview_html_degrades_when_media_contract_is_invalid():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=0,
        canvas_height=1920,
        media_width=-1,
        media_height=1200,
        media_placement={"anchor": "stale", "scale_percent": "bad"},
        title_text="Title",
        caption_text="Caption",
        title_style={},
        caption_style={},
    )

    html = render_preview_html(spec)

    assert 'data-layer="media"' in html
    assert 'data-layer="title"' in html
    assert 'data-layer="caption"' in html
    assert "left:0.000%;" in html
    assert "top:0.000%;" in html
    assert "width:100.000%;" in html
    assert "height:100.000%;" in html
