import hashlib
import json
from pathlib import Path

import pytest

from pixelle_video.models.direct_media import DirectMediaOutput
from pixelle_video.services.media import MediaService
from pixelle_video.services.prompt_trace_artifacts import (
    MEDIA_TRACE_MEDIA_RESULT_FILE_NAME,
    write_single_media_prompt_trace_context,
)


def _service() -> MediaService:
    return MediaService(
        {
            "comfyui": {
                "image": {
                    "default_workflow": "provider/image_openai_gpt_image.json"
                }
            },
            "direct_media": {
                "enabled": True,
                "openai_image": {
                    "enabled": True,
                    "api_key": "test-secret",
                },
            },
        }
    )


def _trace_context(media: MediaService, tmp_path: Path) -> dict:
    resolved = media.resolve_workflow_trace_context(
        workflow="provider/image_openai_gpt_image.json",
        media_type="image",
    )
    return write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-direct-media",
        prompt="a governed image prompt",
        workflow=resolved["workflow"],
        workflow_input=resolved["workflow_input"],
        media_type="image",
        source="test",
        frame_id="frame/1",
        media_width=800,
        media_height=600,
        workflow_params={
            "prompt": "a governed image prompt",
            "width": 800,
            "height": 600,
        },
        task_root=tmp_path,
    )


@pytest.mark.asyncio
async def test_direct_media_uses_existing_governance_and_result_boundary(
    monkeypatch,
    tmp_path,
):
    media = _service()
    trace_context = _trace_context(media, tmp_path)
    descriptor_bytes = Path(
        "workflows/provider/image_openai_gpt_image.json"
    ).read_bytes()
    assert trace_context["workflow_file_sha256"] == hashlib.sha256(
        descriptor_bytes
    ).hexdigest()
    captured = {}

    class FakeRegistry:
        async def generate(self, *, descriptor, request, config):
            captured.update(
                descriptor=descriptor,
                request=request,
                config=config,
            )
            request.output_dir.mkdir(parents=True)
            output_path = request.output_dir / "generated.png"
            output_path.write_bytes(b"provider-output")
            return DirectMediaOutput(
                media_type="image",
                local_path=output_path,
                provider_id=descriptor.provider_id,
                model=descriptor.model,
                request_id="req-safe",
                provider_metadata={"output_bytes": 15},
            )

        async def aclose(self):
            return None

    media._direct_media_registry = FakeRegistry()

    async def fail_comfy_execution(*_args, **_kwargs):
        raise AssertionError("provider workflows must not enter ComfyUI execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_comfy_execution)
    result = await media(
        prompt="a governed image prompt",
        workflow="provider/image_openai_gpt_image.json",
        media_type="image",
        width=800,
        height=600,
        media_prompt_trace_context=trace_context,
        _reference_image_workflow_binding_trace={},
    )

    assert result.model_dump() == {
        "media_type": "image",
        "url": str(captured["request"].output_dir / "generated.png"),
        "duration": None,
    }
    assert captured["descriptor"].provider_id == "openai_image"
    assert captured["request"].parameters == {}
    assert captured["config"].enabled is True
    assert captured["request"].output_dir == (
        tmp_path / "provider_media" / "frame_1"
    ).resolve()

    result_path = Path(trace_context["artifact_path"]).with_name(
        MEDIA_TRACE_MEDIA_RESULT_FILE_NAME
    )
    result_text = result_path.read_text(encoding="utf-8")
    assert '"source": "provider"' in result_text
    assert '"task_relative_path": "provider_media/frame_1/generated.png"' in result_text
    assert str(captured["request"].output_dir / "generated.png") not in result_text
    assert "test-secret" not in result_text


@pytest.mark.asyncio
async def test_direct_media_rejects_adapter_output_outside_task_scope(tmp_path):
    media = _service()
    task_root = tmp_path / "task"
    trace_context = _trace_context(media, task_root)
    escaped_path = tmp_path / "escaped-provider-output.png"
    escaped_path.write_bytes(b"escaped")

    class EscapingRegistry:
        async def generate(self, *, descriptor, **_kwargs):
            return DirectMediaOutput(
                media_type="image",
                local_path=escaped_path,
                provider_id=descriptor.provider_id,
                model=descriptor.model,
            )

        async def aclose(self):
            return None

    media._direct_media_registry = EscapingRegistry()
    with pytest.raises(RuntimeError, match="escaped its task-scoped output directory"):
        await media(
            prompt="a governed image prompt",
            workflow="provider/image_openai_gpt_image.json",
            media_type="image",
            width=800,
            height=600,
            media_prompt_trace_context=trace_context,
            _reference_image_workflow_binding_trace={},
        )


def test_provider_workflow_listing_is_json_serializable_and_contains_no_secrets():
    media = _service()
    workflows = media.list_workflows()
    provider_workflow = next(
        item
        for item in workflows
        if item["key"] == "provider/image_openai_gpt_image.json"
    )
    serialized = json.dumps(provider_workflow, ensure_ascii=False)

    assert provider_workflow["source"] == "provider"
    assert provider_workflow["media_type"] == "image"
    assert provider_workflow["model"] == "gpt-image-1"
    assert "api_key" not in serialized
    assert "test-secret" not in serialized
