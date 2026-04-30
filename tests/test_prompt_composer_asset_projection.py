from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.prompt_composer import apply_scene_cast_to_prompt_plan


def build_prompt_plan() -> PromptPlan:
    return PromptPlan(
        prompt_plan_id="prompt_plan_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_1",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
        source_trace_id="trace_1",
        metadata={"source": "stage1a"},
    )


def build_scene_cast(**overrides) -> SceneCast:
    params = {
        "scene_cast_id": "cast_frame_1",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "asset_bible_id": "bible_demo",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
    }
    params.update(overrides)
    return SceneCast(**params)


def test_apply_scene_cast_to_prompt_plan_returns_new_plan_with_reserved_asset_fields():
    original = build_prompt_plan()
    scene_cast = build_scene_cast()

    projected = apply_scene_cast_to_prompt_plan(original, scene_cast)

    assert projected is not original
    assert projected.character_ids == ("char_luna",)
    assert projected.scene_id == "scene_lab"
    assert projected.prop_ids == ("prop_compass",)
    assert projected.style_id == "style_warm_comic"
    assert projected.prompt_plan_id == original.prompt_plan_id
    assert projected.storyboard_plan_id == original.storyboard_plan_id
    assert projected.frame_id == original.frame_id
    assert projected.image_prompt_draft_id == original.image_prompt_draft_id
    assert projected.prompt_sections == original.prompt_sections
    assert projected.final_prompt == original.final_prompt
    assert projected.metadata["scene_cast_id"] == "cast_frame_1"
    assert projected.metadata["asset_bible_id"] == "bible_demo"
    assert original.character_ids == ()
    assert original.scene_id is None
    assert original.prop_ids == ()
    assert original.style_id is None


def test_apply_scene_cast_to_prompt_plan_rejects_mismatched_frame_identity():
    original = build_prompt_plan()
    scene_cast = build_scene_cast(frame_id="frame_0002")

    try:
        apply_scene_cast_to_prompt_plan(original, scene_cast)
    except ValueError as exc:
        assert "frame_id" in str(exc)
    else:
        raise AssertionError("mismatched frame_id must be rejected")


def test_apply_scene_cast_to_prompt_plan_rejects_mismatched_storyboard_identity():
    original = build_prompt_plan()
    scene_cast = build_scene_cast(storyboard_plan_id="storyboard_plan_2")

    try:
        apply_scene_cast_to_prompt_plan(original, scene_cast)
    except ValueError as exc:
        assert "storyboard_plan_id" in str(exc)
    else:
        raise AssertionError("mismatched storyboard_plan_id must be rejected")

