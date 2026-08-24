import hashlib
import json

import pytest

from pixelle_video.services.prompt_trace_artifacts import (
    MEDIA_TRACE_RESULT_FILE_NAME,
    build_media_prompt_trace_context,
    build_workflow_params_trace,
    media_workflow_trace_context,
    require_media_prompt_trace_context,
    validate_media_prompt_trace_artifact,
    write_final_prompt_artifact,
    write_media_workflow_result_artifact,
    write_single_media_prompt_trace_context,
)


def test_write_final_prompt_artifact_persists_exact_media_prompts(tmp_path):
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task_123",
        frames=[
            {
                "index": 1,
                "prompt": "a precise image prompt\nwith a second line",
                "negative_prompt": "no text, no watermark",
            }
        ],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "selfhost/image_z_image_turbo.json",
            "style_source": "prompt_prefix_library",
            "ip_controls": {"series_visual_signature_enabled": True, "series_visual_signature_profile_id": "hero"},
        },
    )

    assert artifact_path.name == "final_visual_prompts.md"
    assert artifact_path.parent.name == "prompt_traces"
    content = artifact_path.read_text(encoding="utf-8")
    assert "# Final Visual Prompts" in content
    assert "Artifact schema: pixelle.final_visual_prompts.v1" in content
    assert "Task ID: task_123" in content
    assert "Frame count: 1" in content
    assert "## Generation Context" in content
    assert '"workflow": "selfhost/image_z_image_turbo.json"' in content
    assert '"series_visual_signature_profile_id": "hero"' in content
    assert "```text\na precise image prompt\nwith a second line\n```" in content
    assert "```text\nno text, no watermark\n```" in content


def test_build_media_prompt_trace_context_records_artifact_digest(tmp_path):
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task_123",
        frames=[
            {
                "index": 1,
                "prompt": "a precise image prompt",
                "negative_prompt": "",
            }
        ],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "selfhost/image_z_image_turbo.json",
            "media_type": "image",
        },
    )

    context = build_media_prompt_trace_context(
        artifact_path=artifact_path,
        task_id="task_123",
        prompt="a precise image prompt",
        workflow_context={
            "requested_workflow": None,
            "workflow": "selfhost/image_z_image_turbo.json",
        },
        media_type="image",
    )

    assert context["artifact_path"] == str(artifact_path)
    assert len(context["artifact_sha256"]) == 64
    assert context["workflow_input"] == "selfhost/image_z_image_turbo.json"


def test_build_media_prompt_trace_context_records_task_root(tmp_path):
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task_123",
        frames=[{"index": 1, "prompt": "a prompt", "negative_prompt": ""}],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "selfhost/image_z_image_turbo.json",
            "media_type": "image",
        },
    )

    context = build_media_prompt_trace_context(
        artifact_path=artifact_path,
        task_id="task_123",
        prompt="a prompt",
        workflow_context={"workflow": "selfhost/image_z_image_turbo.json"},
        media_type="image",
        task_root=tmp_path,
    )

    assert context["task_root"] == str(tmp_path.resolve())


def test_verbatim_prompt_trace_accepts_blank_and_proves_exact_integrity(tmp_path):
    prompt = "   \n"
    context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task_blank_prompt",
        prompt=prompt,
        workflow="selfhost/image_z_image_turbo.json",
        workflow_input="selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test.verbatim_passthrough",
        frame_id="frame-a",
        media_width=768,
        media_height=768,
        workflow_params={"prompt": prompt, "seed": 123},
        preserve_prompt_verbatim=True,
    )

    assert context["prompt"] == prompt
    assert context["preserve_prompt_verbatim"] is True
    assert context["prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    required = require_media_prompt_trace_context(
        context,
        prompt=prompt,
        media_type="image",
        width=768,
        height=768,
        negative_prompt="",
    )
    validate_media_prompt_trace_artifact(
        required,
        prompt=prompt,
        resolved_workflow="selfhost/image_z_image_turbo.json",
        resolved_workflow_input="selfhost/image_z_image_turbo.json",
        media_type="image",
        width=768,
        height=768,
        negative_prompt="",
        workflow_param_trace=build_workflow_params_trace(
            {"prompt": prompt, "seed": 123},
            prompt=prompt,
            preserve_prompt_verbatim=True,
        ),
    )


def test_verbatim_prompt_trace_rejects_whitespace_rewrite(tmp_path):
    context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task_prompt_integrity",
        prompt="  exact prompt\n",
        workflow="selfhost/image_z_image_turbo.json",
        media_type="image",
        source="test.verbatim_passthrough",
        preserve_prompt_verbatim=True,
    )

    with pytest.raises(ValueError, match="does not match media prompt"):
        require_media_prompt_trace_context(
            context,
            prompt="exact prompt",
            media_type="image",
        )


def test_build_workflow_params_trace_records_media_and_custom_text_inputs():
    trace = build_workflow_params_trace(
        {
            "prompt": "already traced final prompt",
            "negative_prompt": "already traced negative prompt",
            "image_prompt": "already traced final prompt",
            "text_prompt": "already traced final prompt",
            "video_prompt": "already traced final prompt",
            "media": "input-a.png",
            "input_media": "input-b.mp4",
            "goodstype": "travel mug",
            "width": 768,
            "height": 512,
            "second": 8,
        }
    )

    assert trace["workflow_param_inputs"] == {
        "goodstype": "travel mug",
        "input_media": "input-b.mp4",
        "media": "input-a.png",
        "second": "8",
    }
    assert len(trace["workflow_param_inputs_sha256"]) == 64


def test_build_workflow_params_trace_rejects_mismatched_prompt_aliases():
    with pytest.raises(ValueError, match="workflow prompt alias"):
        build_workflow_params_trace(
            {
                "prompt": "safe prompt",
                "image_prompt": "hidden prompt",
                "text_prompt": "safe prompt",
            },
            prompt="safe prompt",
        )


def test_build_workflow_params_trace_rejects_case_variant_prompt_aliases():
    with pytest.raises(ValueError, match="workflow prompt alias"):
        build_workflow_params_trace(
            {
                "prompt": "safe prompt",
                "Image_Prompt": "hidden prompt",
            },
            prompt="safe prompt",
        )


def test_build_workflow_params_trace_ignores_equal_case_variant_prompt_aliases():
    assert build_workflow_params_trace(
        {
            "Prompt": "safe prompt",
            "Image_Prompt": "safe prompt",
            "VIDEO_PROMPT": "safe prompt",
            "Positive_Prompt": "safe prompt",
        },
    ) == {}


def test_build_workflow_params_trace_rejects_mismatched_negative_prompt_aliases():
    with pytest.raises(ValueError, match="negative prompt alias"):
        build_workflow_params_trace(
            {
                "negative_prompt": "safe negative",
                "Negative_Prompt": "hidden negative",
            },
            prompt="safe prompt",
        )


def test_build_workflow_params_trace_ignores_equal_negative_prompt_aliases():
    assert build_workflow_params_trace(
        {
            "negative_prompt": "safe negative",
            "Negative_Prompt": "safe negative",
        },
        prompt="safe prompt",
    ) == {}


def test_build_workflow_params_trace_records_visual_generation_controls():
    trace = build_workflow_params_trace(
        {
            "prompt": "already traced final prompt",
            "negative_prompt": "already traced negative prompt",
            "width": 768,
            "height": 512,
            "duration": 4,
            "frame_rate": 16,
            "guidance": 3.5,
            "guidance_scale": 2,
            "steps": 20,
            "seed": 123,
            "cfg": 7,
            "sampler": "euler",
            "sampler_name": "uni_pc",
        }
    )

    assert trace["workflow_param_inputs"] == {
        "cfg": "7",
        "duration": "4",
        "frame_rate": "16",
        "guidance": "3.5",
        "guidance_scale": "2",
        "sampler": "euler",
        "sampler_name": "uni_pc",
        "seed": "123",
        "steps": "20",
    }
    assert len(trace["workflow_param_inputs_sha256"]) == 64


def test_build_workflow_params_trace_records_unknown_scalar_controls():
    trace = build_workflow_params_trace(
        {
            "prompt": "already traced final prompt",
            "control_weight": 0.8,
            "enable_refiner": False,
        }
    )

    assert trace["workflow_param_inputs"] == {
        "control_weight": "0.8",
        "enable_refiner": "False",
    }
    assert len(trace["workflow_param_inputs_sha256"]) == 64


def test_write_final_prompt_artifact_uses_expandable_fences_for_prompt_text(tmp_path):
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task_123",
        frames=[
            {
                "index": 1,
                "prompt": "prompt with a fenced sample\n```json\n{}\n```",
                "negative_prompt": "",
            }
        ],
        generation_context={
            "workflow": "selfhost/image_z_image_turbo.json",
            "workflow_input": "selfhost/image_z_image_turbo.json",
            "media_type": "image",
        },
    )

    content = artifact_path.read_text(encoding="utf-8")
    assert "````text\nprompt with a fenced sample" in content


def test_media_prompt_trace_artifacts_do_not_overwrite_multiple_calls_in_same_task(
    tmp_path,
):
    first_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task_123",
        prompt="first final prompt",
        workflow="selfhost/image_first.json",
        workflow_input="workflows/selfhost/image_first.json",
        media_type="image",
        source="test.first_call",
        workflow_params={"prompt": "first final prompt"},
    )
    second_context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task_123",
        prompt="second final prompt",
        workflow="selfhost/video_second.json",
        workflow_input="workflows/selfhost/video_second.json",
        media_type="video",
        source="test.second_call",
        workflow_params={"prompt": "second final prompt"},
    )

    first_artifact = first_context["artifact_path"]
    second_artifact = second_context["artifact_path"]

    first_artifact_path = first_artifact.replace("\\", "/")
    second_artifact_path = second_artifact.replace("\\", "/")

    assert first_artifact != second_artifact
    assert first_artifact_path.endswith("prompt_traces/final_visual_prompts.md")
    assert "/prompt_traces/c/" in second_artifact_path

    first_result = write_media_workflow_result_artifact(
        first_context,
        status="completed",
        result={"images": ["first.png"]},
    )
    second_result = write_media_workflow_result_artifact(
        second_context,
        status="completed",
        result={"videos": ["second.mp4"]},
    )

    assert first_result != second_result
    assert first_result.name == MEDIA_TRACE_RESULT_FILE_NAME
    assert second_result.name == MEDIA_TRACE_RESULT_FILE_NAME
    assert "first.png" in first_result.read_text(encoding="utf-8")
    assert "second.mp4" in second_result.read_text(encoding="utf-8")


def test_write_single_media_prompt_trace_context_uses_generation_workflow_file(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow_file = workflow_dir / "image_runninghub.json"
    workflow_file.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-image-123",
                "media_type": "image",
                "inputs": {
                    "prompt": "Describe {image} as a coherent final visual prompt"
                },
            }
        ),
        encoding="utf-8",
    )

    context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task-runninghub-web",
        prompt="final web prompt",
        workflow="rh-image-123",
        workflow_input="rh-image-123",
        media_type="image",
        source="web.pipeline",
        generation_context={
            "workflow_file": "workflows/runninghub/image_runninghub.json",
        },
        workflow_params={"prompt": "final web prompt"},
    )

    assert context["workflow"] == "rh-image-123"
    assert context["workflow_input"] == "rh-image-123"
    assert len(context["workflow_file_sha256"]) == 64
    assert context["workflow_prompt_literals"] == [
        {
            "path": "inputs.prompt",
            "key": "prompt",
            "sha256": hashlib.sha256(
                b"Describe {image} as a coherent final visual prompt"
            ).hexdigest(),
            "preview": "Describe {image} as a coherent final visual prompt",
        }
    ]
    assert len(context["workflow_prompt_literals_sha256"]) == 64


def test_media_result_artifacts_do_not_overwrite_reused_trace_context(tmp_path):
    context = write_single_media_prompt_trace_context(
        tmp_path,
        task_id="task_retry",
        prompt="retry final prompt",
        workflow="selfhost/image_retry.json",
        workflow_input="workflows/selfhost/image_retry.json",
        media_type="image",
        source="test.retry",
        workflow_params={"prompt": "retry final prompt"},
    )

    first_result = write_media_workflow_result_artifact(
        context,
        status="error",
        result={"error": "first attempt"},
    )
    second_result = write_media_workflow_result_artifact(
        context,
        status="completed",
        result={"images": ["second.png"]},
    )

    assert first_result.name == MEDIA_TRACE_RESULT_FILE_NAME
    assert second_result.name == "media_workflow_result-2.md"
    assert "first attempt" in first_result.read_text(encoding="utf-8")
    assert "second.png" in second_result.read_text(encoding="utf-8")


def test_media_workflow_trace_context_prefers_execution_identity_resolver():
    class _Media:
        def resolve_workflow_trace_context(self, *, workflow=None, media_type="image"):
            return {
                "workflow": "runninghub/image_z.json",
                "workflow_input": "rh-123",
                "workflow_source": "runninghub",
            }

        def resolve_workflow_key(self, *, workflow=None, media_type="image"):
            raise AssertionError("trace context resolver should be preferred")

    context = media_workflow_trace_context(
        _Media(),
        workflow="runninghub/image_z.json",
        media_type="image",
    )

    assert context["workflow"] == "runninghub/image_z.json"
    assert context["workflow_input"] == "rh-123"


def test_media_workflow_trace_context_fails_fast_when_workflow_cannot_be_resolved():
    class _Media:
        def resolve_workflow_key(self, *, workflow=None, media_type="image"):
            raise ValueError(f"bad workflow: {workflow}/{media_type}")

    with pytest.raises(ValueError, match="bad workflow"):
        media_workflow_trace_context(
            _Media(),
            workflow="missing.json",
            media_type="image",
        )


def test_media_workflow_trace_context_requires_workflow_resolver():
    with pytest.raises(ValueError, match="resolve_workflow_key"):
        media_workflow_trace_context(
            object(),
            workflow="selfhost/image_z_image_turbo.json",
            media_type="image",
        )
