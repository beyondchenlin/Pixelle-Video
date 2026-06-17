import pytest
from pydantic import ValidationError

from api.schemas.video import VideoGenerateRequest


@pytest.mark.parametrize(
    "field_name, field_value",
    [
        ("ref_image", "/etc/passwd"),
        ("reference_image", {"path": "/etc/passwd"}),
    ],
)
def test_video_generate_request_rejects_reference_image_entrypoints(field_name, field_value):
    with pytest.raises(ValidationError) as exc_info:
        VideoGenerateRequest.model_validate(
            {
                "text": "生成一个儿童故事",
                field_name: field_value,
            }
        )

    message = str(exc_info.value)
    assert field_name in message
    assert "Extra inputs are not permitted" in message
