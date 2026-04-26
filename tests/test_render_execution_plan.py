from pixelle_video.models.render_execution_plan import (
    RenderExecutionArtifact,
    RenderExecutionPlan,
)


def test_render_execution_plan_round_trips_backend_and_artifacts():
    plan = RenderExecutionPlan(
        requested_backend="ffmpeg_manifest",
        effective_backend="legacy",
        fallback_reason="template requires browser prerender",
        template_materialization_mode="html_prerender",
        element_motion_mode="python_ffmpeg",
        subtitle_mode="ass",
        audio_strategy="master_track",
        artifacts=[
            RenderExecutionArtifact(
                role="template_frame",
                path="frames/frame_000.png",
                frame_index=0,
            )
        ],
        diagnostics={"ffmpeg_supported": False},
    )
    restored = RenderExecutionPlan.from_dict(plan.to_dict())
    assert restored.requested_backend == "ffmpeg_manifest"
    assert restored.effective_backend == "legacy"
    assert restored.fallback_reason == "template requires browser prerender"
    assert restored.artifacts[0].role == "template_frame"
    assert restored.diagnostics["ffmpeg_supported"] is False
