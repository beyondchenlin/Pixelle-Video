import pytest
from aiohttp import ClientConnectorError

from pixelle_video.utils import tts_util


@pytest.mark.asyncio
async def test_edge_tts_retries_on_client_connector_error(monkeypatch):
    attempts = {"count": 0}
    connection_key = type(
        "ConnectionKey",
        (),
        {"ssl": None, "host": "speech.platform.bing.com", "port": 443},
    )()

    class FakeCommunicate:
        def __init__(self, **kwargs):
            pass

        async def stream(self):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ClientConnectorError(connection_key, OSError(64, "network name unavailable"))
            yield {"type": "audio", "data": b"pixelle"}

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(tts_util.edge_tts_sdk, "Communicate", FakeCommunicate)
    monkeypatch.setattr(tts_util.asyncio, "sleep", fake_sleep)

    audio = await tts_util.edge_tts("hello", retry_count=1)

    assert audio == b"pixelle"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_edge_tts_does_not_retry_on_output_write_timeout(monkeypatch):
    attempts = {"count": 0}

    class FakeCommunicate:
        def __init__(self, **kwargs):
            pass

        async def stream(self):
            attempts["count"] += 1
            yield {"type": "audio", "data": b"pixelle"}

    class FakeFile:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, _data):
            raise TimeoutError("disk write timed out")

    async def fake_sleep(_seconds):
        return None

    def fake_open(*args, **kwargs):
        return FakeFile()

    monkeypatch.setattr(tts_util.edge_tts_sdk, "Communicate", FakeCommunicate)
    monkeypatch.setattr(tts_util.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(tts_util, "_USE_CERTIFI_SSL", False)
    monkeypatch.setattr("builtins.open", fake_open)

    with pytest.raises(TimeoutError, match="disk write timed out"):
        await tts_util.edge_tts("hello", output_path="dummy.mp3", retry_count=1)

    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_list_voices_retries_on_client_connector_error(monkeypatch):
    attempts = {"count": 0}
    connection_key = type(
        "ConnectionKey",
        (),
        {"ssl": None, "host": "speech.platform.bing.com", "port": 443},
    )()

    async def fake_list_voices():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ClientConnectorError(connection_key, OSError(64, "network name unavailable"))
        return [
            {"Locale": "zh-CN", "ShortName": "zh-CN-YunjianNeural"},
            {"Locale": "en-US", "ShortName": "en-US-JennyNeural"},
        ]

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(tts_util.edge_tts_sdk, "list_voices", fake_list_voices)
    monkeypatch.setattr(tts_util.asyncio, "sleep", fake_sleep)

    voices = await tts_util.list_voices(locale="zh-CN", retry_count=1)

    assert voices == ["zh-CN-YunjianNeural"]
    assert attempts["count"] == 2
