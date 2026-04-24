from pixelle_video.models.text_overlay import TextRenderingPolicy
from pixelle_video.services.text_overlay_planner import TextOverlayPlanner


def test_planner_limits_keyword_candidates_by_density_and_frame():
    policy = TextRenderingPolicy(
        image_text_mode="programmatic_only",
        enabled_targets=("hyperframes", "ass"),
        density="low",
        max_items_per_frame=1,
    )

    plan = TextOverlayPlanner().plan(
        narrations=["保持专注，稳定行动。", "及时复盘，持续优化。"],
        policy=policy,
    )

    assert plan.version == "text_overlay_plan.v1"
    assert len(plan.candidates) == 2
    assert [item.source["frame_index"] for item in plan.candidates] == [0, 1]
    assert all(item.role == "keyword" for item in plan.candidates)
    assert all(item.renderer_targets == ("hyperframes", "ass") for item in plan.candidates)


def test_planner_emits_native_candidates_only_when_policy_allows_native_prompt():
    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        density="medium",
        max_items_per_frame=2,
        allow_native_text_in_image=True,
    )

    plan = TextOverlayPlanner().plan(
        narrations=["把品牌名 Pixelle 放在画面中心。"],
        policy=policy,
    )

    assert [item.role for item in plan.candidates] == ["model_native_hint"]
    assert plan.candidates[0].renderer_targets == ("native_prompt",)
    assert plan.candidates[0].source["kind"] == "narration"
