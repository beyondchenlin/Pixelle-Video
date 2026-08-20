from __future__ import annotations

import pytest

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
from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler
from pixelle_video.services.visual_entity_placement_planner import (
    VisualEntityPlacementPlanner,
)


def _signature() -> SeriesVisualSignatureContract:
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        identity_traits=(
            "black spots",
            "black sunglasses",
            "red collar",
            "small round ears",
        ),
    )
    return SeriesVisualSignatureContract(
        enabled=True,
        role="guide",
        profile=profile,
        max_area_ratio=0.18,
        participation_rule="Small guide points to the reading path.",
    )


def _final_contract(
    *,
    contract_id: str,
    frame_id: str,
    visual_metaphor: str,
    grammar: str,
    required_subjects=(),
    visible_text_policy: str = "no_visible_text",
    render_style: str = "auto",
) -> FinalVisualPromptContractV45:
    signature = _signature()
    article = {
        "anchor": {"anchor_claim": visual_metaphor},
        "diagram": {"grammar": grammar, "visual_metaphor": visual_metaphor},
        "render": {"render_style": render_style},
    }
    placement, fusion = VisualEntityPlacementPlanner().plan(
        frame_id=frame_id,
        base_prompt=visual_metaphor,
        frame_context={"diagram_grammar": grammar},
        base_visual_brief=None,
        article_concretization=article,
        required_subjects=required_subjects,
        signature=signature,
    )
    return FinalVisualPromptContractV45(
        contract_id=contract_id,
        frame_id=frame_id,
        primary_visual_task="cognitive_explanation",
        required_subjects=required_subjects,
        article_concretization=article,
        series_visual_signature=signature,
        diagram_render={"render_style": render_style},
        visible_text_policy=visible_text_policy,
        entity_placement=placement,
        scene_fusion=fusion,
    )
def test_compatibility_compiler_has_no_independent_semantics() -> None:
    assert issubclass(ArticleConcretizationPromptCompiler, FinalVisualPromptCompiler)


def test_disabled_signature_positive_prompt_does_not_mention_character() -> None:
    bundle = FinalVisualPromptCompiler().compile(
        final_contract={
            "contract_id": "contract_1",
            "frame_id": "frame_1",
            "visible_text_policy": "no_visible_text",
            "article_concretization": {
                "anchor": {"anchor_claim": "人物关系很难理解"},
                "diagram": {
                    "grammar": "relationship_map",
                    "visual_metaphor": "家族树图上的名字和名字列表",
                },
            },
        }
    )

    lower_prompt = bundle.positive_prompt.lower()
    assert "signature character" not in lower_prompt
    assert "mascot" not in lower_prompt
    assert "家族树图上的名字" not in bundle.positive_prompt
    assert "名字列表" not in bundle.positive_prompt
    assert "unlabeled" in bundle.positive_prompt
    assert "prompt_budget" not in bundle.to_dict()["metadata"]


def test_enabled_signature_requires_every_identity_trait() -> None:
    bundle = FinalVisualPromptCompiler().compile(
        final_contract=_final_contract(
            contract_id="contract_1",
            frame_id="frame_1",
            visual_metaphor="unlabeled family tree",
            grammar="relationship_map",
            render_style="xiaohei_handdrawn",
        )
    )

    assert "Dalmatian" in bundle.positive_prompt
    for trait in _signature().profile.identity_traits:
        assert trait in bundle.positive_prompt
    assert "medium-small" in bundle.positive_prompt
    assert "%" not in bundle.positive_prompt
    assert "photorealistic mascot" in bundle.negative_prompt
    assert "sticker" in bundle.negative_prompt
    assert "watermark" in bundle.negative_prompt
    assert "duplicate recurring visual signature" in bundle.negative_prompt
    assert "real in-scene participant" not in bundle.positive_prompt


def test_serialized_signature_contract_round_trip_keeps_signature_enabled() -> None:
    signature = _signature()
    contract = _final_contract(
        contract_id="contract_serialized",
        frame_id="frame_serialized",
        visual_metaphor="unlabeled relationship structure",
        grammar="relationship_map",
    ).to_dict()
    contract["series_visual_signature"] = signature.to_dict()
    bundle = FinalVisualPromptCompiler().compile(
        final_contract=contract
    )

    metadata = bundle.to_dict()["metadata"]
    assert metadata["series_visual_signature"]["enabled"] is True
    assert "Dalmatian" in bundle.positive_prompt
    assert "small round ears" in bundle.positive_prompt


def test_required_subjects_are_model_visible_and_protected() -> None:
    bundle = FinalVisualPromptCompiler().compile(
        final_contract=_final_contract(
            contract_id="contract_subjects",
            frame_id="frame_subjects",
            visual_metaphor="unlabeled production bottleneck",
            grammar="process_flow",
            required_subjects=("factory owner", "assembly line"),
        )
    )

    assert "factory owner" in bundle.positive_prompt
    assert "assembly line" in bundle.positive_prompt
    assert "unobscured, and unreplaced" in bundle.positive_prompt
    assert any(
        "required subjects" in item.lower()
        for item in bundle.locked_constraints
    )


def test_base_negative_prompt_is_preserved_without_global_logo_ban() -> None:
    bundle = FinalVisualPromptCompiler().compile(
        final_contract=_final_contract(
            contract_id="contract_negative",
            frame_id="frame_negative",
            visual_metaphor="branded factory sign beside the assembly line",
            grammar="plain_scene",
            required_subjects=("branded factory sign",),
            visible_text_policy="preserve_base",
        ),
        base_negative_prompt="low quality, malformed hands",
    )

    assert "low quality" in bundle.negative_prompt
    assert "malformed hands" in bundle.negative_prompt
    assert "sticker, corner badge, emblem, logo, or watermark overlay" in (
        bundle.negative_prompt
    )
    assert not bundle.negative_prompt.startswith("logo")


def test_long_main_visual_cannot_truncate_signature_or_required_subjects() -> None:
    long_visual = "complex causal mechanism " * 120
    with pytest.raises(ValueError, match="main content and required subjects"):
        FinalVisualPromptCompiler().compile(
            final_contract=_final_contract(
                contract_id="contract_long",
                frame_id="frame_long",
                visual_metaphor=long_visual,
                grammar="process_flow",
                required_subjects=("worker", "machine"),
            )
        )


def test_protected_semantics_over_budget_fail_instead_of_truncating() -> None:
    subjects = [f"required subject {index} " + ("x" * 80) for index in range(20)]

    with pytest.raises(ValueError, match="prompt budget"):
        FinalVisualPromptCompiler().compile(
            final_contract=_final_contract(
                contract_id="contract_over_budget",
                frame_id="frame_over_budget",
                visual_metaphor="production system",
                grammar="process_flow",
                required_subjects=subjects,
            )
        )


def test_z_image_compatibility_entry_uses_provider_adapter_bundle() -> None:
    bundle = ArticleConcretizationPromptCompiler().compile_for_z_image(
        final_contract=_final_contract(
            contract_id="contract_z",
            frame_id="frame_z",
            visual_metaphor="worker at machine",
            grammar="plain_scene",
            required_subjects=("worker",),
            visible_text_policy="preserve_base",
        )
    )

    assert bundle.to_dict()["metadata"]["target_provider"] == "z_image"
