import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.media import MediaService
from pixelle_video.services.prompt_trace_artifacts import (
    MEDIA_TRACE_MEDIA_RESULT_FILE_NAME,
    build_media_prompt_trace_context,
    build_workflow_params_trace,
    write_final_prompt_artifact,
    write_single_media_prompt_trace_context,
)
from pixelle_video.workflow_content_contracts import build_workflow_file_trace


def _trace_context(**overrides):
    workflow_file_trace = build_workflow_file_trace(
        "selfhost/image_z_image_turbo.json",
        "workflows/selfhost/image_z_image_turbo.json",
    )
    context = {
        "artifact_path": "traces/final_visual_prompts.md",
        "task_id": "task-media-trace",
        "prompt": "final visual prompt",
        "workflow": "selfhost/image_z_image_turbo.json",
        "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
        "media_type": "image",
        "media_width": 768,
        "media_height": 512,
        "artifact_sha256": "0" * 64,
        **workflow_file_trace,
    }
    context.update(overrides)
    return context


@pytest.mark.asyncio
async def test_media_service_writes_result_artifact_for_completed_workflow(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    workflow_params = {
        "prompt": "final visual prompt",
        "width": 768,
        "height": 512,
    }
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-result",
        prompt="final visual prompt",
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="workflows/selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
        workflow_params=workflow_params,
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fake_execute_workflow(*_args, **kwargs):
        assert kwargs["media_prompt_trace_context"] == trace_context
        return SimpleNamespace(
            status="completed",
            images=["generated.png"],
            outputs={"node": {"image": "generated.png"}},
        )

    monkeypatch.setattr(media, "_execute_workflow", fake_execute_workflow)

    result = await media(
        prompt="final visual prompt",
        workflow="selfhost/image_z_image_turbo.json",
        media_type="image",
        width=768,
        height=512,
        media_prompt_trace_context=trace_context,
    )

    result_path = Path(trace_context["artifact_path"]).with_name(
        MEDIA_TRACE_MEDIA_RESULT_FILE_NAME
    )
    result_text = result_path.read_text(encoding="utf-8")

    assert result.url == "generated.png"
    assert "pixelle.media_result.v1" in result_text
    assert str(trace_context["artifact_sha256"]) in result_text
    assert "generated.png" in result_text


@pytest.mark.asyncio
async def test_media_service_rejects_media_generation_without_prompt_trace_context(monkeypatch):
    media = MediaService({"comfyui": {"image": {}}})

    def fail_if_workflow_resolves(*_args, **_kwargs):
        raise AssertionError("media prompt trace must be checked before workflow execution")

    monkeypatch.setattr(media, "_resolve_workflow", fail_if_workflow_resolves)

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
        )


@pytest.mark.asyncio
async def test_media_service_rejects_prompt_trace_context_with_wrong_media_type(monkeypatch):
    media = MediaService({"comfyui": {"image": {}}})

    def fail_if_workflow_resolves(*_args, **_kwargs):
        raise AssertionError("media type mismatch must be rejected before workflow resolution")

    monkeypatch.setattr(media, "_resolve_workflow", fail_if_workflow_resolves)

    with pytest.raises(ValueError, match="media type"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="video",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(media_type="image"),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_prompt_trace_context_with_wrong_media_size(monkeypatch):
    media = MediaService({"comfyui": {"image": {}}})

    def fail_if_workflow_resolves(*_args, **_kwargs):
        raise AssertionError("media size mismatch must be rejected before workflow resolution")

    monkeypatch.setattr(media, "_resolve_workflow", fail_if_workflow_resolves)

    with pytest.raises(ValueError, match="media_width"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=1024,
            height=512,
            media_prompt_trace_context=_trace_context(media_width=768),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_prompt_trace_context_with_missing_artifact(monkeypatch, tmp_path):
    media = MediaService({"comfyui": {"image": {}}})
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("missing prompt artifact must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact_path"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=tmp_path / "prompt_traces" / "final_visual_prompts.md"
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_prompt_trace_context_when_artifact_does_not_contain_prompt(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-trace",
        prompt="other prompt",
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="workflows/selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
    )
    trace_context["prompt"] = "final visual prompt"
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("mismatched prompt artifact must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact prompt"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=trace_context,
        )


@pytest.mark.asyncio
async def test_media_service_rejects_prompt_trace_context_when_artifact_hash_mismatches(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Frame 1",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("mismatched prompt artifact hash must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact_sha256"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256="0" * 64,
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_spoofed_non_final_prompt_artifact(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "spoof.txt"
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "workflow: selfhost/image_z_image_turbo.json",
                "media_type: image",
                "media_width: 768",
                "media_height: 512",
                "Positive prompt:",
                "```text",
                "final visual prompt",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("spoofed prompt artifact must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="final_visual_prompts.md"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_with_schema_only_inside_json_context(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"note": "Artifact schema: pixelle.final_visual_prompts.v1", "workflow": "selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Frame 1",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("spoofed schema location must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact header"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_with_header_lines_inside_prompt_block(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Frame 1",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("spoofed header lines must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact header"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_with_matching_debug_context_only(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                (
                    '{"request": {"media_workflow": "wrong-workflow", "media_type": '
                    '"video", "media_width": 1024, "media_height": 768}, '
                    '"debug": {"workflow": "selfhost/image_z_image_turbo.json", '
                    '"workflow_input": "selfhost/image_z_image_turbo.json", '
                    '"media_type": "image", "media_width": 768, "media_height": 512}}'
                ),
                "```",
                "",
                "## Frame 1",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                "",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("debug-only workflow context must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact workflow"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_runninghub_artifact_without_execution_workflow_id(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-trace",
        prompt="final visual prompt",
        workflow="runninghub/image_z.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "runninghub",
            "key": "runninghub/image_z.json",
            "path": "workflows/runninghub/image_z.json",
            "workflow_id": "rh-123",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("runninghub workflow_id mismatch must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="workflow_input"):
        await media(
            prompt="final visual prompt",
            workflow="runninghub/image_z.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=trace_context,
        )


@pytest.mark.asyncio
async def test_media_service_rejects_runninghub_descriptor_without_workflow_file_trace(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "image_runninghub.json"
    workflow_path.write_text(
        '{"source":"runninghub","workflow_id":"rh-image-123","media_type":"image"}',
        encoding="utf-8",
    )
    prompt = "final visual prompt"
    workflow_params = {"prompt": prompt}
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-runninghub-missing-file-trace",
        frames=[
            {
                "index": 1,
                "prompt": prompt,
                "negative_prompt": "",
            }
        ],
        generation_context={
            "source": "test",
            "workflow": "runninghub/image_runninghub.json",
            "workflow_input": "rh-image-123",
            "media_type": "image",
        },
    )
    trace_context = build_media_prompt_trace_context(
        artifact_path=artifact_path,
        task_id="task-runninghub-missing-file-trace",
        prompt=prompt,
        workflow_context={
            "requested_workflow": "runninghub/image_runninghub.json",
            "workflow": "runninghub/image_runninghub.json",
            "workflow_input": "rh-image-123",
        },
        media_type="image",
        workflow_param_trace=build_workflow_params_trace(workflow_params, prompt=prompt),
    )
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("descriptor-backed media service must require workflow file trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed
    media = MediaService({"comfyui": {"image": {}}}, core=core)

    with pytest.raises(ValueError, match="workflow file trace"):
        await media(
            prompt=prompt,
            workflow="runninghub/image_runninghub.json",
            media_type="image",
            media_prompt_trace_context=trace_context,
        )


@pytest.mark.asyncio
async def test_core_media_entrypoint_rejects_descriptor_without_workflow_file_trace(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "image_runninghub.json"
    workflow_path.write_text(
        '{"source":"runninghub","workflow_id":"rh-image-123","media_type":"image"}',
        encoding="utf-8",
    )
    prompt = "final visual prompt"
    workflow_params = {"prompt": prompt}
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-core-runninghub-missing-file-trace",
        frames=[
            {
                "index": 1,
                "prompt": prompt,
                "negative_prompt": "",
            }
        ],
        generation_context={
            "source": "test",
            "workflow": "runninghub/image_runninghub.json",
            "workflow_input": "rh-image-123",
            "media_type": "image",
        },
    )
    trace_context = build_media_prompt_trace_context(
        artifact_path=artifact_path,
        task_id="task-core-runninghub-missing-file-trace",
        prompt=prompt,
        workflow_context={
            "requested_workflow": "runninghub/image_runninghub.json",
            "workflow": "runninghub/image_runninghub.json",
            "workflow_input": "rh-image-123",
        },
        media_type="image",
        workflow_param_trace=build_workflow_params_trace(workflow_params, prompt=prompt),
    )
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("core media execution must require workflow file trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="workflow file trace"):
        await core._execute_media_comfykit_workflow(
            "rh-image-123",
            workflow_params,
            workflow_source="runninghub",
            media_service_domain="image",
            media_prompt_trace_context=trace_context,
            media_type="image",
            resolved_workflow="runninghub/image_runninghub.json",
        )


@pytest.mark.asyncio
async def test_core_media_entrypoint_rejects_forged_workflow_file_trace(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "image_runninghub.json"
    workflow_path.write_text(
        '{"source":"runninghub","workflow_id":"rh-image-123","media_type":"image"}',
        encoding="utf-8",
    )
    prompt = "final visual prompt"
    workflow_params = {"prompt": prompt}
    forged_trace = {
        "workflow_file_sha256": "f" * 64,
        "workflow_prompt_literals": [],
        "workflow_prompt_literals_sha256": "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
    }
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-core-runninghub-forged-file-trace",
        frames=[
            {
                "index": 1,
                "prompt": prompt,
                "negative_prompt": "",
            }
        ],
        generation_context={
            "source": "test",
            "workflow": "runninghub/image_runninghub.json",
            "workflow_input": "rh-image-123",
            "media_type": "image",
            **forged_trace,
        },
    )
    trace_context = build_media_prompt_trace_context(
        artifact_path=artifact_path,
        task_id="task-core-runninghub-forged-file-trace",
        prompt=prompt,
        workflow_context={
            "requested_workflow": "runninghub/image_runninghub.json",
            "workflow": "runninghub/image_runninghub.json",
            "workflow_input": "rh-image-123",
        },
        media_type="image",
        workflow_param_trace=build_workflow_params_trace(workflow_params, prompt=prompt),
        workflow_file_trace=forged_trace,
    )
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("core media execution must reject forged workflow file trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="workflow file trace"):
        await core._execute_media_comfykit_workflow(
            "rh-image-123",
            workflow_params,
            workflow_source="runninghub",
            media_service_domain="image",
            media_prompt_trace_context=trace_context,
            media_type="image",
            resolved_workflow="runninghub/image_runninghub.json",
            workflow_file_trace=forged_trace,
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_negative_prompt_mismatch(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-trace",
        prompt="final visual prompt",
        negative_prompt="artifact negative",
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="workflows/selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
    )
    trace_context["negative_prompt"] = "call negative"
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("negative prompt mismatch must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact negative prompt"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            negative_prompt="call negative",
            media_prompt_trace_context=trace_context,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alias_params",
    [
        {"Negative_Prompt": "hidden negative payload"},
        {"negative": "hidden negative payload"},
        {"negative_image_prompt": "hidden negative payload"},
        {"negative_video_prompt": "hidden negative payload"},
    ],
)
async def test_media_service_rejects_negative_prompt_alias_params(
    monkeypatch,
    tmp_path,
    alias_params,
):
    media = MediaService({"comfyui": {"image": {}}})
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-trace",
        prompt="final visual prompt",
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="workflows/selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("negative prompt aliases must be rejected before execution")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="prompt alias"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=trace_context,
            **alias_params,
        )


def test_workflow_params_trace_rejects_empty_canonical_negative_alias_bypass():
    with pytest.raises(ValueError, match="negative prompt alias"):
        build_workflow_params_trace(
            {
                "prompt": "final visual prompt",
                "negative_prompt": "",
                "negative_image_prompt": "hidden negative payload",
            },
            prompt="final visual prompt",
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_top_level_context_conflict(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-media-trace",
        frames=[
            {
                "index": 1,
                "frame_id": "1",
                "prompt": "final visual prompt",
                "negative_prompt": "",
            }
        ],
        generation_context={
            "workflow": "selfhost/wrong_image_workflow.json",
            "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
            "media_type": "image",
            "media_width": 768,
            "media_height": 512,
            "request": {
                "workflow": "selfhost/image_z_image_turbo.json",
            },
        },
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("artifact top-level conflict must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact workflow"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_nested_request_context_conflict(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-media-trace",
        frames=[
            {
                "index": 1,
                "frame_id": "1",
                "prompt": "final visual prompt",
                "negative_prompt": "",
            }
        ],
        generation_context={
            "source": "test",
            "request": {
                "workflow": "selfhost/image_z_image_turbo.json",
                "media_workflow": "selfhost/wrong_image_workflow.json",
                "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
                "media_type": "image",
                "media_width": 768,
                "media_height": 512,
            },
        },
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("nested request workflow conflict must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact workflow"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_nested_request_conflict_when_top_level_matches(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-media-trace",
        frames=[
            {
                "index": 1,
                "frame_id": "1",
                "prompt": "final visual prompt",
                "negative_prompt": "",
            }
        ],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
            "media_type": "image",
            "media_width": 768,
            "media_height": 512,
            "request": {
                "workflow": "selfhost/image_z_image_turbo.json",
                "media_workflow": "selfhost/wrong_image_workflow.json",
                "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
                "media_type": "image",
                "media_width": 768,
                "media_height": 512,
            },
        },
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("nested request conflict must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact workflow"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_nested_request_workflow_param_trace_conflict(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    actual_trace = build_workflow_params_trace(
        {"prompt": "final visual prompt", "image": "expected.png"},
        prompt="final visual prompt",
    )
    hidden_trace = build_workflow_params_trace(
        {"prompt": "final visual prompt", "image": "hidden.png"},
        prompt="final visual prompt",
    )
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-media-trace",
        frames=[
            {
                "index": 1,
                "frame_id": "1",
                "prompt": "final visual prompt",
                "negative_prompt": "",
            }
        ],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
            "media_type": "image",
            "media_width": 768,
            "media_height": 512,
            **actual_trace,
            "request": {
                "workflow": "selfhost/image_z_image_turbo.json",
                "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
                "media_type": "image",
                "media_width": 768,
                "media_height": 512,
                **hidden_trace,
            },
        },
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("nested request workflow params must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="workflow_param_inputs"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            image="expected.png",
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                **actual_trace,
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_untraced_visual_generation_controls(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-trace",
        prompt="final visual prompt",
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="workflows/selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("untraced generation controls must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="workflow_param_inputs"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            steps=20,
            seed=123,
            cfg=7,
            sampler="euler",
            media_prompt_trace_context=trace_context,
        )


@pytest.mark.asyncio
async def test_media_service_rejects_untraced_nested_visual_controls(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    trace_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-media-nested-control",
        prompt="final visual prompt",
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="workflows/selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("untraced nested controls must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="workflow_param_inputs"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            control={"image": "untraced.png", "strength": 0.9},
            media_prompt_trace_context=trace_context,
        )


@pytest.mark.asyncio
async def test_media_service_rejects_duplicate_prompt_artifact_when_frame_id_mismatches(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    workflow_file_trace = build_workflow_file_trace(
        "selfhost/image_z_image_turbo.json",
        "workflows/selfhost/image_z_image_turbo.json",
    )
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task-media-trace",
        frames=[
            {
                "index": 1,
                "frame_id": "frame-a",
                "prompt": "same visual prompt",
                "negative_prompt": "same negative prompt",
            },
            {
                "index": 2,
                "frame_id": "frame-b",
                "prompt": "same visual prompt",
                "negative_prompt": "same negative prompt",
            },
        ],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "workflows/selfhost/image_z_image_turbo.json",
            "media_type": "image",
            "media_width": 768,
            "media_height": 512,
            **workflow_file_trace,
        },
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("frame_id mismatch must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="artifact frame_id"):
        await media(
            prompt="same visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            negative_prompt="same negative prompt",
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                frame_id="frame-c",
                prompt="same visual prompt",
                negative_prompt="same negative prompt",
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_artifact_when_frame_count_header_mismatches_blocks(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "workflow_input": "workflows/selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Frame 1",
                "",
                "Frame ID: frame-a",
                "",
                "Positive prompt:",
                "",
                "```text",
                "same visual prompt",
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                "",
                "```",
                "",
                "## Frame 2",
                "",
                "Frame ID: frame-b",
                "",
                "Positive prompt:",
                "",
                "```text",
                "same visual prompt",
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                "",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("frame count mismatch must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="frame count"):
        await media(
            prompt="same visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                frame_id="frame-b",
                prompt="same visual prompt",
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_generation_context_hidden_inside_prompt_block(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Frame 1",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "````text",
                "final visual prompt",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "workflow_input": "selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "````",
                "",
                "Negative prompt:",
                "",
                "```text",
                "",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("hidden generation context must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="generation context"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_positive_prompt_outside_frame_section(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Audit Note",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("positive prompt outside frame section must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="unexpected section"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_non_numeric_frame_heading(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "workflow_input": "workflows/selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Frame banana",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                "",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("non-numeric frame heading must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="unexpected section"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                prompt="final visual prompt",
            ),
        )


@pytest.mark.asyncio
async def test_media_service_rejects_duplicate_prompt_label_inside_frame(
    monkeypatch,
    tmp_path,
):
    media = MediaService({"comfyui": {"image": {}}})
    artifact_path = tmp_path / "prompt_traces" / "final_visual_prompts.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        "\n".join(
            [
                "# Final Visual Prompts",
                "",
                "Artifact schema: pixelle.final_visual_prompts.v1",
                "Task ID: task-media-trace",
                "Frame count: 1",
                "",
                "## Generation Context",
                "",
                "```json",
                '{"workflow": "selfhost/image_z_image_turbo.json", "workflow_input": "workflows/selfhost/image_z_image_turbo.json", "media_type": "image", "media_width": 768, "media_height": 512}',
                "```",
                "",
                "## Frame 1",
                "",
                "Frame ID: 1",
                "",
                "Positive prompt:",
                "",
                "```text",
                "final visual prompt",
                "```",
                "",
                "Positive prompt:",
                "",
                "```text",
                "spoofed prompt",
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                "",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        media,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo.json",
            "path": "workflows/selfhost/image_z_image_turbo.json",
        },
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("duplicate prompt label must be rejected")

    monkeypatch.setattr(media, "_execute_workflow", fail_if_executed)

    with pytest.raises(ValueError, match="duplicated"):
        await media(
            prompt="final visual prompt",
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
            width=768,
            height=512,
            media_prompt_trace_context=_trace_context(
                artifact_path=artifact_path,
                artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                prompt="final visual prompt",
            ),
        )
