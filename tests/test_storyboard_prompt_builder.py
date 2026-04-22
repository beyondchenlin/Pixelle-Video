from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.utils.prompt_helper import assemble_storyboard_prompt
from pixelle_video.utils.style_resolution import normalize_storyboard_style


def _resolved_conflicting_ip_world() -> ResolvedStyleSpec:
    return ResolvedStyleSpec(
        style_kind="ip_world",
        prompt_template="{prompt}, same playful bird-universe silhouette",
        negative_prompt="photo realism, realistic fur",
        style_profile={
            "style_kind": "ip_world",
            "subject_policy": "keep_subject_semantics_but_restyle_into_world",
            "shape_language": "rounded geometric cartoon forms",
            "material": "clean game-like cartoon surface",
            "palette": "high saturation reds and yellows",
            "lighting": "dramatic rim light only",
            "world_elements": "destructible wooden obstacles and game-like props",
            "consistency_anchor": "all frames belong to the same playful bird universe",
            "negative_rules": "do not revert to realistic anatomy",
        },
        content_hash="hash-123",
        resolver_version="2026-04-21-v1",
        source_identity="request:hash-123",
        raw_content="different ip world",
    )


def _resolved_compatible_refinement() -> ResolvedStyleSpec:
    return ResolvedStyleSpec(
        style_kind="visual_only",
        prompt_template="{prompt}",
        negative_prompt="",
        style_profile={
            "style_kind": "visual_only",
            "subject_policy": "preserve_subject",
            "shape_language": "",
            "material": "",
            "palette": "",
            "lighting": "soft diagram glow",
            "world_elements": "",
            "consistency_anchor": "clean educational illustration finish",
            "negative_rules": "",
        },
        content_hash="hash-456",
        resolver_version="2026-04-21-v1",
        source_identity="request:hash-456",
        raw_content="clean educational illustration finish",
    )


def test_normalize_storyboard_style_drops_conflicting_world_identity_and_keeps_visual_suffix():
    normalized = normalize_storyboard_style(
        resolved_style=_resolved_conflicting_ip_world(),
        world_preset={
            "preset_id": "neutral_knowledge_storyboard",
            "display_name": "Neutral Knowledge Storyboard",
            "style_core": "clean educational illustration",
        },
    )

    assert normalized["classification"] == "conflicting_world_override"
    assert normalized["visual_suffix"]
    assert "dramatic rim light only" in normalized["visual_suffix"]
    assert "different ip world" not in normalized["visual_suffix"]
    assert "playful bird universe" not in normalized["visual_suffix"].lower()


def test_normalize_storyboard_style_keeps_compatible_refinement_suffix():
    normalized = normalize_storyboard_style(
        resolved_style=_resolved_compatible_refinement(),
        world_preset={
            "preset_id": "neutral_knowledge_storyboard",
            "display_name": "Neutral Knowledge Storyboard",
            "style_core": "clean educational illustration",
        },
    )

    assert normalized["classification"] == "compatible_refinement"
    assert normalized["visual_suffix"] == "soft diagram glow, clean educational illustration finish"


def test_assemble_storyboard_prompt_prefers_world_identity_over_conflicting_ip_prefix():
    prompt = assemble_storyboard_prompt(
        base_prompt="Liu Bei studies a strategy scroll",
        frame_plan={
            "shot_type": "medium_shot",
            "shot_purpose": "character_relationship",
            "world_elements": ["camp flag", "strategy board"],
        },
        world_preset={
            "display_name": "Angry Birds Three Kingdoms",
            "style_core": "playful bird-world history illustration",
        },
        normalized_style={
            "classification": "conflicting_world_override",
            "visual_suffix": "dramatic rim light only",
        },
    )

    assert "Angry Birds Three Kingdoms" in prompt
    assert "dramatic rim light only" in prompt
    assert "different ip world" not in prompt


def test_assemble_storyboard_prompt_includes_shot_language_and_world_elements():
    prompt = assemble_storyboard_prompt(
        base_prompt="host explainer introduces penicillin",
        frame_plan={
            "shot_type": "close_up",
            "shot_purpose": "detail_focus",
            "world_elements": ["lab bench", "culture dish"],
        },
        world_preset={
            "display_name": "Neutral Knowledge Storyboard",
            "style_core": "clean educational illustration",
        },
        normalized_style=None,
    )

    assert "close_up" in prompt
    assert "detail_focus" in prompt
    assert "lab bench" in prompt
    assert "culture dish" in prompt
