import base64
import io
import json

import pytest
from PIL import Image

from pixelle_video.services.vision_capabilities import (
    detect_vision_capabilities,
    estimate_messages_text_tokens,
    redact_multimodal_messages_for_trace,
    validate_multimodal_image_limits,
)


def _data_url() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 1), (255, 255, 255)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def test_detect_vision_capabilities_defaults_unknown_to_unsupported():
    capabilities = detect_vision_capabilities(model="some-text-model")

    assert capabilities.supports_vision_messages is False
    assert capabilities.reason == "unknown_model"


def test_detect_vision_capabilities_supports_known_qwen_vl_model():
    capabilities = detect_vision_capabilities(model="qwen-vl-max")

    assert capabilities.supports_vision_messages is True
    assert capabilities.reason == "known_vision_model"


def test_detect_vision_capabilities_force_override_wins():
    capabilities = detect_vision_capabilities(
        model="deepseek-chat",
        force_supports_vision=True,
    )

    assert capabilities.supports_vision_messages is True
    assert capabilities.reason == "forced_by_config"


def test_redact_multimodal_messages_removes_data_url_base64():
    data_url = _data_url()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张参考图"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    redacted = redact_multimodal_messages_for_trace(messages)
    payload = json.dumps(redacted, ensure_ascii=False)

    assert "base64," not in payload
    assert "data:image" not in payload
    assert "<redacted:data-url>" in payload
    assert "sha256" in payload
    assert "byte_size" in payload
    assert "width" in payload
    assert estimate_messages_text_tokens(messages) > 0


def test_validate_multimodal_image_limits_rejects_remote_image_url():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述参考图"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/signed.png?token=secret",
                    },
                },
            ],
        }
    ]

    with pytest.raises(ValueError, match="remote image URLs are not supported"):
        validate_multimodal_image_limits(messages, max_image_size_mb=5)

    redacted = redact_multimodal_messages_for_trace(messages)
    payload = json.dumps(redacted, ensure_ascii=False)
    assert "secret" not in payload
    assert "signed.png" not in payload
    assert "<redacted:remote-image-url>" in payload
    assert "example.com" in payload


def test_validate_multimodal_image_limits_rejects_invalid_base64_data_url():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述参考图"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,not-valid"},
                },
            ],
        }
    ]

    with pytest.raises(ValueError, match="invalid vision image data URL"):
        validate_multimodal_image_limits(messages, max_image_size_mb=5)
