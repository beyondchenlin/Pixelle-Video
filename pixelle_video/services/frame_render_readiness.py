from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Final

FRAME_RENDER_READY_SCRIPT: Final[str] = """
async () => {
    const fontReady = document.fonts && document.fonts.ready
        ? document.fonts.ready.catch(() => undefined)
        : Promise.resolve();

    const imageReady = Array.from(document.images || []).map((img) => {
        if (img.complete) {
            return Promise.resolve();
        }
        if (typeof img.decode === "function") {
            return img.decode().catch(() => undefined);
        }
        return new Promise((resolve) => {
            img.addEventListener("load", resolve, { once: true });
            img.addEventListener("error", resolve, { once: true });
        });
    });

    await Promise.all([fontReady, ...imageReady]);
    await new Promise((resolve) => requestAnimationFrame(resolve));
    await new Promise((resolve) => requestAnimationFrame(resolve));
}
"""


class FrameRenderReadinessTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class FrameRenderReadiness:
    navigation_wait_until: str = "domcontentloaded"
    navigation_timeout_ms: int = 30_000
    ready_timeout_ms: int = 30_000
    ready_script: str = FRAME_RENDER_READY_SCRIPT

    async def wait(self, page: Any) -> None:
        try:
            await asyncio.wait_for(
                page.evaluate(self.ready_script),
                timeout=self.ready_timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            raise FrameRenderReadinessTimeoutError(
                "HTML render readiness timed out after "
                f"{self.ready_timeout_ms}ms while waiting for fonts, images, "
                "and animation frames."
            ) from exc
