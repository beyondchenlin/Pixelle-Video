import pytest

from pixelle_video.pipelines.custom import CustomPipeline


class _FakeCore:
    def __getattr__(self, name):
        return None


@pytest.mark.asyncio
async def test_custom_pipeline_is_disabled_to_avoid_legacy_per_frame_audio_path():
    pipeline = CustomPipeline(_FakeCore())

    with pytest.raises(RuntimeError, match="standard pipeline"):
        await pipeline(text="scene one")
