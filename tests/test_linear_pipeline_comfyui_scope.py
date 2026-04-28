from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from pixelle_video.pipelines.linear import LinearVideoPipeline


class _Core:
    def __init__(self):
        self.events = []
        self.llm = object()
        self.tts = object()
        self.media = object()
        self.video = object()

    @asynccontextmanager
    async def local_comfyui_task_scope(self):
        self.events.append("scope:enter")
        try:
            yield
        finally:
            self.events.append("scope:exit")


class _Pipeline(LinearVideoPipeline):
    async def setup_environment(self, ctx):
        self.core.events.append("setup")

    async def generate_content(self, ctx):
        self.core.events.append("content")

    async def determine_title(self, ctx):
        self.core.events.append("title")

    async def plan_visuals(self, ctx):
        self.core.events.append("visuals")

    async def initialize_storyboard(self, ctx):
        self.core.events.append("storyboard")

    async def produce_assets(self, ctx):
        self.core.events.append("assets")

    async def post_production(self, ctx):
        self.core.events.append("post")

    async def finalize(self, ctx):
        self.core.events.append("finalize")
        return SimpleNamespace(status="ok")


@pytest.mark.asyncio
async def test_linear_pipeline_wraps_full_lifecycle_in_local_comfyui_task_scope():
    core = _Core()
    pipeline = _Pipeline(core)

    result = await pipeline("topic")

    assert result.status == "ok"
    assert core.events == [
        "scope:enter",
        "setup",
        "content",
        "title",
        "visuals",
        "storyboard",
        "assets",
        "post",
        "finalize",
        "scope:exit",
    ]
