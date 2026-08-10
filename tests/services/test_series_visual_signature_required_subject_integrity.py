from __future__ import annotations

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.article_concretization_prompt_compiler import (
    ArticleConcretizationPromptCompiler,
)


def _signature() -> SeriesVisualSignatureContract:
    return SeriesVisualSignatureContract(
        enabled=True,
        role="guide",
        profile=VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name="Dalmatian",
            identity_traits=("black spots", "black sunglasses"),
        ),
        max_area_ratio=0.18,
        participation_rule="Guide the reading path without replacing source subjects.",
    )


def test_long_required_subject_is_preserved_in_full_when_budget_allows() -> None:
    subject = "industrial assembly machine with emergency stop housing and conveyor guard"
    bundle = ArticleConcretizationPromptCompiler().compile_for_z_image(
        final_contract={
            "contract_id": "subject-integrity",
            "frame_id": "frame-1",
            "visible_text_policy": "no_visible_text",
            "required_subjects": [subject],
            "series_visual_signature": _signature().to_dict(),
            "article_concretization": {
                "diagram": {
                    "grammar": "process_flow",
                    "visual_metaphor": "production bottleneck",
                }
            },
        }
    )

    assert subject in bundle.positive_prompt
