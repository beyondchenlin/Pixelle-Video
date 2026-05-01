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


def test_build_text_rendering_preview_spec_merges_title_preset_defaults():
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
        title_style={"font_size": 96},
        caption_style={},
    )

    assert spec.title_style["font_size"] == 96
    assert spec.title_style["primary_color"] == "#2C3E50"
    assert spec.title_style["background_color"] == "#FFFFFF"
    assert spec.title_style["background_opacity"] == 0.92


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


def test_render_preview_html_uses_text_style_layout_for_instant_preview():
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1000,
        canvas_height=500,
        media_width=500,
        media_height=500,
        media_placement={"anchor": "center"},
        title_text="Title",
        caption_text="Caption",
        title_style={
            "position": "bottom_right",
            "alignment": "right",
            "margin_x": 44,
            "margin_y": 56,
            "max_width_ratio": 0.4,
        },
        caption_style={},
    )

    html = render_preview_html(spec)

    assert "left:auto;" in html
    assert "right:9.000%;" in html
    assert "top:auto;" in html
    assert "bottom:79.500%;" in html
    assert "transform:none;" in html
    assert "width:40.000%;" in html
    assert "max-width:min(40.000%, calc(100% - 9.000% - 9.000%));" in html
    assert "text-align:right;" in html
    assert "justify-content:flex-end;" in html


def test_render_preview_html_constrains_title_layout_to_template_region():
    spec = build_text_rendering_preview_spec(
        template_id="image_landscape_minimal",
        render_backend="hyperframes",
        canvas_width=1000,
        canvas_height=500,
        media_width=500,
        media_height=500,
        media_placement={"anchor": "center"},
        title_text="Title",
        caption_text="Caption",
        title_style={
            "position": "bottom_right",
            "alignment": "right",
            "margin_x": 10,
            "margin_y": 20,
            "max_width_ratio": 1.0,
        },
        caption_style={},
    )

    html = render_preview_html(spec)

    assert "right:50.500%;" in html
    assert "bottom:71.500%;" in html
    assert "width:44.000%;" in html
    assert "max-width:min(44.000%, calc(100% - 5.500% - 50.500%));" in html


def test_render_preview_html_uses_template_region_when_style_has_no_layout():
    spec = build_text_rendering_preview_spec(
        template_id="image_landscape_minimal",
        render_backend="hyperframes",
        canvas_width=1280,
        canvas_height=720,
        media_width=960,
        media_height=540,
        media_placement={"anchor": "center"},
        title_text="Title",
        caption_text="Caption",
        title_style={},
        caption_style={"font_size": 42},
    )

    html = render_preview_html(spec)

    assert "left:18.000%;" in html
    assert "top:69.000%;" in html
    assert "width:64.000%;" in html
    assert "height:17.000%;" in html


def test_render_preview_html_applies_background_opacity_to_background_only():
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
            "background_color": "#000000",
            "background_opacity": 0.5,
        },
        caption_style={},
    )

    html = render_preview_html(spec)

    assert "background:rgba(0, 0, 0, 0.5);" in html
    assert "opacity:0.5;" not in html


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


def test_preview_cache_marks_real_frame_stale_when_fingerprint_changes():
    from web.components.text_rendering_preview import (
        build_real_preview_state,
        is_real_preview_stale,
    )

    state = build_real_preview_state(
        storage_key="artifacts/ws/preview.png",
        url="/api/files/artifacts/ws/preview.png",
        fingerprint="old",
        error=None,
    )

    assert is_real_preview_stale(state, "old") is False
    assert is_real_preview_stale(state, "new") is True
    assert is_real_preview_stale(None, "new") is True


def test_request_real_preview_frame_posts_storage_key_only_for_artifacts(monkeypatch):
    from web.components import text_rendering_preview
    from web.components.text_rendering_preview import (
        is_real_preview_stale,
        request_real_preview_frame,
    )

    posts = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "storage_key": "artifacts/ws/rendered.png",
                "url": "/api/files/artifacts/ws/rendered.png",
                "fingerprint": "server-fp",
            }

    def fake_post(url, *, json, timeout):
        posts.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(text_rendering_preview.httpx, "post", fake_post)

    artifacts_spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        media_placement={"anchor": "center"},
        preview_media_ref="artifacts/ws/source.png",
        title_text="Title",
        caption_text="Caption",
        title_style={"font_size": 84},
        caption_style={"font_size": 42},
    )
    state = request_real_preview_frame(
        spec=artifacts_spec,
        text_rendering_payload={"title_style": {"font_size": 84}},
        api_base_url="http://localhost:8000/api/",
        workspace_id="ws",
    )

    public_spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        media_placement={"anchor": "center"},
        preview_media_ref="https://cdn.example.test/source.png",
        title_text="Title",
        caption_text="Caption",
        title_style={"font_size": 84},
        caption_style={"font_size": 42},
    )
    request_real_preview_frame(
        spec=public_spec,
        text_rendering_payload={"caption_style": {"font_size": 42}},
        api_base_url="http://localhost:8000/api/",
        workspace_id="ws",
    )

    assert state == {
        "storage_key": "artifacts/ws/rendered.png",
        "url": "/api/files/artifacts/ws/rendered.png",
        "fingerprint": artifacts_spec.fingerprint,
        "frame_fingerprint": "server-fp",
        "error": None,
    }
    assert is_real_preview_stale(state, artifacts_spec.fingerprint) is False
    assert posts[0]["url"] == "http://localhost:8000/api/text-rendering/preview-frame"
    assert posts[0]["json"]["preview_media_storage_key"] == "artifacts/ws/source.png"
    assert "preview_media_url" not in posts[0]["json"]
    assert "preview_media_storage_key" not in posts[1]["json"]
    assert "preview_media_url" not in posts[1]["json"]
    assert posts[0]["json"]["text_rendering"] == {"title_style": {"font_size": 84}}
    assert posts[0]["json"]["workspace_id"] == "ws"
    assert posts[0]["json"]["template_id"] == "image_default"
    assert posts[0]["json"]["render_backend"] == "hyperframes"
    assert posts[0]["json"]["canvas_width"] == 1080
    assert posts[0]["json"]["canvas_height"] == 1920
    assert posts[0]["json"]["media_width"] == 900
    assert posts[0]["json"]["media_height"] == 1200
    assert posts[0]["json"]["media_placement"] == {"anchor": "center"}
    assert posts[0]["json"]["title_text"] == "Title"
    assert posts[0]["json"]["caption_text"] == "Caption"


def test_request_real_preview_frame_returns_error_state_on_exception(monkeypatch):
    from web.components import text_rendering_preview
    from web.components.text_rendering_preview import request_real_preview_frame

    def fake_post(*_args, **_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(text_rendering_preview.httpx, "post", fake_post)
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        title_style={},
        caption_style={},
    )

    state = request_real_preview_frame(
        spec=spec,
        text_rendering_payload={},
        api_base_url="http://localhost:8000/api",
        workspace_id="ws",
    )

    assert state == {
        "storage_key": None,
        "url": None,
        "fingerprint": spec.fingerprint,
        "error": "network unavailable",
    }


def test_request_real_preview_frame_uses_http_error_detail(monkeypatch):
    import httpx

    from web.components import text_rendering_preview
    from web.components.text_rendering_preview import request_real_preview_frame

    def fake_post(*_args, **_kwargs):
        return httpx.Response(
            422,
            json={"detail": "preview media storage key is invalid"},
            request=httpx.Request("POST", "http://localhost:8000/api/text-rendering/preview-frame"),
        )

    monkeypatch.setattr(text_rendering_preview.httpx, "post", fake_post)
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        title_style={},
        caption_style={},
    )

    state = request_real_preview_frame(
        spec=spec,
        text_rendering_payload={},
        api_base_url="http://localhost:8000/api",
        workspace_id="ws",
    )

    assert state["storage_key"] is None
    assert state["url"] is None
    assert state["fingerprint"] == spec.fingerprint
    assert "preview media storage key is invalid" in state["error"]


def test_request_real_preview_frame_uses_http_error_envelope_message(monkeypatch):
    import httpx

    from web.components import text_rendering_preview
    from web.components.text_rendering_preview import request_real_preview_frame

    def fake_post(*_args, **_kwargs):
        return httpx.Response(
            400,
            json={
                "success": False,
                "message": "Unsupported text rendering preview template_id",
                "error": {"code": "http_400", "details": None},
            },
            request=httpx.Request("POST", "http://localhost:8000/api/text-rendering/preview-frame"),
        )

    monkeypatch.setattr(text_rendering_preview.httpx, "post", fake_post)
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        title_style={},
        caption_style={},
    )

    state = request_real_preview_frame(
        spec=spec,
        text_rendering_payload={},
        api_base_url="http://localhost:8000/api",
        workspace_id="ws",
    )

    assert state["storage_key"] is None
    assert state["url"] is None
    assert state["fingerprint"] == spec.fingerprint
    assert state["error"] == "Unsupported text rendering preview template_id"


def test_request_real_preview_frame_uses_nested_http_error_message(monkeypatch):
    import httpx

    from web.components import text_rendering_preview
    from web.components.text_rendering_preview import request_real_preview_frame

    def fake_post(*_args, **_kwargs):
        return httpx.Response(
            409,
            json={"error": {"message": "preview frame is stale"}},
            request=httpx.Request("POST", "http://localhost:8000/api/text-rendering/preview-frame"),
        )

    monkeypatch.setattr(text_rendering_preview.httpx, "post", fake_post)
    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        title_style={},
        caption_style={},
    )

    state = request_real_preview_frame(
        spec=spec,
        text_rendering_payload={},
        api_base_url="http://localhost:8000/api",
        workspace_id="ws",
    )

    assert state["error"] == "preview frame is stale"


def test_render_real_preview_status_reports_current_stale_and_error():
    from web.components.text_rendering_preview import (
        build_real_preview_state,
        render_real_preview_status,
    )

    class FakeUI:
        def __init__(self):
            self.images = []
            self.captions = []
            self.errors = []

        def image(self, url, **kwargs):
            self.images.append({"url": url, **kwargs})

        def caption(self, message):
            self.captions.append(message)

        def error(self, message):
            self.errors.append(message)

    spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        title_style={},
        caption_style={},
    )
    def translate(key, **kwargs):
        return f"{key}:{kwargs}" if kwargs else key

    current_ui = FakeUI()
    render_real_preview_status(
        spec,
        build_real_preview_state(
            storage_key="artifacts/ws/current.png",
            url="/api/files/current.png",
            fingerprint=spec.fingerprint,
            error=None,
        ),
        current_ui,
        translate,
    )
    stale_ui = FakeUI()
    render_real_preview_status(
        spec,
        build_real_preview_state(
            storage_key="artifacts/ws/old.png",
            url="/api/files/old.png",
            fingerprint="old",
            error=None,
        ),
        stale_ui,
        translate,
    )
    error_ui = FakeUI()
    render_real_preview_status(
        spec,
        build_real_preview_state(
            storage_key=None,
            url=None,
            fingerprint=spec.fingerprint,
            error="boom",
        ),
        error_ui,
        translate,
    )

    assert current_ui.images == [
        {
            "url": "/api/files/current.png",
            "caption": "text_rendering_preview.real_current",
        }
    ]
    assert stale_ui.images == []
    assert stale_ui.captions == ["text_rendering_preview.real_stale"]
    assert error_ui.errors == ["text_rendering_preview.real_failed:{'error': 'boom'}"]
