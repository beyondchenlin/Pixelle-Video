from __future__ import annotations

from pixelle_video.models.final_visual_prompt_contract_v45 import (
    FinalVisualPromptContractV45,
)
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.article_concretization_prompt_compiler import (
    ArticleConcretizationPromptCompiler,
)
from pixelle_video.services.visual_entity_placement_planner import (
    VisualEntityPlacementPlanner,
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
    signature = _signature()
    article = {
        "diagram": {
            "grammar": "process_flow",
            "visual_metaphor": "production bottleneck",
        }
    }
    placement, fusion = VisualEntityPlacementPlanner().plan(
        frame_id="frame-1",
        base_prompt="production bottleneck",
        frame_context={"diagram_grammar": "process_flow"},
        base_visual_brief=None,
        article_concretization=article,
        required_subjects=(subject,),
        signature=signature,
    )
    bundle = ArticleConcretizationPromptCompiler().compile_for_z_image(
        final_contract=FinalVisualPromptContractV45(
            contract_id="subject-integrity",
            frame_id="frame-1",
            primary_visual_task="cognitive_explanation",
            visible_text_policy="no_visible_text",
            required_subjects=(subject,),
            series_visual_signature=signature,
            article_concretization=article,
            entity_placement=placement,
            scene_fusion=fusion,
        )
    )

    assert subject in bundle.positive_prompt
