import sys
from pathlib import Path
from types import ModuleType

import pytest

from web.state.async_runtime import AsyncRuntime
from web.state.async_runtime import shutdown_all_async_runtimes
from pixelle_video.services.frame_html import HTMLFrameGenerator
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
