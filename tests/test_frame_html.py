import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from pixelle_video.services.frame_html import HTMLDocumentFrameRenderer, HTMLFrameGenerator
from pixelle_video.services.frame_render_readiness import FrameRenderReadiness
from pixelle_video.services.layered_template_adapters.html_frame import (
    LayeredTemplateHTMLFrameAdapter,
)
from web.state.async_runtime import AsyncRuntime, shutdown_all_async_runtimes
from web.utils.async_helpers import run_async


def _layered_template_spec_payload(**overrides):
    payload = {
        "version": "layered_template.v1",
        "template_id": "user:portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [],
        "metadata": {"source_kind": "user"},
    }
    payload.update(overrides)
    return payload


def test_run_async_can_render_html_frames_across_multiple_calls(tmp_path):
    template = Path("templates/1080x1080/image_minimal_framed.html")
    image = Path("resources/example.png")
    generator = HTMLFrameGenerator(str(template))

    first_output = tmp_path / "first.png"
    second_output = tmp_path / "second.png"

    try:
        first_path = run_async(
            generator.generate_frame(
                title="First",
                text="first render",
                image=str(image),
                ext={"index": 1},
                output_path=str(first_output),
            )
        )
        second_path = run_async(
            generator.generate_frame(
                title="Second",
                text="second render",
                image=str(image),
                ext={"index": 2},
                output_path=str(second_output),
            )
        )
    finally:
        run_async(HTMLFrameGenerator.close_browser())
        shutdown_all_async_runtimes()

    assert Path(first_path).exists()
    assert Path(second_path).exists()


def test_html_frame_generator_isolates_browser_instances_per_runtime(monkeypatch):
    launches = []

    class FakeBrowser:
        def __init__(self, name):
            self.name = name
            self.closed = False

        def is_connected(self):
            return not self.closed

        async def close(self):
            self.closed = True

    class FakeChromium:
        async def launch(self, args=None):
            browser = FakeBrowser(f"browser-{len(launches)}")
            launches.append(browser)
            return browser

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()
            self.stopped = False

        async def stop(self):
            self.stopped = True

    class FakePlaywrightStarter:
        async def start(self):
            return FakePlaywright()

    fake_module = ModuleType("playwright.async_api")
    fake_module.async_playwright = lambda: FakePlaywrightStarter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)

    runtime_a = AsyncRuntime("runtime-a")
    runtime_b = AsyncRuntime("runtime-b")

    try:
        browser_a = runtime_a.run(HTMLFrameGenerator._ensure_browser())
        browser_b = runtime_b.run(HTMLFrameGenerator._ensure_browser())
        assert browser_a is not browser_b

        runtime_b.run(HTMLFrameGenerator.close_browser())
        assert browser_b.closed is True
        assert browser_a.closed is False

        browser_a_again = runtime_a.run(HTMLFrameGenerator._ensure_browser())
        assert browser_a_again is browser_a
    finally:
        try:
            runtime_a.run(HTMLFrameGenerator.close_browser())
        except Exception:
            pass
        try:
            runtime_b.run(HTMLFrameGenerator.close_browser())
        except Exception:
            pass
        runtime_a.close()
        runtime_b.close()


@pytest.mark.parametrize(
    "template_path",
    sorted(Path("templates").rglob("image_*.html")),
)
def test_all_image_templates_use_768_square_media_defaults(template_path):
    generator = HTMLFrameGenerator(str(template_path))

    assert generator.get_media_size() == (768, 768)


def test_square_minimal_template_reserves_title_caption_and_signature_regions():
    template = Path("templates/1080x1080/image_minimal_framed.html").read_text(
        encoding="utf-8"
    )

    assert "PixelleNotoSansSC" in template
    assert "{{title}}" in template
    assert "{{text}}" in template
    assert "{{brand=LanRen}}" in template
    assert "{{author=LanRen.AI}}" in template
    assert "{{describe=LanRen}}" in template
    assert "pixelle_media_layer" in template
    assert "signature" in template
    assert "display: grid;" in template
    assert "grid-template-rows: 120px 602px 104px 82px;" in template
    assert "aspect-ratio: 1 / 1;" in template
    assert ".signature-mark" not in template


def test_prepare_html_for_render_injects_template_base_href(tmp_path):
    test_root = tmp_path / "test_frame_html_base_href"
    template_dir = test_root / "templates" / "1920x1080"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text(
        "<!DOCTYPE html><html><head><meta charset='UTF-8'><style>@font-face { src: url('./font.ttf'); }</style></head><body>{{title}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template))
    prepared_html = generator._prepare_html_for_render(generator.template)

    assert f'<base href="{template_dir.resolve().as_uri()}/">' in prepared_html


def test_html_document_frame_renderer_injects_base_href(tmp_path):
    renderer = HTMLDocumentFrameRenderer(base_path=tmp_path / "assets")

    prepared_html = renderer._prepare_html_for_render(
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>demo</body></html>"
    )

    assert f'<base href="{(tmp_path / "assets").resolve().as_uri()}/">' in prepared_html


def test_html_document_frame_renderer_keeps_existing_base_tag(tmp_path):
    renderer = HTMLDocumentFrameRenderer(base_path=tmp_path / "assets")
    html = "<html><head><base href='file:///existing/'></head><body>demo</body></html>"

    prepared_html = renderer._prepare_html_for_render(html)

    assert prepared_html == html


@pytest.mark.asyncio
async def test_layered_template_html_frame_adapter_renders_document_with_spec_canvas(
    tmp_path,
):
    calls = {}

    class FakeTemplateService:
        def render_preview_html(self, *, spec, title_text, caption_text, text_rendering):
            calls["html_args"] = {
                "spec": spec.to_dict(),
                "title_text": title_text,
                "caption_text": caption_text,
                "text_rendering": dict(text_rendering),
            }
            return "<html>preview</html>"

    class FakeRenderer:
        async def render_html_document(self, *, html, output_path, width, height):
            calls["render"] = {
                "html": html,
                "output_path": output_path,
                "width": width,
                "height": height,
            }
            Path(output_path).write_bytes(b"png")
            return output_path

    adapter = LayeredTemplateHTMLFrameAdapter(
        template_service=FakeTemplateService(),
        renderer=FakeRenderer(),
    )

    result = await adapter.render_frame(
        spec=_layered_template_spec_payload(),
        output_path=tmp_path / "frame.png",
        title_text="Title",
        caption_text="Caption",
        text_rendering={"title_style": {"font_size": 88}},
        media_path="raw.png",
    )

    assert result == tmp_path / "frame.png"
    assert calls["render"]["html"] == "<html>preview</html>"
    assert calls["render"]["width"] == 720
    assert calls["render"]["height"] == 1280
    assert calls["html_args"]["title_text"] == "Title"
    assert calls["html_args"]["caption_text"] == "Caption"


@pytest.mark.asyncio
async def test_layered_template_html_frame_adapter_rejects_unknown_generated_media_ref(
    tmp_path,
):
    spec = _layered_template_spec_payload(
        layers=[
            {
                "id": "unknown-generated",
                "type": "generated_media",
                "name": "Unknown generated media",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 1,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://secondary",
                    "metadata": {},
                },
                "style": {},
                "role": None,
            }
        ],
    )

    class FakeRenderer:
        async def render_html_document(self, **_kwargs):
            raise AssertionError("renderer must not run for unknown generated-media refs")

    adapter = LayeredTemplateHTMLFrameAdapter(renderer=FakeRenderer())

    with pytest.raises(ValueError, match="unsupported generated-media ref: generated://secondary"):
        await adapter.render_frame(
            spec=spec,
            output_path=tmp_path / "frame.png",
            title_text="Title",
            caption_text="Caption",
            text_rendering={},
            media_path="raw.png",
        )


@pytest.mark.asyncio
async def test_layered_template_html_frame_adapter_requires_media_path_for_primary_generated_media(
    tmp_path,
):
    spec = _layered_template_spec_payload(
        layers=[
            {
                "id": "primary-generated",
                "type": "generated_media",
                "name": "Primary generated media",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 1,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://primary",
                    "metadata": {},
                },
                "style": {},
                "role": None,
            }
        ],
    )

    class FakeRenderer:
        async def render_html_document(self, **_kwargs):
            raise AssertionError("renderer must not render generated media placeholder")

    adapter = LayeredTemplateHTMLFrameAdapter(renderer=FakeRenderer())

    with pytest.raises(ValueError, match="generated://primary requires media_path"):
        await adapter.render_frame(
            spec=spec,
            output_path=tmp_path / "frame.png",
            title_text="Title",
            caption_text="Caption",
            text_rendering={},
            media_path=None,
        )


@pytest.mark.asyncio
async def test_layered_template_html_frame_adapter_rejects_generated_media_without_source(
    tmp_path,
):
    spec = _layered_template_spec_payload(
        layers=[
            {
                "id": "missing-generated-source",
                "type": "generated_media",
                "name": "Missing generated media",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 1,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": None,
                "style": {},
                "role": None,
            }
        ],
    )

    class FakeRenderer:
        async def render_html_document(self, **_kwargs):
            raise AssertionError("renderer must not render generated media placeholder")

    adapter = LayeredTemplateHTMLFrameAdapter(renderer=FakeRenderer())

    with pytest.raises(ValueError, match="generated-media layer missing source"):
        await adapter.render_frame(
            spec=spec,
            output_path=tmp_path / "frame.png",
            title_text="Title",
            caption_text="Caption",
            text_rendering={},
            media_path=str(tmp_path / "primary.png"),
        )


@pytest.mark.asyncio
async def test_layered_template_html_frame_adapter_maps_primary_generated_media_to_media_path(
    tmp_path,
):
    media_path = tmp_path / "primary.png"
    media_path.write_bytes(b"png")
    calls = {}
    spec = _layered_template_spec_payload(
        layers=[
            {
                "id": "primary-generated",
                "type": "generated_media",
                "name": "Primary generated media",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 1,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://primary",
                    "metadata": {},
                },
                "style": {},
                "role": None,
            }
        ],
    )

    class FakeTemplateService:
        def render_preview_html(self, *, spec, title_text, caption_text, text_rendering):
            calls["layer_source"] = spec.layers[0].source.to_dict()
            return "<html>preview</html>"

    class FakeRenderer:
        async def render_html_document(self, *, html, output_path, width, height):
            Path(output_path).write_bytes(b"png")
            return output_path

    adapter = LayeredTemplateHTMLFrameAdapter(
        template_service=FakeTemplateService(),
        renderer=FakeRenderer(),
    )

    await adapter.render_frame(
        spec=spec,
        output_path=tmp_path / "frame.png",
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
        media_path=str(media_path),
    )

    assert calls["layer_source"]["kind"] == "asset"
    assert calls["layer_source"]["ref"] == media_path.resolve().as_uri()


def test_parse_template_parameters_excludes_runtime_reserved_placeholders(tmp_path):
    template_dir = tmp_path / "templates" / "1920x1080"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_reserved.html"
    template.write_text(
        """
        <html>
          <body data-media-layout-mode="{{media_layout_mode=template}}">
            {{title}} {{text}} {{image}} {{index}}
            <span>{{brand=Pixelle}}</span>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    params = HTMLFrameGenerator(str(template)).parse_template_parameters()

    assert params == {
        "brand": {
            "type": "text",
            "default": "Pixelle",
            "label": "brand",
        }
    }


def test_html_frame_generator_injects_standard_media_layer_css(tmp_path):
    template_dir = tmp_path / "templates" / "1920x1080"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_standard.html"
    template.write_text(
        "<html><head></head><body>{{pixelle_media_layer}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template), canvas_width=1280, canvas_height=720)
    html = generator._build_render_html(
        title="Demo",
        text="",
        image="file:///tmp/source.png",
        ext={"index": 1},
        media_placement={"scale_percent": 80, "anchor": "center"},
        media_type="image",
        media_width=1280,
        media_height=720,
    )

    assert "pixelle-media-layer" in html
    assert "--pixelle-media-display-width: 1536px" in html
    assert "--pixelle-media-display-height: 864px" in html
    assert "--pixelle-media-left: 192px" in html
    assert "--pixelle-media-top: 108px" in html
    assert '<img class="pixelle-media"' in html


def test_html_frame_generator_defaults_standard_media_layer_to_full_contain_fit(
    tmp_path,
):
    template_dir = tmp_path / "templates" / "1920x1080"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_standard.html"
    template.write_text(
        "<html><head></head><body>{{pixelle_media_layer}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template), canvas_width=1280, canvas_height=720)
    html = generator._build_render_html(
        title="Demo",
        text="",
        image="file:///tmp/source.png",
        ext={"index": 1},
        media_placement=None,
        media_type="image",
        media_width=1280,
        media_height=720,
    )

    assert "--pixelle-media-display-width: 1920px" in html
    assert "--pixelle-media-display-height: 1080px" in html
    assert "--pixelle-media-left: 0px" in html
    assert "--pixelle-media-top: 0px" in html


def test_html_frame_generator_injects_video_media_element(tmp_path):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "video_standard.html"
    template.write_text(
        "<html><head></head><body>{{pixelle_media_layer}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template), canvas_width=1280, canvas_height=720)
    html = generator._build_render_html(
        title="Demo",
        text="",
        image="file:///tmp/source.mp4",
        ext={"index": 1},
        media_placement={"scale_percent": 80},
        media_type="video",
        media_width=1280,
        media_height=720,
    )

    assert '<video class="pixelle-media"' in html
    assert "muted playsinline" in html


def test_html_frame_generator_keeps_legacy_image_placeholder_without_standard_layer(
    tmp_path,
):
    template_dir = tmp_path / "templates" / "1080x1920"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_legacy.html"
    template.write_text(
        "<html><head></head><body>{{image}}</body></html>",
        encoding="utf-8",
    )

    generator = HTMLFrameGenerator(str(template), canvas_width=1280, canvas_height=720)
    html = generator._build_render_html(
        title="Demo",
        text="",
        image="file:///tmp/source.png",
        ext={"index": 1},
        media_placement={"scale_percent": 80, "anchor": "center"},
        media_type="image",
        media_width=1280,
        media_height=720,
    )

    assert "file:///tmp/source.png" in html
    assert "data-pixelle-media-placement" not in html
    assert "pixelle-media-layer" not in html


def test_html_frame_generator_normalizes_output_png_to_target_canvas(tmp_path):
    template_dir = tmp_path / "templates" / "1080x1920"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"
    Image.new("RGBA", (1080, 1920), (255, 0, 0, 255)).save(output)

    generator = HTMLFrameGenerator(
        str(template),
        canvas_width=1280,
        canvas_height=720,
    )
    generator._normalize_canvas_output(str(output))

    with Image.open(output) as image:
        assert image.size == (1280, 720)

    assert (generator.template_width, generator.template_height) == (1080, 1920)
    assert (generator.width, generator.height) == (1280, 720)


def test_html_frame_generator_uses_deterministic_render_readiness(
    tmp_path,
    monkeypatch,
):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"
    calls = {}

    class FakePage:
        async def goto(self, url, wait_until, timeout=None):
            calls["goto"] = {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            }

        async def evaluate(self, script):
            calls.setdefault("evaluate", []).append(script)

        async def screenshot(self, path, type, omit_background):
            Image.new("RGBA", (1280, 720), (255, 0, 0, 255)).save(path)

        async def close(self):
            calls["closed"] = True

    class FakeBrowser:
        async def new_page(self, viewport, device_scale_factor):
            calls["new_page"] = {
                "viewport": viewport,
                "device_scale_factor": device_scale_factor,
            }
            return FakePage()

    async def fake_ensure_browser(_cls):
        return FakeBrowser()

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", fake_ensure_browser)

    generator = HTMLFrameGenerator(str(template))
    try:
        run_async(
            generator.generate_frame(
                title="Demo",
                text="",
                image="",
                ext={"index": 1},
                output_path=str(output),
            )
        )
    finally:
        shutdown_all_async_runtimes()

    assert calls["goto"]["wait_until"] == "domcontentloaded"
    assert calls["goto"]["timeout"] == 30000
    assert "document.fonts.ready" in calls["evaluate"][0]
    assert "decode" in calls["evaluate"][0]
    assert output.exists()


def test_html_frame_generator_retries_when_browser_disconnects_during_screenshot(
    tmp_path,
    monkeypatch,
):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"
    attempts = {"count": 0, "closed": 0}

    class FakePage:
        def __init__(self, should_fail):
            self.should_fail = should_fail

        async def goto(self, url, wait_until, timeout=None):
            pass

        async def evaluate(self, script):
            pass

        async def screenshot(self, path, type, omit_background):
            if self.should_fail:
                raise RuntimeError(
                    "Page.screenshot: Target page, context or browser has been closed"
                )
            Image.new("RGBA", (1280, 720), (255, 0, 0, 255)).save(path)

        async def close(self):
            attempts["closed"] += 1

    class FakeBrowser:
        def __init__(self, should_fail):
            self.should_fail = should_fail

        async def new_page(self, viewport, device_scale_factor):
            return FakePage(self.should_fail)

    async def fake_ensure_browser(_cls):
        attempts["count"] += 1
        return FakeBrowser(should_fail=attempts["count"] == 1)

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", fake_ensure_browser)

    generator = HTMLFrameGenerator(str(template))
    try:
        result = run_async(
            generator.generate_frame(
                title="Retry screenshot",
                text="",
                image="",
                ext={"index": 1},
                output_path=str(output),
            )
        )
    finally:
        shutdown_all_async_runtimes()

    assert result == str(output)
    assert output.exists()
    assert attempts["count"] == 2
    assert attempts["closed"] == 2
    assert not (tmp_path / "frame.debug.html").exists()


def test_html_frame_generator_preserves_debug_html_when_rendering_fails(
    tmp_path,
    monkeypatch,
):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"

    class FailingReadiness(FrameRenderReadiness):
        async def wait(self, page):
            raise RuntimeError("font decode failed")

    class FakePage:
        async def goto(self, url, wait_until, timeout=None):
            self.url = url

        async def screenshot(self, path, type, omit_background):
            raise AssertionError("screenshot should not run after readiness failure")

        async def close(self):
            pass

    class FakeBrowser:
        async def new_page(self, viewport, device_scale_factor):
            return FakePage()

    async def fake_ensure_browser(_cls):
        return FakeBrowser()

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", fake_ensure_browser)

    generator = HTMLFrameGenerator(
        str(template),
        render_readiness=FailingReadiness(),
    )

    try:
        with pytest.raises(RuntimeError, match="frame.debug.html"):
            run_async(
                generator.generate_frame(
                    title="Debug",
                    text="",
                    image="",
                    ext={"index": 1},
                    output_path=str(output),
                )
            )
    finally:
        shutdown_all_async_runtimes()

    debug_html = tmp_path / "frame.debug.html"
    assert debug_html.exists()
    assert "Debug" in debug_html.read_text(encoding="utf-8")


def test_html_frame_generator_ignores_page_close_failure_after_screenshot(
    tmp_path,
    monkeypatch,
):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"

    class FakePage:
        async def goto(self, url, wait_until, timeout=None):
            pass

        async def evaluate(self, script):
            pass

        async def screenshot(self, path, type, omit_background):
            Image.new("RGBA", (1280, 720), (255, 0, 0, 255)).save(path)

        async def close(self):
            raise RuntimeError("page already closed")

    class FakeBrowser:
        async def new_page(self, viewport, device_scale_factor):
            return FakePage()

    async def fake_ensure_browser(_cls):
        return FakeBrowser()

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", fake_ensure_browser)

    generator = HTMLFrameGenerator(str(template))
    try:
        result = run_async(
            generator.generate_frame(
                title="Close failure",
                text="",
                image="",
                ext={"index": 1},
                output_path=str(output),
            )
        )
    finally:
        shutdown_all_async_runtimes()

    assert result == str(output)
    assert output.exists()
    assert not (tmp_path / "frame.debug.html").exists()


def test_html_frame_generator_ignores_temp_html_delete_failure_after_screenshot(
    tmp_path,
    monkeypatch,
):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"

    class FakePage:
        async def goto(self, url, wait_until, timeout=None):
            pass

        async def evaluate(self, script):
            pass

        async def screenshot(self, path, type, omit_background):
            Image.new("RGBA", (1280, 720), (255, 0, 0, 255)).save(path)

        async def close(self):
            pass

    class FakeBrowser:
        async def new_page(self, viewport, device_scale_factor):
            return FakePage()

    async def fake_ensure_browser(_cls):
        return FakeBrowser()

    def fail_unlink(path):
        raise PermissionError("temp file locked")

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", fake_ensure_browser)
    monkeypatch.setattr("pixelle_video.services.frame_html.os.unlink", fail_unlink)

    generator = HTMLFrameGenerator(str(template))
    try:
        result = run_async(
            generator.generate_frame(
                title="Unlink failure",
                text="",
                image="",
                ext={"index": 1},
                output_path=str(output),
            )
        )
    finally:
        shutdown_all_async_runtimes()

    assert result == str(output)
    assert output.exists()


def test_html_frame_generator_keeps_original_error_when_temp_html_delete_fails(
    tmp_path,
    monkeypatch,
):
    template_dir = tmp_path / "templates" / "1280x720"
    template_dir.mkdir(parents=True)
    template = template_dir / "image_sample.html"
    template.write_text("<html><body>{{title}}</body></html>", encoding="utf-8")
    output = tmp_path / "frame.png"

    class FailingReadiness(FrameRenderReadiness):
        async def wait(self, page):
            raise RuntimeError("original render failure")

    class FakePage:
        async def goto(self, url, wait_until, timeout=None):
            pass

        async def screenshot(self, path, type, omit_background):
            raise AssertionError("screenshot should not run after readiness failure")

        async def close(self):
            pass

    class FakeBrowser:
        async def new_page(self, viewport, device_scale_factor):
            return FakePage()

    async def fake_ensure_browser(_cls):
        return FakeBrowser()

    def fail_unlink(path):
        raise PermissionError("temp file locked")

    monkeypatch.setattr(HTMLFrameGenerator, "_ensure_browser", fake_ensure_browser)
    monkeypatch.setattr("pixelle_video.services.frame_html.os.unlink", fail_unlink)

    generator = HTMLFrameGenerator(
        str(template),
        render_readiness=FailingReadiness(),
    )

    try:
        with pytest.raises(RuntimeError) as exc_info:
            run_async(
                generator.generate_frame(
                    title="Failure",
                    text="",
                    image="",
                    ext={"index": 1},
                    output_path=str(output),
                )
            )
    finally:
        shutdown_all_async_runtimes()

    assert "original render failure" in str(exc_info.value)
    assert "temp file locked" not in str(exc_info.value)
    assert "frame.debug.html" in str(exc_info.value)
