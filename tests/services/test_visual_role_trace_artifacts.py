import json

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


def test_visual_role_trace_artifacts_write_structure_and_participation_decisions(tmp_path):
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_dir = str(tmp_path)
    ctx.planning_snapshot = {
        "visual_role_request": {"enabled": True},
        "visual_role_plan_by_frame": {
            "f1": {
                "version": "visual_role_integrated_prompt_plan.v4_2",
                "integrated_scene_prompt": "final integrated prompt",
                "structure_mode": "workflow",
                "participation_mode": "guide_explainer",
                "structure_decision": "Use a workflow structure.",
                "participation_decision": "The IP guides the workflow.",
            }
        },
    }

    pipeline = object.__new__(StandardPipeline)
    pipeline._write_visual_role_trace_artifacts(ctx)

    frame_artifacts = ctx.planning_snapshot["visual_role_artifacts"]["frames"]["f1"]
    structure_path = tmp_path / frame_artifacts["visual_role_structure_decision"]
    participation_path = tmp_path / frame_artifacts["visual_role_participation_decision"]

    structure_payload = json.loads(structure_path.read_text(encoding="utf-8"))
    participation_payload = json.loads(participation_path.read_text(encoding="utf-8"))

    assert structure_payload["visual_structure_mode"] == "workflow"
    assert structure_payload["structure_decision"] == "Use a workflow structure."
    assert participation_payload["visual_participation_mode"] == "guide_explainer"
    assert participation_payload["participation_decision"] == "The IP guides the workflow."
