from pixelle_video.services.visual_profile_registry import resolve_visual_profile
from pixelle_video.services.visual_prompt_profile_projector import (
    VISUAL_PROFILE_PROMPT_MARKER,
    apply_visual_profile_to_prompt,
    merge_negative_prompt,
)
from pixelle_video.services.visual_quality_gate import VisualQualityGate


def test_resolve_builtin_visual_profile_and_project_prompt():
    profile = resolve_visual_profile(profile_id="article_cognitive_illustration")
    prompt = apply_visual_profile_to_prompt(
        "a simple metaphor scene",
        profile=profile,
        frame_context={"visual_goal": "解释抽象概念"},
        frame_index=0,
    )
    assert VISUAL_PROFILE_PROMPT_MARKER in prompt
    assert "cognitive anchor" in prompt
    assert "解释抽象概念" in prompt


def test_visual_quality_gate_repairs_missing_profile_terms():
    profile = resolve_visual_profile(profile_id="xiaohei_article_illustration")
    report = VisualQualityGate(enabled=True, strict=False).evaluate_prompts(
        ["a black hand drawn creature pushing a stone"],
        profile=profile,
    )
    assert report.passed
    assert report.issues
    assert report.repair_clauses_by_frame[0]


def test_merge_negative_prompt_dedupes_rules():
    merged = merge_negative_prompt("PPT, dense text", ["dense text", "infographic"])
    assert merged == "PPT, dense text, infographic"
