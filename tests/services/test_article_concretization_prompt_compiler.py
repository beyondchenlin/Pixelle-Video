from __future__ import annotations

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.article_concretization_prompt_compiler import (
    ArticleConcretizationPromptCompiler,
)


def test_disabled_signature_positive_prompt_does_not_mention_character() -> None:
    bundle = ArticleConcretizationPromptCompiler().compile_for_z_image(
        final_contract={
            "contract_id": "contract_1",
            "frame_id": "frame_1",
            "visible_text_policy": "no_visible_text",
            "article_concretization": {
                "anchor": {"anchor_claim": "人物关系很难理解"},
                "diagram": {"grammar": "relationship_map", "visual_metaphor": "家族树图上的名字和名字列表"},
            },
        }
    )

    lower_prompt = bundle.positive_prompt.lower()
    assert "signature character" not in lower_prompt
    assert "mascot" not in lower_prompt
    assert "家族树图上的名字" not in bundle.positive_prompt
    assert "名字列表" not in bundle.positive_prompt
    assert "unlabeled" in bundle.positive_prompt


def test_enabled_signature_is_small_line_art_not_real_participant() -> None:
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        identity_traits=("black spots", "black sunglasses"),
    )
    signature = SeriesVisualSignatureContract(
        enabled=True,
        role="guide",
        profile=profile,
        max_area_ratio=0.18,
        participation_rule="Small guide points to the reading path.",
    )

    bundle = ArticleConcretizationPromptCompiler().compile_for_z_image(
        final_contract={
            "contract_id": "contract_1",
            "frame_id": "frame_1",
            "visible_text_policy": "no_visible_text",
            "series_visual_signature": signature,
            "article_concretization": {
                "anchor": {"anchor_claim": "人物关系很难理解"},
                "diagram": {"grammar": "relationship_map", "visual_metaphor": "unlabeled family tree"},
                "render": {"render_style": "xiaohei_handdrawn"},
            },
        }
    )

    assert "max 18% image area" in bundle.positive_prompt
    assert "not photorealistic" in bundle.positive_prompt
    assert "real in-scene participant" not in bundle.positive_prompt
