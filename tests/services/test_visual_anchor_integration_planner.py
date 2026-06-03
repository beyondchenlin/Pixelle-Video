import asyncio

import pytest
from pydantic import ValidationError

from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.mandatory_visual_anchor_integration import (
    MandatoryVisualAnchorIntegrationPlanResponse,
    MandatoryVisualAnchorIntegrationResponse,
)
from pixelle_video.models.visual_anchor_planning import AnchorProminence
from pixelle_video.services.series_visual_signature_anchor_planner import (
    VisualAnchorIntegrationPlanner,
)


class ValidSceneBoundLLM:
    async def __call__(self, **kwargs):
        return MandatoryVisualAnchorIntegrationResponse(
            visual_anchor_integration_plans=[
                MandatoryVisualAnchorIntegrationPlanResponse(
                    frame_id="f1",
                    carrier_type="bookplate_or_stamp",
                    anchor_function="material_signature",
                    prominence="embedded_mark",
                    style_relation="blended",
                    placement="attached to the inner paper margin of the open page",
                    support_anchor="open book page",
                    contact_relation="pressed into the paper surface",
                    interaction_target="book page",
                    occlusion_relation="main reading area remains clear",
                    visual_weight_clause="low contrast in-scene material detail",
                    image_prompt_clause=(
                        "white tech rabbit with a blue collar appears as a subtle "
                        "bookplate stamp on the open page"
                    ),
                    integrated_scene_prompt=(
                        "An open book page with a subtle bookplate stamp showing "
                        "a white tech rabbit with a blue collar."
                    ),
                    integration_strategy="supporting_integration",
                    manifestation_form="bookplate stamp",
                    manifestation_location="inner paper margin",
                    manifestation_visibility="clear",
                    manifestation_relationship="supports the book scene without replacing it",
                    scene_coherence_score=10,
                    disruption_risk=1,
                    identity_preservation_score=9,
                    reason="low disruption",
                )
            ]
        )


class RejectedOverlayLLM:
    async def __call__(self, **kwargs):
        return {
            "visual_anchor_integration_plans": [
                {
                    "frame_id": "f1",
                    "carrier_type": "printed_mark",
                    "anchor_function": "material_signature",
                    "prominence": "embedded_mark",
                    "style_relation": "blended",
                    "placement": "canvas lower-right corner",
                    "support_anchor": "canvas corner",
                    "contact_relation": "floating overlay on the image",
                    "image_prompt_clause": "lower-right blue-collar rabbit logo corner badge",
                    "integrated_scene_prompt": "lower-right blue-collar rabbit logo corner badge",
                    "integration_strategy": "supporting_integration",
                    "anchor_manifestation": {
                        "form": "corner badge",
                        "location": "canvas lower-right corner",
                        "visibility": "clear",
                        "relationship": "floating overlay",
                    },
                    "scene_coherence_score": 10,
                    "disruption_risk": 1,
                    "identity_preservation_score": 9,
                    "reason": "bad overlay",
                }
            ]
        }


class MalformedButJsonLLM:
    async def __call__(self, **kwargs):
        return {
            "visual_anchor_integration_plans": [
                {
                    "frame_id": "f1",
                    "affordance": None,
                    "candidates": "selected_index",
                    "selected_index": "0",
                }
            ]
        }


class TypedRepairLLM:
    def __init__(self):
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise ValueError("schema validation failed: candidates must be an array")
        return MandatoryVisualAnchorIntegrationResponse(
            visual_anchor_integration_plans=[
                MandatoryVisualAnchorIntegrationPlanResponse(
                    frame_id="f1",
                    carrier_type="bookplate_or_stamp",
                    anchor_function="material_signature",
                    prominence="embedded_mark",
                    style_relation="blended",
                    placement="attached to the inner paper margin of the open page",
                    support_anchor="open book page",
                    contact_relation="pressed into the paper surface",
                    interaction_target="book page",
                    occlusion_relation="main reading area remains clear",
                    visual_weight_clause="low contrast in-scene material detail",
                    image_prompt_clause=(
                        "a dalmatian wearing black sunglasses appears as a subtle "
                        "bookplate stamp on the open page"
                    ),
                    integrated_scene_prompt=(
                        "An open book page with a subtle bookplate stamp showing "
                        "a dalmatian wearing black sunglasses."
                    ),
                    integration_strategy="supporting_integration",
                    manifestation_form="bookplate stamp",
                    manifestation_location="inner paper margin",
                    manifestation_visibility="clear",
                    manifestation_relationship="supports the book scene without replacing it",
                    scene_coherence_score=9,
                    disruption_risk=1,
                    identity_preservation_score=9,
                    reason="mandatory integration",
                )
            ]
        )


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="white tech rabbit",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="white tech rabbit with a blue collar",
    )


def _ascii_profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="dalmatian",
        workspace_id="ws",
        project_id="prj",
        name="dalmatian",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="dalmatian wearing black sunglasses",
    )


def _book_brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f1",
        core_message="book introduction",
        visual_moment="an open book page shows a family story",
        main_subjects=("open book page",),
        anchor_affordances=("open book paper surface",),
        base_image_prompt="an open book page shows a family story",
    )


def test_series_visual_signature_anchor_planner_uses_flat_typed_scene_bound_plan():
    plans = asyncio.run(
        VisualAnchorIntegrationPlanner(llm_service=ValidSceneBoundLLM()).plan_batch(
            base_visual_briefs=(_book_brief(),),
            anchor_profile=_profile(),
        )
    )

    assert plans[0].visible
    assert plans[0].anchor_prominence is AnchorProminence.EMBEDDED_MARK
    assert "white tech rabbit" in plans[0].image_prompt_clause
    assert "blue collar" in plans[0].image_prompt_clause
    assert "bookplate stamp" in plans[0].image_prompt_clause
    assert "corner" not in plans[0].image_prompt_clause
    assert "watermark" not in plans[0].image_prompt_clause
    assert plans[0].metadata["source"] == "llm_mandatory_series_visual_signature_integration"


def test_series_visual_signature_anchor_planner_uses_typed_schema_and_repairs_validation_failures():
    llm = TypedRepairLLM()

    plans = asyncio.run(
        VisualAnchorIntegrationPlanner(llm_service=llm).plan_batch(
            base_visual_briefs=(_book_brief(),),
            anchor_profile=_ascii_profile(),
        )
    )

    assert len(llm.calls) == 2
    assert all(call["response_type"] is MandatoryVisualAnchorIntegrationResponse for call in llm.calls)
    assert "schema validation failed" in llm.calls[1]["prompt"]
    assert plans[0].visible
    assert "dalmatian wearing black sunglasses" in plans[0].image_prompt_clause
    assert plans[0].metadata["anchor_manifestation"]["form"] == "bookplate stamp"


def test_mandatory_visual_anchor_integration_schema_rejects_legacy_candidate_shape():
    with pytest.raises(ValidationError) as exc_info:
        MandatoryVisualAnchorIntegrationResponse.model_validate(
            {
                "visual_anchor_integration_plans": [
                    {
                        "frame_id": "f1",
                        "candidates": "selected_index",
                    }
                ]
            }
        )

    fields = {".".join(str(part) for part in error["loc"]) for error in exc_info.value.errors()}
    assert "visual_anchor_integration_plans.0.candidates" in fields
    assert "visual_anchor_integration_plans.0.carrier_type" in fields


def test_mandatory_visual_anchor_integration_schema_rejects_malformed_nested_manifestation_shape():
    with pytest.raises(ValidationError) as exc_info:
        MandatoryVisualAnchorIntegrationResponse.model_validate(
            {
                "visual_anchor_integration_plans": [
                    {
                        "frame_id": "f1",
                        "carrier_type": "bookplate_or_stamp",
                        "anchor_function": "material_signature",
                        "prominence": "embedded_mark",
                        "style_relation": "blended",
                        "placement": "attached to the inner paper margin",
                        "support_anchor": "open book page",
                        "contact_relation": "pressed into the paper surface",
                        "interaction_target": "book page",
                        "occlusion_relation": "main reading area remains clear",
                        "visual_weight_clause": "low contrast in-scene material detail",
                        "image_prompt_clause": "dalmatian stamp on the open page",
                        "integrated_scene_prompt": "Open book page with a dalmatian stamp.",
                        "integration_strategy": "supporting_integration",
                        "anchor_manifestation": "form",
                        "location": "inner paper margin",
                        "visibility": "clear",
                        "relationship": "supports source intent without replacing it",
                    }
                ]
            }
        )

    fields = {".".join(str(part) for part in error["loc"]) for error in exc_info.value.errors()}
    assert "visual_anchor_integration_plans.0.anchor_manifestation" in fields
    assert "visual_anchor_integration_plans.0.manifestation_form" in fields
    assert "visual_anchor_integration_plans.0.scene_coherence_score" in fields


def test_mandatory_visual_anchor_integration_schema_is_flat_for_qwen_json_mode():
    schema_text = str(MandatoryVisualAnchorIntegrationResponse.model_json_schema())

    assert "manifestation_form" in schema_text
    assert "MandatoryVisualAnchorIntegrationManifestationResponse" not in schema_text
    assert "anchor_manifestation" not in schema_text
    assert "suppressed" not in schema_text
    assert "hidden" not in schema_text


def test_mandatory_visual_anchor_integration_plan_maps_flat_wire_fields_to_internal_payload():
    plan = MandatoryVisualAnchorIntegrationPlanResponse(
        frame_id="f1",
        carrier_type="bookplate_or_stamp",
        anchor_function="material_signature",
        prominence="embedded_mark",
        style_relation="blended",
        placement="inner margin",
        support_anchor="open book page",
        contact_relation="printed on paper",
        visual_weight_clause="subtle printed detail",
        image_prompt_clause="dalmatian stamp on the open page",
        integrated_scene_prompt="Open book page with a dalmatian stamp.",
        integration_strategy="supporting_integration",
        manifestation_form="bookplate stamp",
        manifestation_location="inner margin",
        manifestation_visibility="clear",
        manifestation_relationship="supports the book scene",
        scene_coherence_score=9,
        disruption_risk=1,
        identity_preservation_score=9,
        reason="mandatory integration",
    )

    payload = plan.to_plan_payload()

    assert payload["anchor_manifestation"] == {
        "form": "bookplate stamp",
        "location": "inner margin",
        "visibility": "clear",
        "relationship": "supports the book scene",
    }
    assert "manifestation_form" not in payload
    assert "manifestation_location" not in payload


def test_series_visual_signature_anchor_planner_rejects_overlay_candidate_fail_closed():
    with pytest.raises(ValueError, match="forbidden overlay"):
        asyncio.run(
            VisualAnchorIntegrationPlanner(llm_service=RejectedOverlayLLM()).plan_batch(
                base_visual_briefs=(_book_brief(),),
                anchor_profile=_profile(),
            )
        )


def test_series_visual_signature_anchor_planner_rejects_legacy_candidate_array_shape():
    with pytest.raises(ValueError, match="candidates arrays are not allowed"):
        asyncio.run(
            VisualAnchorIntegrationPlanner(llm_service=MalformedButJsonLLM()).plan_batch(
                base_visual_briefs=(_book_brief(),),
                anchor_profile=_profile(),
            )
        )


def test_series_visual_signature_anchor_planner_rejects_non_callable_llm_service():
    with pytest.raises(ValueError, match="callable llm_service"):
        asyncio.run(
            VisualAnchorIntegrationPlanner(llm_service=object()).plan_batch(
                base_visual_briefs=(_book_brief(),),
                anchor_profile=_profile(),
            )
        )
