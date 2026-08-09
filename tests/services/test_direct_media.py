import asyncio
import base64
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from pixelle_video.config.schema import DirectMediaConfig
from pixelle_video.models.direct_media import (
    DirectMediaDescriptor,
    DirectMediaOutput,
    DirectMediaRequest,
)
from pixelle_video.services.direct_media import (
    DirectMediaConfigurationError,
    DirectMediaProviderRegistry,
    DirectMediaResponseError,
    load_direct_media_descriptor,
)


def _descriptor() -> DirectMediaDescriptor:
    return load_direct_media_descriptor(
        Path("workflows/provider/image_openai_gpt_image.json")
    )


def _png_bytes(*, width: int = 16, height: int = 12) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _request(tmp_path: Path, **overrides) -> DirectMediaRequest:
    values = {
        "workflow_key": "provider/image_openai_gpt_image.json",
        "prompt": "a safe image prompt",
        "media_type": "image",
        "model": "gpt-image-1",
        "output_dir": tmp_path,
        "width": 800,
        "height": 600,
        "parameters": {},
    }
    values.update(overrides)
    return DirectMediaRequest(**values)


def _config(**provider_overrides) -> DirectMediaConfig:
    return DirectMediaConfig(
        enabled=True,
        openai_image={
            "enabled": True,
            "api_key": "test-secret",
            **provider_overrides,
        },
    )


class _FakeImages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.images = _FakeImages(response)
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_openai_image_adapter_is_lazy_reused_bounded_and_closed(
    monkeypatch,
    tmp_path,
):
    encoded = base64.b64encode(_png_bytes()).decode("ascii")
    response = SimpleNamespace(
        data=[SimpleNamespace(b64_json=encoded)],
        _request_id="req_test-1",
        usage={"input_tokens": 11, "output_tokens": 22, "ignored": "text"},
    )
    client = _FakeClient(response)
    created = []

    def fake_create_client(settings):
        created.append(settings)
        return client

    monkeypatch.setenv("PIXELLE_PROXY_MODE", "direct")
    monkeypatch.setattr(
        "pixelle_video.services.direct_media.create_openai_client",
        fake_create_client,
    )
    registry = DirectMediaProviderRegistry()
    assert created == []

    first = await registry.generate(
        descriptor=_descriptor(),
        request=_request(tmp_path / "first"),
        config=_config(),
    )
    second = await registry.generate(
        descriptor=_descriptor(),
        request=_request(tmp_path / "second"),
        config=_config(),
    )

    assert len(created) == 1
    assert first.local_path.is_file()
    assert second.local_path.is_file()
    assert first.local_path != second.local_path
    assert first.provider_metadata == {
        "actual_width": 16,
        "actual_height": 12,
        "format": "png",
        "output_bytes": len(_png_bytes()),
        "requested_size": "1536x1024",
        "usage": {"input_tokens": 11, "output_tokens": 22},
    }
    assert client.images.calls[0] == {
        "prompt": "a safe image prompt",
        "model": "gpt-image-1",
        "n": 1,
        "response_format": "b64_json",
        "size": "1536x1024",
        "output_format": "png",
        "background": "auto",
        "quality": "auto",
    }
    assert "test-secret" not in repr(client.images.calls)

    await registry.aclose()
    assert client.closed is True


@pytest.mark.asyncio
async def test_openai_image_adapter_rejects_remote_url_without_downloading(
    monkeypatch,
    tmp_path,
):
    client = _FakeClient(
        SimpleNamespace(data=[SimpleNamespace(url="https://example.test/image.png")])
    )
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "direct")
    monkeypatch.setattr(
        "pixelle_video.services.direct_media.create_openai_client",
        lambda _settings: client,
    )
    registry = DirectMediaProviderRegistry()

    with pytest.raises(DirectMediaResponseError, match="remote URL"):
        await registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path),
            config=_config(),
        )
    assert list(tmp_path.glob("**/*")) == []
    await registry.aclose()


@pytest.mark.asyncio
async def test_openai_image_adapter_rejects_invalid_or_oversized_output(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "direct")
    responses = [
        SimpleNamespace(data=[SimpleNamespace(b64_json="not-base64!")]),
        SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(
                        _png_bytes(width=20, height=20)
                    ).decode()
                )
            ]
        ),
    ]
    clients = [_FakeClient(response) for response in responses]
    monkeypatch.setattr(
        "pixelle_video.services.direct_media.create_openai_client",
        lambda _settings: clients.pop(0),
    )

    invalid_registry = DirectMediaProviderRegistry()
    with pytest.raises(DirectMediaResponseError, match="invalid base64"):
        await invalid_registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path / "invalid"),
            config=_config(),
        )
    await invalid_registry.aclose()

    pixel_registry = DirectMediaProviderRegistry()
    with pytest.raises(DirectMediaResponseError, match="pixel limits"):
        await pixel_registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path / "pixels"),
            config=_config(max_output_pixels=100),
        )
    await pixel_registry.aclose()


@pytest.mark.asyncio
async def test_registry_validates_contract_before_adapter_creation(tmp_path):
    created = []

    def factory():
        created.append(True)
        raise AssertionError("invalid input must fail before adapter creation")

    registry = DirectMediaProviderRegistry({"openai_image": factory})
    with pytest.raises(DirectMediaConfigurationError, match="unsupported"):
        await registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path, parameters={"secret_option": "value"}),
            config=_config(),
        )
    assert created == []


@pytest.mark.asyncio
async def test_registry_close_waits_for_in_flight_generation(tmp_path):
    started = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()

    class BlockingAdapter:
        async def generate(self, *, request, **_kwargs):
            started.set()
            await release.wait()
            request.output_dir.mkdir(parents=True, exist_ok=True)
            output = request.output_dir / "generated.png"
            output.write_bytes(_png_bytes())
            return DirectMediaOutput(
                media_type="image",
                local_path=output,
                provider_id="openai_image",
                model="gpt-image-1",
            )

        async def aclose(self):
            closed.set()

    registry = DirectMediaProviderRegistry({"openai_image": BlockingAdapter})
    generation = asyncio.create_task(
        registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path),
            config=_config(),
        )
    )
    await started.wait()
    closing = asyncio.create_task(registry.aclose())
    await asyncio.sleep(0)
    assert closed.is_set() is False

    release.set()
    await generation
    await closing
    assert closed.is_set() is True
    with pytest.raises(RuntimeError, match="closed"):
        await registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path / "late"),
            config=_config(),
        )


def test_direct_media_descriptor_rejects_unsafe_or_ambiguous_contracts():
    base = _descriptor().model_dump(mode="json")

    with pytest.raises(ValidationError, match="credential"):
        DirectMediaDescriptor.model_validate(
            {**base, "declared_params": {"api_key": {"type": "string"}}}
        )
    with pytest.raises(ValidationError, match="unsupported type"):
        DirectMediaDescriptor.model_validate(
            {**base, "declared_params": {"mode": {"type": "object"}}}
        )
    with pytest.raises(ValidationError, match="unique"):
        DirectMediaDescriptor.model_validate(
            {
                **base,
                "declared_params": {
                    "mode": {"type": "string", "enum": ["a", "a"]}
                },
                "defaults": {"mode": "a"},
            }
        )
    with pytest.raises(ValidationError, match="must be one of"):
        DirectMediaDescriptor.model_validate(
            {
                **base,
                "declared_params": {
                    "mode": {"type": "string", "enum": ["a", "b"]}
                },
                "defaults": {"mode": "c"},
            }
        )


def test_direct_media_request_requires_complete_dimensions(tmp_path):
    descriptor = _descriptor()
    assert descriptor.normalize_parameters({"quality": "high"})["quality"] == "high"
    with pytest.raises(ValueError, match="positive integer"):
        _request(tmp_path, width=0)


def test_descriptor_loader_does_not_expose_invalid_secret_inputs(tmp_path):
    descriptor = _descriptor().model_dump(mode="json")
    descriptor["declared_params"] = {"api_key": {"type": "string"}}
    descriptor["defaults"] = {"api_key": "must-not-leak"}
    descriptor_path = tmp_path / "unsafe.json"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DirectMediaConfigurationError) as captured:
        load_direct_media_descriptor(descriptor_path)

    assert "must-not-leak" not in str(captured.value)
    assert str(captured.value) == "direct media descriptor validation failed: unsafe.json"


@pytest.mark.asyncio
async def test_openai_image_adapter_rejects_invalid_requests_before_network_resolution(
    monkeypatch,
    tmp_path,
):
    async def fail_settings(_config):
        raise AssertionError("invalid requests must fail before transport resolution")

    monkeypatch.setattr(
        "pixelle_video.services.direct_media._openai_image_client_settings",
        fail_settings,
    )
    registry = DirectMediaProviderRegistry()

    with pytest.raises(DirectMediaConfigurationError, match="provided together"):
        await registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path / "dimensions", height=None),
            config=_config(),
        )
    with pytest.raises(DirectMediaConfigurationError, match="transparent"):
        await registry.generate(
            descriptor=_descriptor(),
            request=_request(
                tmp_path / "format",
                parameters={"background": "transparent", "output_format": "jpeg"},
            ),
            config=_config(),
        )
    with pytest.raises(DirectMediaConfigurationError, match="disabled"):
        await registry.generate(
            descriptor=_descriptor(),
            request=_request(tmp_path / "disabled"),
            config=DirectMediaConfig(),
        )

    await registry.aclose()
