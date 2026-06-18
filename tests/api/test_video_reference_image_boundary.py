import pytest
from pydantic import ValidationError

from api.routers.video import build_video_generation_params
from api.schemas.video import VideoGenerateRequest


class _FakeReferenceImageStore:
    def resolve_reference_image_request(self, payload):
        assert payload == {"upload_id": "rimg_test", "analysis_mode": "auto", "workflow_injection_mode": "off"}
        return _FakeRecord()


class _FakeRecord:
    local_path = "/controlled/reference-image-store/rimg_test/upload.png"

    def to_trace_dict(self):
        return {
            "upload_id": "rimg_test",
            "artifact_id": "rimg_test",
            "sha256": "a" * 64,
            "source_kind": "api_upload",
        }


def test_video_generate_request_still_rejects_legacy_ref_image_path():
    with pytest.raises(ValidationError) as exc_info:
        VideoGenerateRequest.model_validate(
            {
                "text": "生成一个儿童故事",
                "ref_image": "/etc/passwd",
            }
        )

    message = str(exc_info.value)
    assert "ref_image" in message
    assert "Extra inputs are not permitted" in message


def test_video_generate_request_rejects_reference_image_server_path():
    with pytest.raises(ValidationError) as exc_info:
        VideoGenerateRequest.model_validate(
            {
                "text": "生成一个儿童故事",
                "reference_image": {"path": "/etc/passwd"},
            }
        )

    message = str(exc_info.value)
    assert "path" in message
    assert "Extra inputs are not permitted" in message


def test_video_generate_request_accepts_reference_upload_id_and_resolves_to_internal_ref_image():
    request = VideoGenerateRequest.model_validate(
        {
            "text": "生成一个儿童故事",
            "reference_image": {
                "upload_id": "rimg_test",
                "analysis_mode": "auto",
                "workflow_injection_mode": "off",
            },
        }
    )

    params = build_video_generation_params(
        request,
        request_id="req_test",
        reference_image_store=_FakeReferenceImageStore(),
    )

    assert params["reference_image_enabled"] is True
    assert params["ref_image"] == "/controlled/reference-image-store/rimg_test/upload.png"
    assert params["reference_image_analysis_mode"] == "auto"
    assert params["reference_image_workflow_injection_mode"] == "off"
    assert params["reference_image_api_source"]["upload_id"] == "rimg_test"


def test_video_generate_request_rejects_both_upload_and_artifact_id():
    with pytest.raises(ValidationError, match="exactly one"):
        VideoGenerateRequest.model_validate(
            {
                "text": "生成一个儿童故事",
                "reference_image": {
                    "upload_id": "rimg_a",
                    "artifact_id": "rimg_b",
                },
            }
        )
