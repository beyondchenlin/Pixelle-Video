import asyncio

import pytest

from pixelle_video.services.frame_render_readiness import (
    FRAME_RENDER_READY_SCRIPT,
    FrameRenderReadiness,
    FrameRenderReadinessTimeoutError,
)


@pytest.mark.asyncio
async def test_frame_render_readiness_waits_for_fonts_images_and_animation_frames():
    calls = {}

    class FakePage:
        async def evaluate(self, script):
            calls["script"] = script

    readiness = FrameRenderReadiness(ready_timeout_ms=1000)

    await readiness.wait(FakePage())

    assert readiness.navigation_wait_until == "domcontentloaded"
    assert calls["script"] == FRAME_RENDER_READY_SCRIPT
    assert "document.fonts.ready" in calls["script"]
    assert "decode" in calls["script"]
    assert "requestAnimationFrame" in calls["script"]


@pytest.mark.asyncio
async def test_frame_render_readiness_times_out_with_context():
    class HangingPage:
        async def evaluate(self, script):
            await asyncio.sleep(1)

    readiness = FrameRenderReadiness(ready_timeout_ms=1)

    with pytest.raises(
        FrameRenderReadinessTimeoutError,
        match="HTML render readiness timed out after 1ms",
    ):
        await readiness.wait(HangingPage())
