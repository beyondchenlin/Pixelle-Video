from __future__ import annotations

import pytest

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.services import image_prompt_composer as composer_module
from pixelle_video.services.image_prompt_composer import ImagePromptComposer


def _storyboard_plan() -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="A worker operates a machine.",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="A worker operates a machine.",
                visual_goal="show the production process",
                prompt_intent="explain the bottleneck",
                frame_id="frame-1",
            )
        ],
    )


@pytest.mark.asyncio
async def test_prompt_composer_records_shadow_report_without_replacing_production_prompt(
    monkeypatch,
) -> None:
    production_prompt = "production prompt selected by the current execution path"
    captured_shadow = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return StyledImagePromptBatch(
            prompts=[production_prompt],
            negative_prompt=None,
            resolved_style=None,
            planning_snapshot={"existing": True},
        )

    class FakeShadowReport:
        enabled = True

        def to_dict(self):
            return {
                "schema_version": "series_visual_signature_shadow.v1",
                "ready_for_cutover": False,
                "frames": [{"frame_id": "frame-1", "candidate_prompt": "candidate"}],
            }

    def fake_shadow_report(**kwargs):
        captured_shadow.update(kwargs)
        return FakeShadowReport()

    monkeypatch.setattr(
        composer_module,
        "generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )
    monkeypatch.setattr(
        composer_module,
        "build_series_visual_signature_shadow_report",
        fake_shadow_report,
    )

    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    result = await ImagePromptComposer().compose(
        llm_service=None,
        storyboard_plan=_storyboard_plan(),
        image_config={},
        series_visual_signature_request=request,
    )

    assert result.prompts == [production_prompt]
    assert captured_shadow["production_prompts"] == [production_prompt]
    assert captured_shadow["frame_ids"] == ["frame-1"]
    assert captured_shadow["request"] is request
    fallback_context = captured_shadow["fallback_frame_contexts"]["frame-1"]
    assert fallback_context["frame_source_text"] == "A worker operates a machine."
    assert fallback_context["visual_goal"] == "show the production process"
    assert result.planning_snapshot["existing"] is True
    assert (
        result.planning_snapshot["series_visual_signature_shadow_comparison"][
            "frames"
        ][0]["candidate_prompt"]
        == "candidate"
    )
