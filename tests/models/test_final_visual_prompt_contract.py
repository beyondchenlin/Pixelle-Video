import json
import math
from enum import Enum

import pytest

from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    FinalVisualPromptContractV44,
    ProjectedPromptPart,
    RenderedMediaPrompt,
    attach_v44_contract_metadata,
)
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisibleTextPolicy
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy


class _UnsafeEnum(Enum):
    VALUE = object()


def test_final_visual_prompt_contract_sections_are_stable():
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style assignment",
        character_layer_style="character layer",
        world_layer_style="world layer",
        integration_priority="priority",
    )
    assert set(contract.prompt_sections()) == {
        "scene",
        "composition",
        "style_assignment",
        "character_layer_style",
        "world_layer_style",
        "integration_priority",
    }


def test_negative_rules_are_not_prompt_sections():
    contract = FinalVisualPromptContract("s", "c", "a", "char", "world", "priority", negative_rules=("no collage",))
    assert "negative_rules" not in contract.prompt_sections()


def test_final_visual_prompt_contract_to_dict_keeps_v1_shape():
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style assignment",
        character_layer_style="character layer",
        world_layer_style="world layer",
        integration_priority="priority",
        negative_rules=("no blur", "no blur"),
        metadata={"source": "legacy"},
    )

    assert contract.to_dict() == {
        "version": "final_visual_prompt_contract.v1",
        "scene": "scene",
        "composition": "composition",
        "style_assignment": "style assignment",
        "character_layer_style": "character layer",
        "world_layer_style": "world layer",
        "integration_priority": "priority",
        "negative_rules": ["no blur"],
        "metadata": {"source": "legacy"},
    }


def _projected_part(**overrides):
    values = {
        "part_id": "part-1",
        "priority": 10,
        "source_plan_type": "article_anchor_plan",
        "source_field": "scene",
        "content": "a concrete visual prompt part",
        "locked": True,
        "critic_check_required": False,
    }
    values.update(overrides)
    return ProjectedPromptPart(**values)


def _v44_contract(**overrides):
    values = {
        "contract_id": "contract-1",
        "frame_id": "frame-1",
        "primary_visual_task": "cognitive_explanation",
        "article_anchor": "article anchor",
        "required_subjects": ["host", {"name": "screen", "count": 1}],
        "visual_concretization_summary": "concrete summary",
        "identity_contract": {"identity": "Pixelle", "traits": ("bright", "precise")},
        "visual_role_strategy": VisualRoleStrategy.OBSERVER_GUIDE,
        "weight_contract": {"subject": 0.8, "style": 0.2},
        "visible_text_policy": VisibleTextPolicy.SOURCE_TEXT_ONLY,
        "projected_prompt_parts": [_projected_part()],
        "negative_semantics": ("no unreadable text", "no unreadable text", "no blur"),
        "route_decision_id": "route-1",
    }
    values.update(overrides)
    return FinalVisualPromptContractV44(**values)


def test_v44_contract_serializes_json_safe_payload():
    contract = _v44_contract()

    payload = contract.to_dict()

    assert payload["contract_schema_version"] == "final_visual_prompt_contract.v4_4"
    assert payload["route_decision_id"] == "route-1"
    assert payload["primary_visual_task"] == PrimaryVisualTask.COGNITIVE_EXPLANATION.value
    assert payload["visual_role_strategy"] == VisualRoleStrategy.OBSERVER_GUIDE.value
    assert payload["visible_text_policy"] == VisibleTextPolicy.SOURCE_TEXT_ONLY.value
    assert payload["required_subjects"] == ["host", {"name": "screen", "count": 1}]
    assert payload["projected_prompt_parts"] == [
        {
            "part_id": "part-1",
            "priority": 10,
            "source_plan_type": "article_anchor_plan",
            "source_field": "scene",
            "content": "a concrete visual prompt part",
            "locked": True,
            "critic_check_required": False,
        }
    ]
    assert payload["negative_semantics"] == ["no unreadable text", "no blur"]
    json.dumps(payload, allow_nan=False)


def test_attach_v44_contract_metadata_preserves_v1_fields_and_original_metadata():
    original = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        negative_rules=("no blur",),
        metadata={"existing": {"keep": True}},
    )
    v44 = _v44_contract()

    attached = attach_v44_contract_metadata(original, v44)

    assert attached is not original
    assert attached.prompt_sections() == original.prompt_sections()
    assert attached.negative_rules == original.negative_rules
    assert attached.version == original.version
    assert "v44_contract" not in original.metadata
    assert attached.metadata["existing"] == {"keep": True}
    assert attached.to_dict()["metadata"]["v44_contract"] == v44.to_dict()


def test_attach_v44_contract_metadata_detaches_nested_metadata_from_original():
    original = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={"existing": {"keep": True}},
    )
    v44 = _v44_contract()

    attached = attach_v44_contract_metadata(original, v44)

    with pytest.raises(TypeError):
        original.metadata["existing"]["keep"] = False
    assert attached.metadata["existing"] == {"keep": True}


def test_final_visual_prompt_contract_to_dict_detaches_v44_metadata():
    original = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={"source": "legacy"},
    )
    v44 = _v44_contract()

    attached = attach_v44_contract_metadata(original, v44)
    payload = attached.to_dict()
    payload["metadata"]["v44_contract"]["route_decision_id"] = "mutated-route"

    assert attached.metadata["v44_contract"]["route_decision_id"] == "route-1"
    assert FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={"source": "legacy"},
    ).to_dict()["metadata"] == {"source": "legacy"}


def test_final_visual_prompt_contract_metadata_is_deep_frozen():
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={"existing": {"keep": True}, "items": ["a"]},
    )

    with pytest.raises(TypeError):
        contract.metadata["existing"]["keep"] = False
    with pytest.raises(TypeError):
        contract.metadata["items"][0] = "b"


def test_rendered_media_prompt_metadata_cannot_diverge_from_contract_trace():
    contract = attach_v44_contract_metadata(
        FinalVisualPromptContract(
            scene="scene",
            composition="composition",
            style_assignment="style",
            character_layer_style="character",
            world_layer_style="world",
            integration_priority="priority",
        ),
        _v44_contract(),
    )
    rendered = RenderedMediaPrompt(
        prompt="rendered prompt",
        negative_prompt=None,
        prompt_contract=contract,
        renderer_id="renderer",
        renderer_version="v1",
    )

    with pytest.raises(TypeError):
        contract.metadata["v44_contract"]["route_decision_id"] = "mutated-route"
    with pytest.raises(TypeError):
        rendered.metadata["v44_contract"]["route_decision_id"] = "mutated-route"
    assert rendered.metadata["route_decision_id"] == contract.metadata["v44_contract"]["route_decision_id"]


def test_final_visual_prompt_contract_to_dict_drops_unsafe_legacy_metadata():
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={
            "safe": {"keep": True},
            "unsafe_object": object(),
            "unsafe_nan": math.nan,
            "unsafe_inf": math.inf,
            "mixed_list": ["keep", object(), -math.inf, 3],
        },
    )

    payload = contract.to_dict()

    assert payload["metadata"] == {
        "safe": {"keep": True},
        "mixed_list": ["keep", 3],
    }
    json.dumps(payload, allow_nan=False)


def test_attach_v44_contract_metadata_drops_unsafe_legacy_metadata():
    original = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={
            "safe": "keep",
            "unsafe_object": object(),
            "unsafe_nan": math.nan,
        },
    )
    v44 = _v44_contract()

    payload = attach_v44_contract_metadata(original, v44).to_dict()

    assert payload["metadata"]["safe"] == "keep"
    assert "unsafe_object" not in payload["metadata"]
    assert "unsafe_nan" not in payload["metadata"]
    assert payload["metadata"]["v44_contract"] == v44.to_dict()
    json.dumps(payload, allow_nan=False)


def test_rendered_media_prompt_metadata_exposes_v44_trace_keys():
    contract = attach_v44_contract_metadata(
        FinalVisualPromptContract(
            scene="scene",
            composition="composition",
            style_assignment="style",
            character_layer_style="character",
            world_layer_style="world",
            integration_priority="priority",
        ),
        _v44_contract(),
    )

    rendered = RenderedMediaPrompt(
        prompt="rendered prompt",
        negative_prompt=None,
        prompt_contract=contract,
        renderer_id="renderer",
        renderer_version="v1",
        metadata={"provider_prompt_mode": "test"},
    )

    assert rendered.metadata["contract_id"] == "contract-1"
    assert rendered.metadata["frame_id"] == "frame-1"
    assert rendered.metadata["route_decision_id"] == "route-1"
    assert rendered.metadata["contract_schema_version"] == "final_visual_prompt_contract.v4_4"
    assert rendered.metadata["v44_contract"] == {
        "contract_schema_version": "final_visual_prompt_contract.v4_4",
        "contract_id": "contract-1",
        "frame_id": "frame-1",
        "route_decision_id": "route-1",
    }
    assert "contract-1" not in rendered.prompt
    json.dumps(rendered.to_dict(), allow_nan=False)


def test_rendered_media_prompt_metadata_preserves_matching_trace_keys():
    contract = attach_v44_contract_metadata(
        FinalVisualPromptContract(
            scene="scene",
            composition="composition",
            style_assignment="style",
            character_layer_style="character",
            world_layer_style="world",
            integration_priority="priority",
        ),
        _v44_contract(),
    )

    rendered = RenderedMediaPrompt(
        prompt="rendered prompt",
        negative_prompt=None,
        prompt_contract=contract,
        renderer_id="renderer",
        renderer_version="v1",
        metadata={
            "contract_schema_version": "final_visual_prompt_contract.v4_4",
            "contract_id": "contract-1",
            "frame_id": "frame-1",
            "route_decision_id": "route-1",
            "v44_contract": {
                "contract_schema_version": "final_visual_prompt_contract.v4_4",
                "contract_id": "contract-1",
                "frame_id": "frame-1",
                "route_decision_id": "route-1",
                "extra_call_site_field": "discarded",
            },
        },
    )

    assert rendered.metadata["contract_id"] == "contract-1"
    assert rendered.metadata["frame_id"] == "frame-1"
    assert rendered.metadata["route_decision_id"] == "route-1"
    assert rendered.metadata["v44_contract"] == {
        "contract_schema_version": "final_visual_prompt_contract.v4_4",
        "contract_id": "contract-1",
        "frame_id": "frame-1",
        "route_decision_id": "route-1",
    }


@pytest.mark.parametrize(
    ("metadata", "match"),
    [
        ({"contract_id": "other-contract"}, "contract_id"),
        ({"frame_id": "other-frame"}, "frame_id"),
        (
            {
                "v44_contract": {
                    "contract_schema_version": "final_visual_prompt_contract.v4_4",
                    "contract_id": "contract-1",
                    "frame_id": "other-frame",
                    "route_decision_id": "route-1",
                }
            },
            "frame_id",
        ),
        (
            {
                "v44_contract": {
                    "contract_schema_version": "wrong.schema",
                    "contract_id": "contract-1",
                    "frame_id": "frame-1",
                    "route_decision_id": "route-1",
                }
            },
            "contract_schema_version",
        ),
    ],
)
def test_rendered_media_prompt_metadata_rejects_conflicting_trace_keys(metadata, match):
    contract = attach_v44_contract_metadata(
        FinalVisualPromptContract(
            scene="scene",
            composition="composition",
            style_assignment="style",
            character_layer_style="character",
            world_layer_style="world",
            integration_priority="priority",
        ),
        _v44_contract(),
    )

    with pytest.raises(ValueError, match=match):
        RenderedMediaPrompt(
            prompt="rendered prompt",
            negative_prompt=None,
            prompt_contract=contract,
            renderer_id="renderer",
            renderer_version="v1",
            metadata=metadata,
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"contract_id": "contract-1"},
        {"frame_id": "frame-1"},
        {"route_decision_id": "route-1"},
        {
            "v44_contract": {
                "contract_schema_version": "final_visual_prompt_contract.v4_4",
                "contract_id": "contract-1",
                "frame_id": "frame-1",
                "route_decision_id": "route-1",
            }
        },
    ],
)
def test_rendered_media_prompt_rejects_trace_metadata_without_contract_source(metadata):
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
    )

    with pytest.raises(ValueError, match="prompt_contract metadata"):
        RenderedMediaPrompt(
            prompt="rendered prompt",
            negative_prompt=None,
            prompt_contract=contract,
            renderer_id="renderer",
            renderer_version="v1",
            metadata=metadata,
        )


def test_attach_v44_contract_metadata_rejects_conflicting_existing_contract():
    existing = _v44_contract(route_decision_id="route-old").to_dict()
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
        metadata={"v44_contract": existing},
    )

    with pytest.raises(ValueError, match="v44_contract"):
        attach_v44_contract_metadata(contract, _v44_contract())


@pytest.mark.parametrize(
    ("metadata", "match"),
    [
        ({"v44_contract": object()}, "v44_contract"),
        (
            {
                "v44_contract": {
                    "contract_schema_version": "final_visual_prompt_contract.v4_4",
                    "contract_id": "contract-1",
                    "route_decision_id": "route-1",
                }
            },
            "frame_id",
        ),
        (
            {
                "v44_contract": {
                    "contract_schema_version": "wrong.schema",
                    "contract_id": "contract-1",
                    "frame_id": "frame-1",
                    "route_decision_id": "route-1",
                }
            },
            "contract_schema_version",
        ),
        (
            {
                "v44_contract": {
                    "contract_schema_version": "final_visual_prompt_contract.v4_4",
                    "contract_id": "contract-1",
                    "frame_id": "frame-1",
                    "route_decision_id": "route-1",
                    "unsafe": object(),
                }
            },
            "JSON-safe",
        ),
    ],
)
def test_final_visual_prompt_contract_rejects_invalid_reserved_v44_metadata(
    metadata,
    match,
):
    with pytest.raises((TypeError, ValueError), match=match):
        FinalVisualPromptContract(
            scene="scene",
            composition="composition",
            style_assignment="style",
            character_layer_style="character",
            world_layer_style="world",
            integration_priority="priority",
            metadata=metadata,
        )


@pytest.mark.parametrize("priority", [True, False, "1", 1.0, None])
def test_projected_prompt_part_rejects_invalid_priority(priority):
    with pytest.raises(ValueError, match="priority"):
        _projected_part(priority=priority)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("locked", "true"),
        ("critic_check_required", "false"),
        ("locked", 1),
        ("critic_check_required", 0),
        ("locked", None),
    ],
)
def test_projected_prompt_part_rejects_invalid_bool_fields(field_name, value):
    with pytest.raises(ValueError, match=field_name):
        _projected_part(**{field_name: value})


def test_v44_contract_rejects_invalid_projected_prompt_parts():
    with pytest.raises(ValueError, match="projected_prompt_parts"):
        _v44_contract(projected_prompt_parts=[{"part_id": "part-1"}])


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("primary_visual_task", "not_a_task"),
        ("visual_role_strategy", "not_a_strategy"),
        ("visible_text_policy", "free_text"),
    ],
)
def test_v44_contract_rejects_invalid_enum_strings(field_name, value):
    with pytest.raises(ValueError, match=field_name):
        _v44_contract(**{field_name: value})


def test_v44_contract_accepts_exact_enum_names():
    contract = _v44_contract(
        primary_visual_task="COGNITIVE_EXPLANATION",
        visual_role_strategy="OBSERVER_GUIDE",
        visible_text_policy="SOURCE_TEXT_ONLY",
    )

    assert contract.to_dict()["primary_visual_task"] == "cognitive_explanation"
    assert contract.to_dict()["visual_role_strategy"] == "observer_guide"
    assert contract.to_dict()["visible_text_policy"] == "source_text_only"


@pytest.mark.parametrize("negative_semantics", ["no blur", (1,), (True,), ({"rule": "no blur"},), ("",)])
def test_v44_contract_rejects_non_string_negative_semantics(negative_semantics):
    with pytest.raises(ValueError, match="negative_semantics"):
        _v44_contract(negative_semantics=negative_semantics)


def test_v44_contract_rejects_unsafe_enum_values_in_metadata_like_fields():
    with pytest.raises(ValueError, match="identity_contract"):
        _v44_contract(identity_contract={"unsafe": _UnsafeEnum.VALUE})


def test_v44_contract_rejects_invalid_schema_version():
    with pytest.raises(ValueError, match="contract_schema_version"):
        _v44_contract(contract_schema_version="wrong.schema")
