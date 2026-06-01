import json

import pytest

from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    FinalVisualPromptContractV44,
    ProjectedPromptPart,
    attach_v44_contract_metadata,
)
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisibleTextPolicy
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy


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


def _projected_part(**overrides):
    values = {
        "part_id": "part-1",
        "priority": 10,
        "source_plan_type": "article_anchor_plan",
        "source_field": "scene",
        "content": "a concrete visual prompt part",
        "locked": True,
        "critic_check_required": "false",
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
    assert attached.metadata["v44_contract"] == v44.to_dict()


@pytest.mark.parametrize("priority", [True, False, "1", 1.0, None])
def test_projected_prompt_part_rejects_invalid_priority(priority):
    with pytest.raises(ValueError, match="priority"):
        _projected_part(priority=priority)


@pytest.mark.parametrize("field_name", ["locked", "critic_check_required"])
def test_projected_prompt_part_rejects_invalid_bool_fields(field_name):
    with pytest.raises(ValueError, match=field_name):
        _projected_part(**{field_name: "sometimes"})


def test_v44_contract_rejects_invalid_projected_prompt_parts():
    with pytest.raises(ValueError, match="projected_prompt_parts"):
        _v44_contract(projected_prompt_parts=[{"part_id": "part-1"}])
