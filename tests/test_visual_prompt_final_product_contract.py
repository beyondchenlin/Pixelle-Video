from types import SimpleNamespace

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle
from pixelle_video.utils.prompt_helper import (
    assemble_image_prompt,
    assemble_storyboard_prompt,
    sanitize_visual_prompt_text,
)


def test_assemble_storyboard_prompt_returns_fused_scene_language_not_block_list():
    frame_plan = SimpleNamespace(
        shot_type="medium_shot",
        shot_purpose="establish_market_space",
        world_elements=("ancient gate", "morning market"),
    )

    prompt = assemble_storyboard_prompt(
        base_prompt=(
            "A white rabbit guide with a blue tie stands beside the tea stall, "
            "naturally pointing visitors toward the old city gate."
        ),
        frame_plan=frame_plan,
        world_preset={
            "display_name": "Neutral Knowledge Storyboard",
            "style_core": "clean educational illustration",
        },
        normalized_style=None,
    )

    assert not prompt.startswith("Neutral Knowledge Storyboard,")
    assert "medium_shot" not in prompt
    assert "establish_market_space" not in prompt
    assert "shot_type" not in prompt
    assert "shot_purpose" not in prompt
    assert "clean educational illustration" in prompt
    assert "ancient gate" in prompt
    assert "morning market" in prompt
    assert "white rabbit guide with a blue tie" in prompt


def test_assemble_storyboard_prompt_excludes_neutral_workflow_display_name():
    prompt = assemble_storyboard_prompt(
        base_prompt="A host explains penicillin beside a lab bench.",
        frame_plan={
            "shot_type": "close_up",
            "shot_purpose": "detail_focus",
            "world_elements": ("culture dish",),
        },
        world_preset={
            "display_name": "Neutral Knowledge Storyboard",
            "style_core": "clean educational illustration",
        },
        normalized_style=None,
    )

    assert "Neutral Knowledge Storyboard" not in prompt
    assert "close_up" not in prompt
    assert "detail_focus" not in prompt
    assert "framed as close up, detail focus" in prompt
    assert "rendered as clean educational illustration" in prompt


def test_assemble_storyboard_prompt_excludes_neutral_preset_id_display_name():
    prompt = assemble_storyboard_prompt(
        base_prompt="A teacher explains a science diagram.",
        frame_plan={
            "shot_type": "medium_shot",
            "shot_purpose": "concept_context",
            "world_elements": ("chalkboard",),
        },
        world_preset={
            "preset_id": "neutral_knowledge_storyboard",
            "display_name": "Clean Classroom",
            "style_core": "clean educational illustration",
        },
        normalized_style=None,
    )

    assert "Clean Classroom" not in prompt
    assert "neutral_knowledge_storyboard" not in prompt
    assert "set in the Clean Classroom world" not in prompt
    assert "rendered as clean educational illustration" in prompt


def test_assemble_storyboard_prompt_preserves_branded_world_identity_semantically():
    prompt = assemble_storyboard_prompt(
        base_prompt="Liu Bei studies a strategy scroll.",
        frame_plan={
            "shot_type": "medium_shot",
            "shot_purpose": "character_relationship",
            "world_elements": ("camp flag", "strategy board"),
        },
        world_preset={
            "display_name": "Angry Birds Three Kingdoms",
            "style_core": "playful bird-world history illustration",
        },
        normalized_style=None,
    )

    assert not prompt.startswith("Angry Birds Three Kingdoms,")
    assert "Angry Birds Three Kingdoms" in prompt
    assert "set in the Angry Birds Three Kingdoms world" in prompt
    assert "medium_shot" not in prompt
    assert "character_relationship" not in prompt
    assert "framed as medium shot, character relationship" in prompt


def test_assemble_storyboard_prompt_preserves_branded_preset_id_display_name():
    prompt = assemble_storyboard_prompt(
        base_prompt="Liu Bei studies a strategy scroll.",
        frame_plan={
            "shot_type": "medium_shot",
            "shot_purpose": "character_relationship",
            "world_elements": ("camp flag", "strategy board"),
        },
        world_preset={
            "preset_id": "angry_birds_three_kingdoms",
            "display_name": "Angry Birds Three Kingdoms",
            "style_core": "playful bird-world history illustration",
        },
        normalized_style=None,
    )

    assert "set in the Angry Birds Three Kingdoms world" in prompt
    assert "Angry Birds Three Kingdoms" in prompt
    assert "angry_birds_three_kingdoms" not in prompt


def test_assemble_image_prompt_uses_resolved_style_template_without_raw_prefix_append():
    resolved_style = ResolvedStyleSpec(
        style_kind="visual_only",
        source_identity="test",
        raw_content="raw watercolor prefix that should not be appended",
        prompt_template="warm watercolor scene: {prompt}, soft hand-painted texture",
        negative_prompt="",
        style_profile={"style_kind": "visual_only"},
    )

    prompt = assemble_image_prompt(
        "A rabbit guide walks through a quiet morning market.",
        raw_prefix="raw watercolor prefix that should not be appended",
        resolved_style=resolved_style,
    )

    assert prompt == (
        "warm watercolor scene: A rabbit guide walks through a quiet morning market., "
        "soft hand-painted texture"
    )
    assert prompt.count("raw watercolor prefix") == 0


def test_assemble_image_prompt_uses_hybrid_template_without_raw_prefix_append():
    resolved_style = ResolvedStyleSpec(
        style_kind="hybrid",
        source_identity="test",
        raw_content="raw hybrid prefix that should not be appended",
        prompt_template="hybrid story-world treatment: {prompt}, cohesive character style",
        negative_prompt="",
        style_profile={"style_kind": "hybrid"},
    )

    prompt = assemble_image_prompt(
        "A rabbit guide walks through a quiet morning market.",
        raw_prefix="raw hybrid prefix that should not be appended",
        resolved_style=resolved_style,
    )

    assert prompt == (
        "hybrid story-world treatment: A rabbit guide walks through a quiet morning market., "
        "cohesive character style"
    )
    assert prompt.count("raw hybrid prefix") == 0


def test_assemble_image_prompt_without_resolved_style_does_not_append_raw_prefix():
    prompt = assemble_image_prompt(
        "A rabbit guide walks through a quiet morning market.",
        raw_prefix="raw prefix must not be appended",
        resolved_style=None,
    )

    assert prompt == "A rabbit guide walks through a quiet morning market."
    assert "raw prefix" not in prompt


def test_assemble_image_prompt_without_template_uses_structured_style_profile():
    resolved_style = ResolvedStyleSpec(
        style_kind="ip_world",
        source_identity="test",
        raw_content="Angry Birds style must not be appended",
        prompt_template="",
        negative_prompt="",
        style_profile={
            "style_kind": "ip_world",
            "shape_language": "rounded geometric cartoon forms",
            "material": "clean game-like cartoon surface",
            "palette": "high saturation reds and yellows",
            "lighting": "bright playful lighting",
            "world_elements": "destructible wooden obstacles and game-like props",
            "consistency_anchor": "all frames belong to the same playful bird universe",
        },
    )

    prompt = assemble_image_prompt(
        "A rabbit guide walks through a quiet morning market.",
        raw_prefix="Angry Birds style must not be appended",
        resolved_style=resolved_style,
    )

    assert prompt.startswith("A rabbit guide walks through a quiet morning market.")
    assert "rounded geometric cartoon forms" in prompt
    assert "destructible wooden obstacles" in prompt
    assert "Angry Birds style" not in prompt


def test_prompt_plan_final_prompt_matches_generated_visual_prompt():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="The guide introduces the old city gate.",
        visual_goal="show a coherent travel illustration",
        prompt_intent="visualize the guide and gate in one image",
        primary_subject="old city gate",
    )
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="The guide introduces the old city gate.",
        frames=[frame],
        plan_id="plan_1",
    )
    final_prompt = (
        "A white rabbit guide with a blue tie points toward the old city gate "
        "inside a warm educational illustration."
    )

    bundle = build_prompt_plan_bundle(
        storyboard_plan=plan,
        image_prompts=(final_prompt,),
        planning_snapshot={},
    )

    assert bundle.image_prompt_drafts[0].prompt_text == final_prompt
    assert bundle.prompt_plans[0].final_prompt == final_prompt


def test_sanitize_visual_prompt_text_removes_ip_adaptation_field_label():
    prompt = sanitize_visual_prompt_text(
        'ip_adaptation: white rabbit guide, "identity_anchors_visible": blue tie'
    )

    assert "ip_adaptation" not in prompt
    assert "white rabbit guide" in prompt
