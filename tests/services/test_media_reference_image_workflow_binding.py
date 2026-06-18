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


def _write_reference_asset(task_dir: Path, *, relative_path="reference_image/workflow_abcd1234.jpg"):
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
                    "workflow_asset_relative_path": relative_path,
                    "task_asset_relative_path": "reference_image/original_abcd1234.jpg",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return workflow_asset


def _write_trace_context(tmp_path: Path, *, workflow_params=None, task_root=None):
    return write_single_media_prompt_trace_context(
        tmp_path / "prompt_traces" / "c" / "frame_001",
        task_id="task",
        prompt="hello world",
        workflow="selfhost/image_reference.json",
        workflow_input="/tmp/fake_workflow.json",
        media_type="image",
        source="test",
        media_width=512,
        media_height=512,
        workflow_params=workflow_params or {"prompt": "hello world", "width": 512, "height": 512, "index": 1},
        task_root=task_root if task_root is not None else tmp_path,
    )


def _latest_media_result_text(task_dir: Path) -> str:
    candidates = sorted(task_dir.rglob("media_result.md"), key=lambda path: path.stat().st_mtime)
    assert candidates, "expected media_result.md"
    return candidates[-1].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_media_service_injects_reference_image_and_records_safe_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=("reference_image",)),
    )
    workflow_asset = _write_reference_asset(tmp_path)
    trace_context = _write_trace_context(tmp_path)
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
    result_text = _latest_media_result_text(tmp_path)
    assert "reference_image_workflow_binding" in result_text
    assert "workflow_abcd1234.jpg" in result_text
    assert str(workflow_asset.resolve()) not in result_text
    assert "base64," not in result_text

    prompt_trace_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("final_visual_prompts.md"))
    assert "reference_image" in prompt_trace_text
    assert "workflow_asset_relative_path" in prompt_trace_text
    assert str(workflow_asset.resolve()) not in prompt_trace_text


@pytest.mark.asyncio
async def test_reference_asset_relative_path_cannot_escape_task_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=("reference_image",)),
    )
    secret = tmp_path.parent / "secret.jpg"
    secret.write_bytes(b"secret")
    _write_reference_asset(tmp_path, relative_path="../secret.jpg")
    trace_context = _write_trace_context(tmp_path)
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

    assert service.captured_workflow_params is None


@pytest.mark.asyncio
async def test_media_service_rejects_trace_task_root_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=("reference_image",)),
    )
    _write_reference_asset(tmp_path)
    wrong_root = tmp_path / "other_task"
    wrong_root.mkdir()
    trace_context = _write_trace_context(tmp_path, task_root=wrong_root)
    service = _FakeMediaService(
        {
            "reference_image": {"workflow_injection_mode": "required"},
            "comfyui": {},
        }
    )

    with pytest.raises(ValueError, match="task_root must contain artifact_path"):
        await service(
            prompt="hello world",
            workflow="selfhost/image_reference.json",
            media_type="image",
            width=512,
            height=512,
            index=1,
            media_prompt_trace_context=trace_context,
        )

    assert service.captured_workflow_params is None


@pytest.mark.asyncio
async def test_media_service_request_injection_mode_overrides_config_off(monkeypatch, tmp_path):
    monkeypatch.setattr(
        binding_module,
        "get_workflow_capabilities",
        lambda workflow_info: SimpleNamespace(reference_image_param_names=("reference_image",)),
    )
    workflow_asset = _write_reference_asset(tmp_path)
    trace_context = _write_trace_context(tmp_path)
    service = _FakeMediaService(
        {
            "reference_image": {"workflow_injection_mode": "off"},
            "comfyui": {},
        }
    )

    await service(
        prompt="hello world",
        workflow="selfhost/image_reference.json",
        media_type="image",
        width=512,
        height=512,
        reference_image_workflow_injection_mode="auto",
        media_prompt_trace_context=trace_context,
    )

    assert service.captured_workflow_params["reference_image"] == str(workflow_asset.resolve())


@pytest.mark.asyncio
async def test_media_service_required_injection_fails_when_asset_missing(tmp_path):
    trace_context = _write_trace_context(
        tmp_path,
        workflow_params={"prompt": "hello world", "width": 512, "height": 512},
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
