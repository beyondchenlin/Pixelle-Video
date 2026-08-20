from __future__ import annotations

from types import SimpleNamespace

import pytest

from pixelle_video.models.final_visual_prompt_contract_v45 import (
    FinalVisualPromptContractV45,
)
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
    relative_size_from_max_area_ratio,
)
from pixelle_video.models.visual_entity_placement import (
    NOT_APPLICABLE,
    VisualRelativeSize,
    VisualSceneType,
)
from pixelle_video.services.final_visual_prompt_compiler import (
    FinalVisualPromptCompiler,
)
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    SeriesVisualSignatureFinalPromptGateError,
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
)
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionError,
    SeriesVisualSignatureProjectionService,
)
from pixelle_video.services.visual_entity_placement_planner import (
    VisualEntityPlacementPlanner,
)


def _request(**overrides) -> SeriesVisualSignatureRequest:
    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_profile_id": "dog_1",
        "series_visual_signature_role": "guide",
    }
    payload.update(overrides)
    return SeriesVisualSignatureRequest.from_mapping(payload)


def _profile(*, forbidden_traits=()) -> VisualSignatureProfileSnapshot:
    return VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        core_identity_traits=("black spots", "black sunglasses", "red collar"),
        supporting_identity_traits=("small round ears",),
        forbidden_traits=forbidden_traits,
    )


def _signature(*, forbidden_traits=()) -> SeriesVisualSignatureContract:
    return SeriesVisualSignatureContract(
        enabled=True,
        role="guide",
        profile=_profile(forbidden_traits=forbidden_traits),
        max_area_ratio=0.18,
        participation_rule="Guide points to the reading path.",
    )


def _contract(
    *,
    frame_id: str = "frame-1",
    grammar: str = "plain_scene",
    base_prompt: str = "worker beside assembly line on a factory floor",
    required_subjects=("worker", "assembly line"),
    forbidden_traits=(),
) -> FinalVisualPromptContractV45:
    signature = _signature(forbidden_traits=forbidden_traits)
    article = {
        "anchor": {"anchor_claim": base_prompt},
        "diagram": {"grammar": grammar, "visual_metaphor": base_prompt},
        "render": {"render_style": "editorial_diagram"},
    }
    placement, fusion = VisualEntityPlacementPlanner().plan(
        frame_id=frame_id,
        base_prompt=base_prompt,
        frame_context={
            "diagram_grammar": grammar,
            "world_elements": ["factory floor"],
            "lighting": "warm light",
        },
        base_visual_brief=None,
        article_concretization=article,
        required_subjects=required_subjects,
        signature=signature,
    )
    return FinalVisualPromptContractV45(
        contract_id=f"contract:{frame_id}",
        frame_id=frame_id,
        primary_visual_task="cognitive_explanation",
        required_subjects=required_subjects,
        article_concretization=article,
        series_visual_signature=signature,
        diagram_render={"render_style": "editorial_diagram"},
        visible_text_policy="preserve_base",
        entity_placement=placement,
        scene_fusion=fusion,
    )


def test_snapshot_merges_all_identity_sources_without_losing_order() -> None:
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=_request(),
        ip_profile=SimpleNamespace(
            series_visual_signature_profile_id="dog_1",
            name="Dalmatian",
            identity_lock=("black spots", "red collar"),
            minimal_traits=("red collar", "black sunglasses"),
            identity_anchors=("black sunglasses", "small round ears"),
            forbidden_elements=("green tail",),
            metadata={},
        ),
    )

    assert profile.core_identity_traits == (
        "black spots",
        "red collar",
        "black sunglasses",
    )
    assert profile.supporting_identity_traits == ("small round ears",)
    assert profile.identity_traits == (
        "black spots",
        "red collar",
        "black sunglasses",
        "small round ears",
    )
    assert "small round ears" in profile.canonical_identity_clause


def test_identity_hash_is_normalized_stable_and_changes_with_every_identity_fact() -> None:
    base = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Cafe\u0301 Dog",
        core_identity_traits=(" black   spots ", "red collar"),
        supporting_identity_traits=("small ears",),
        forbidden_traits=("green tail",),
    )
    normalized = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Café Dog",
        core_identity_traits=("black spots", "red collar"),
        supporting_identity_traits=("small ears",),
        forbidden_traits=("green tail",),
    )

    assert base.canonical_identity_clause == normalized.canonical_identity_clause
    assert base.identity_content_sha256 == normalized.identity_content_sha256
    changed_hashes = {
        VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name="Other Dog",
            core_identity_traits=normalized.core_identity_traits,
            supporting_identity_traits=normalized.supporting_identity_traits,
            forbidden_traits=normalized.forbidden_traits,
        ).identity_content_sha256,
        VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name=normalized.display_name,
            core_identity_traits=("brown spots", "red collar"),
            supporting_identity_traits=normalized.supporting_identity_traits,
            forbidden_traits=normalized.forbidden_traits,
        ).identity_content_sha256,
        VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name=normalized.display_name,
            core_identity_traits=normalized.core_identity_traits,
            supporting_identity_traits=normalized.supporting_identity_traits,
            forbidden_traits=("blue tail",),
        ).identity_content_sha256,
    }
    assert len(changed_hashes) == 3
    assert normalized.identity_content_sha256 not in changed_hashes


def test_canonical_identity_over_budget_fails_before_frame_projection() -> None:
    with pytest.raises(ValueError, match="canonical_identity_clause exceeds 400"):
        VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name="Dalmatian",
            core_identity_traits=tuple(
                f"trait-{index}-" + ("x" * 51) for index in range(7)
            ),
        )


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (0.10, VisualRelativeSize.SMALL),
        (0.18, VisualRelativeSize.MEDIUM_SMALL),
        (0.30, VisualRelativeSize.MEDIUM),
        (0.45, VisualRelativeSize.LARGE),
    ],
)
def test_legacy_area_ratio_maps_to_stable_relative_size(ratio, expected) -> None:
    assert relative_size_from_max_area_ratio(ratio) is expected


def test_physical_contract_compiles_every_placement_and_fusion_fact() -> None:
    contract = _contract()
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)
    placement = contract.entity_placement
    fusion = contract.scene_fusion

    assert placement is not None
    assert fusion is not None
    assert placement.instance_count == 1
    assert placement.scene_type is VisualSceneType.PHYSICAL_SCENE
    for fact in (
        placement.horizontal_position.value,
        placement.depth_position.value,
        placement.relative_size.value.replace("_", "-"),
        placement.relation_target,
        placement.spatial_relation,
        placement.support_relation,
        placement.action,
        placement.orientation,
        placement.visible_extent.value.replace("_", "-"),
        *placement.visible_core_traits,
        fusion.occlusion_relation,
        fusion.perspective_relation,
        fusion.contact_relation,
        fusion.lighting_relation,
        fusion.shadow_relation,
        fusion.style_relation,
    ):
        assert fact in bundle.positive_prompt
    assert len(bundle.positive_prompt) <= 1200
    assert len(bundle.negative_prompt) <= 800
    assert "%" not in bundle.positive_prompt
    assert "Only one instance" in bundle.positive_prompt
    assert "It keeps its original character form" in bundle.positive_prompt
    assert bundle.positive_prompt.index("Required subjects stay visible") < (
        bundle.positive_prompt.index("Canonical recurring identity")
    )
    assert (
        "non-human recurring identity with human anatomy, human clothing, or mascot costume"
        in bundle.negative_prompt
    )


def test_physical_support_prefers_ground_plane_over_table_surface() -> None:
    signature = _signature()
    placement, _ = VisualEntityPlacementPlanner().plan(
        frame_id="frame-ground",
        base_prompt="a woman reviews a map beside a table on a studio floor",
        frame_context={"world_elements": ["wooden table", "studio floor"]},
        base_visual_brief=None,
        article_concretization={"diagram": {"grammar": "plain_scene"}},
        required_subjects=("woman", "map"),
        signature=signature,
    )

    assert placement.support_relation == "feet on existing floor"


def test_walking_scene_uses_shared_motion_instead_of_static_role_fallback() -> None:
    signature = _signature()
    placement, _ = VisualEntityPlacementPlanner().plan(
        frame_id="frame-walk",
        base_prompt="a man walking along a riverside path",
        frame_context={"world_elements": ["riverside path"]},
        base_visual_brief=None,
        article_concretization={"diagram": {"grammar": "plain_scene"}},
        required_subjects=("man", "riverside path"),
        signature=signature,
    )

    assert placement.action == "walks with man"
    assert placement.spatial_relation == "alongside"
    assert placement.orientation == "faces movement direction"
    assert placement.support_relation == "feet on existing path"


def test_abstract_contract_marks_physical_facts_not_applicable_but_omits_them() -> None:
    contract = _contract(
        grammar="process_flow",
        base_prompt="unlabeled process nodes connected by a reading path",
        required_subjects=("process nodes",),
    )
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)
    placement = contract.entity_placement
    fusion = contract.scene_fusion

    assert placement is not None
    assert fusion is not None
    assert placement.scene_type is VisualSceneType.ABSTRACT_DIAGRAM
    assert fusion.perspective_relation == NOT_APPLICABLE
    assert fusion.contact_relation == NOT_APPLICABLE
    assert fusion.lighting_relation == NOT_APPLICABLE
    assert fusion.shadow_relation == NOT_APPLICABLE
    positive = bundle.positive_prompt.casefold()
    assert "not_applicable" not in positive
    assert "feet on" not in positive
    assert "contact shadow" not in positive
    assert "node" in positive
    assert "path" in positive
    assert "linework" in positive
    assert "material" in positive


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("entity_placement", "support_relation"),
        ("scene_fusion", "lighting_relation"),
    ],
)
def test_missing_structured_fact_fails_with_frame_and_field_path(section, field) -> None:
    payload = _contract(frame_id="frame-missing").to_dict()
    payload[section][field] = ""

    with pytest.raises(ValueError, match=rf"frame frame-missing: .*{field}"):
        FinalVisualPromptContractV45.from_mapping(payload)


def test_serialized_contract_rejects_tampered_semantics_against_saved_hash() -> None:
    payload = _contract(frame_id="frame-hash").to_dict()
    payload["series_visual_signature"]["role"] = "operator"

    with pytest.raises(ValueError, match="contract_content_sha256"):
        FinalVisualPromptContractV45.from_mapping(payload)
    with pytest.raises(ValueError, match="contract_content_sha256"):
        FinalVisualPromptCompiler().compile(final_contract=payload)


def test_negative_prompt_over_budget_fails_without_dropping_forbidden_traits() -> None:
    contract = _contract(forbidden_traits=("green tail",))
    with pytest.raises(ValueError, match="negative prompt exceeds 800"):
        FinalVisualPromptCompiler().compile(
            final_contract=contract,
            base_negative_prompt="x" * 240,
        )


def test_final_gate_rejects_missing_profile_forbidden_trait() -> None:
    contract = _contract(forbidden_traits=("green tail",))
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)
    placement = contract.entity_placement
    fusion = contract.scene_fusion

    with pytest.raises(
        SeriesVisualSignatureFinalPromptGateError,
        match="configured forbidden identity trait missing",
    ):
        assert_series_visual_signature_final_prompt(
            positive_prompt=bundle.positive_prompt,
            negative_prompt=bundle.negative_prompt.replace(", green tail", ""),
            required_subjects=contract.required_subjects,
            signature=contract.series_visual_signature,
            visible_text_policy=contract.visible_text_policy,
            placement=placement,
            scene_fusion=fusion,
            frame_id=contract.frame_id,
        )


def test_batch_projection_fails_atomically_after_a_later_frame_error() -> None:
    profile = _profile()
    with pytest.raises(SeriesVisualSignatureProjectionError) as captured:
        SeriesVisualSignatureProjectionService().project_batch(
            base_prompts=["worker on a factory floor", "oversized fact " * 40],
            frame_ids=["frame-good", "frame-bad"],
            frame_contexts=[{}, {}],
            request=_request(),
            profile=profile,
        )

    error = captured.value
    assert error.failed_frame_id == "frame-bad"
    assert error.metrics.expected_frame_count == 2
    assert error.metrics.projected_frame_count == 1
    assert error.audit_dict()["status"] == "failed"
    assert error.audit_dict()["all_frames_passed"] is False


def test_old_prompt_plan_record_remains_readable_with_empty_v45_fields() -> None:
    plan = PromptPlan.from_dict(
        {
            "prompt_plan_id": "plan-old",
            "storyboard_plan_id": "storyboard-old",
            "frame_id": "frame-old",
            "image_prompt_draft_id": "draft-old",
            "prompt_sections": {"scene": "old scene"},
            "final_prompt": "old scene",
        }
    )

    assert plan.final_negative_prompt is None
    assert plan.identity_content_sha256 is None
    assert plan.contract_content_sha256 is None
    assert plan.contract_version is None
