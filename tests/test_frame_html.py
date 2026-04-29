import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from pixelle_video.services.frame_html import HTMLFrameGenerator
from pixelle_video.services.frame_render_readiness import FrameRenderReadiness
from web.state.async_runtime import AsyncRuntime, shutdown_all_async_runtimes
from web.utils.async_helpers import run_async


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
