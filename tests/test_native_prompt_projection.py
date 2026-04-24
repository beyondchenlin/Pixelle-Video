from pixelle_video.models.text_overlay import (
    TextOverlayCandidate,
    TextOverlayPlan,
    TextRenderingPolicy,
)
from pixelle_video.services.native_prompt_projection import NativePromptProjection


def test_projection_only_uses_native_prompt_candidates_and_limits_per_frame():
    plan = TextOverlayPlan(
        candidates=(
            TextOverlayCandidate(
                id="native-1",
                text="Pixelle",
                role="model_native_hint",
                renderer_targets=("native_prompt",),
                source={"frame_index": 0},
            ),
            TextOverlayCandidate(
                id="native-2",
                text="Extra",
                role="model_native_hint",
                renderer_targets=("native_prompt",),
                source={"frame_index": 0},
            ),
            TextOverlayCandidate(
                id="overlay-1",
                text="稳定",
                role="keyword",
                renderer_targets=("hyperframes",),
                source={"frame_index": 0},
            ),
        )
    )
    policy = TextRenderingPolicy(
        image_text_mode="native_hint",
        enabled_targets=("native_prompt",),
        allow_native_text_in_image=True,
        max_items_per_frame=1,
    )

    projected = NativePromptProjection().project(plan=plan, policy=policy)

    assert list(projected.keys()) == [0]
    assert projected[0][0].prompt_fragment == 'render the planned text "Pixelle"'
    assert projected[0][0].source_candidate_ids == ("native-1",)


def test_projection_returns_empty_when_policy_disallows_native_prompt():
    plan = TextOverlayPlan(
        candidates=(
            TextOverlayCandidate(
                id="native-1",
                text="Pixelle",
                role="model_native_hint",
                renderer_targets=("native_prompt",),
                source={"frame_index": 0},
            ),
        )
    )
    policy = TextRenderingPolicy(
        image_text_mode="programmatic_only",
        enabled_targets=("hyperframes",),
    )

    assert NativePromptProjection().project(plan=plan, policy=policy) == {}
