from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    RenderedMediaPrompt,
)
from pixelle_video.models.storyboard_plan import (
    StoryboardCountMode,
    StoryboardGenerationMode,
    StoryboardPlan,
    StoryboardPlanFrame,
)
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle


def test_prompt_plan_stores_contract_sections_only():
    plan = StoryboardPlan(
        plan_id="plan",
        source_digest="41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d",
        source_text="source",
        revision=1,
        mode=StoryboardGenerationMode.SMART,
        count_mode=StoryboardCountMode.AUTO,
        requested_scene_count=None,
        resolved_scene_count=1,
        frames=(
            StoryboardPlanFrame(
                frame_id="frame-1",
                index=1,
                source_text="source",
                visual_goal="visual",
                prompt_intent="intent",
                shot_type="medium shot",
                shot_purpose="show scene",
                primary_subject="teacher",
                secondary_subjects=(),
                continuity_anchors=(),
                world_elements=(),
                source_start=0,
                source_end=6,
                metadata={},
            ),
        ),
    )
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style assignment",
        character_layer_style="character layer",
        world_layer_style="world layer",
        integration_priority="priority",
    )
    rendered = RenderedMediaPrompt(
        prompt="final prompt",
        negative_prompt=None,
        prompt_contract=contract,
        renderer_id="test",
        renderer_version="v1",
    )
    bundle = build_prompt_plan_bundle(storyboard_plan=plan, rendered_prompts=(rendered,))
    sections = bundle.prompt_plans[0].prompt_sections
    assert "generated_prompt" not in sections
    assert "source_text" not in sections
    assert set(sections) == set(contract.prompt_sections())
