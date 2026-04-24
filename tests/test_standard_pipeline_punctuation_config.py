import pytest

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


@pytest.mark.asyncio
async def test_generate_content_uses_configured_preserve_natural_punctuation_default(monkeypatch):
    captured = {}

    class _FakeCore:
        config = {
            "render": {
                "timing": {
                    "preserve_natural_punctuation": False,
                },
            },
        }
        llm = object()
        tts = None
        media = None
        video = None

    async def fake_generate_narrations_from_topic(*args, **kwargs):
        captured["preserve_natural_punctuation"] = kwargs["preserve_natural_punctuation"]
        return ["narration"]

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_narrations_from_topic",
        fake_generate_narrations_from_topic,
    )

    pipeline = StandardPipeline(_FakeCore())
    ctx = PipelineContext(input_text="topic", params={"mode": "generate"})

    await pipeline.generate_content(ctx)

    assert captured["preserve_natural_punctuation"] is False
