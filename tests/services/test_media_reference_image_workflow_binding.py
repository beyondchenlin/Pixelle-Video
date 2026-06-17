import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.media import MediaResult
from pixelle_video.services import reference_image_workflow_binding as binding_module
from pixelle_video.services.media import MediaService
from pixelle_video.services.prompt_trace_artifacts import write_single_media_prompt_trace_context


class _FakeMediaService(MediaService):
    def __init__(self, config, core=None):
        super().__init__(config, core=core)
        self.captured_workflow_params = None

    def _resolve_workflow(self, *, workflow=None, workflow_domain=None):
        return {
            "key": workflow or "selfhost/image_reference.json",
            "source": "selfhost",
            "path": "/tmp/fake_workflow.json",
        }

    def _build_resolved_workflow_file_trace(self, workflow_info, workflow_input):
        return {}

    async def _execute_workflow(self, workflow_input, workflow_params, workflow_info, **kwargs):
        self.captured_workflow_params = dict(workflow_params)
        return SimpleNamespace(status="completed", images=["https://example.test/result.png"], videos=[], msg="")


def _write_reference_asset(task_dir: Path):
    image_dir = task_dir / "reference_image"
    image_dir.mkdir(parents=True)
    workflow_asset = image_dir / "workflow_abcd1234.jpg"
    workflow_asset.write_bytes(b"fake-image")
    (image_dir / "asset.json").write_text(
        json.dumps(
            {
                "version": "reference_image_asset/v1",
                "asset": {
                    "sha256": "a" * 64,
                    "mime_type": "image/jpeg",
                    "width": 100,
                    "height": 120,
                    "byte_size": len(b"fake-image"),
                    "workflow_asset_relative_path": "reference_image/workflow_abcd1234.jpg",
                    "task_asset_relative_path": "reference_image/original_abcd1234.jpg",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return workflow_asset


@pytest.mark.asyncio
async def test_media_service_injects_reference_image_and_records_safe_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=("reference_image",)),
    )
    workflow_asset = _write_reference_asset(tmp_path)
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "prompt_traces" / "c" / "frame_001",
        task_id="task",
        prompt="hello world",
        workflow="selfhost/image_reference.json",
        workflow_input="/tmp/fake_workflow.json",
        media_type="image",
        source="test",
        media_width=512,
        media_height=512,
        workflow_params={"prompt": "hello world", "width": 512, "height": 512, "index": 1},
    )
    service = _FakeMediaService(
        {
            "reference_image": {"workflow_injection_mode": "auto"},
            "comfyui": {},
        }
    )

    result = await service(
        prompt="hello world",
        workflow="selfhost/image_reference.json",
        media_type="image",
        width=512,
        height=512,
        index=1,
        media_prompt_trace_context=trace_context,
    )

    assert isinstance(result, MediaResult)
    assert service.captured_workflow_params["reference_image"] == str(workflow_asset.resolve())
    result_artifact = Path(trace_context["artifact_path"]).with_name("media_result.md")
    text = result_artifact.read_text(encoding="utf-8")
    assert "reference_image_workflow_binding" in text
    assert "workflow_abcd1234.jpg" in text
    assert str(workflow_asset.resolve()) not in text
    assert "base64," not in text


@pytest.mark.asyncio
async def test_media_service_required_injection_fails_when_asset_missing(tmp_path):
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "prompt_traces" / "c" / "frame_001",
        task_id="task",
        prompt="hello world",
        workflow="selfhost/image_reference.json",
        workflow_input="/tmp/fake_workflow.json",
        media_type="image",
        media_width=512,
        media_height=512,
        workflow_params={"prompt": "hello world", "width": 512, "height": 512},
        source="test",
    )
    service = _FakeMediaService(
        {
            "reference_image": {"workflow_injection_mode": "required"},
            "comfyui": {},
        }
    )

    with pytest.raises(ValueError, match="reference image workflow injection failed"):
        await service(
            prompt="hello world",
            workflow="selfhost/image_reference.json",
            media_type="image",
            width=512,
            height=512,
            media_prompt_trace_context=trace_context,
        )
