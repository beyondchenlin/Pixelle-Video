import json

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


def test_series_visual_signature_trace_artifacts_write_structure_and_participation_decisions(tmp_path):
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_dir = str(tmp_path)
    ctx.planning_snapshot = {
        "series_visual_signature_request": {"enabled": True},
        "series_visual_signature_plan_by_frame": {
            "f1": {
                "version": "series_visual_signature_integrated_prompt_plan.v4_2",
                "integrated_scene_prompt": "final integrated prompt",
                "structure_mode": "workflow",
                "participation_mode": "guide_explainer",
                "structure_decision": "Use a workflow structure.",
                "participation_decision": "The IP guides the workflow.",
            }
        },
    }

    pipeline = object.__new__(StandardPipeline)
    pipeline._write_series_visual_signature_trace_artifacts(ctx)

    frame_artifacts = ctx.planning_snapshot["series_visual_signature_artifacts"]["frames"]["f1"]
    structure_path = tmp_path / frame_artifacts["series_visual_signature_structure_decision"]
    participation_path = tmp_path / frame_artifacts["series_visual_signature_participation_decision"]

    structure_payload = json.loads(structure_path.read_text(encoding="utf-8"))
    participation_payload = json.loads(participation_path.read_text(encoding="utf-8"))

    assert structure_payload["series_visual_signature_structure_mode"] == "workflow"
    assert structure_payload["structure_decision"] == "Use a workflow structure."
    assert participation_payload["series_visual_signature_participation_mode"] == "guide_explainer"
    assert participation_payload["participation_decision"] == "The IP guides the workflow."


def test_visual_anchor_two_stage_writes_every_stage_and_generation_request(tmp_path):
    frame = {
        "frame_id": "frame-a",
        "content_stage_input": {"original_storyboard_text": "原始分镜"},
        "content_stage_output": {"pure_content_prompt": "纯内容画面"},
        "fusion_stage_input": {"identity_profile": {"profile_id": "bird-v1"}},
        "fusion_stage_output": {"selected_fusion_method": "唯一实体"},
        "preflight_review_input": {"frame_id": "frame-a"},
        "preflight_review_output": {"decision": "pass"},
        "generation_request": {"random_seed": 2026082201},
    }
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_dir = str(tmp_path)
    ctx.planning_snapshot = {
        "visual_anchor_two_stage": {
            "schema_version": "visual_anchor_two_stage_batch.v1",
            "prompt_versions": {
                "content_stage": "visual_anchor_content_stage.v1",
                "fusion_stage": "visual_anchor_fusion_stage.v1",
                "preflight_review": "visual_anchor_preflight_review.v1",
            },
            "frames": [frame],
        },
        "identity_reference_workflow_inspection": {"workflow_key": "z-reference"},
        "visual_anchor_generation_request_by_frame": {
            "frame-a": frame["generation_request"]
        },
    }

    pipeline = object.__new__(StandardPipeline)
    pipeline._write_series_visual_signature_trace_artifacts(ctx)

    record = ctx.planning_snapshot["visual_anchor_two_stage_artifacts"]
    assert set(record["frames"]["frame-a"]) == {
        "content_stage_input",
        "content_stage_output",
        "fusion_stage_input",
        "fusion_stage_output",
        "preflight_review_input",
        "preflight_review_output",
        "generation_request",
    }
    for relative_path in record["frames"]["frame-a"].values():
        assert (tmp_path / relative_path).is_file()
    generation_request = json.loads(
        (
            tmp_path
            / record["frames"]["frame-a"]["generation_request"]
        ).read_text(encoding="utf-8")
    )
    assert generation_request["random_seed"] == 2026082201
