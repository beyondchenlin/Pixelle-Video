from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.prompt_plan import PromptPlan, PromptProjection
from pixelle_video.services.prompt_projection import build_prompt_projection


def build_prompt_plan(**overrides):
    payload = {
        "prompt_plan_id": "prompt_plan_001",
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_001",
        "prompt_sections": {"subject": "fox cub", "style": "storybook"},
        "final_prompt": "fox cub, storybook",
        "character_ids": ("char_fox",),
        "scene_id": "scene_village",
        "prop_ids": ("prop_lantern", "prop_book"),
        "style_id": "style_storybook",
        "metadata": {"source": "stage2_preview"},
    }
    payload.update(overrides)
    return PromptPlan(**payload)


def test_prompt_projection_contract_is_derived_from_prompt_plan_without_preview_fields():
    plan = build_prompt_plan()

    projection = build_prompt_projection(
        plan,
        metadata={
            "projection_source": "prompt_plan",
            "trace": {"stage": "stage23", "attempt": 1},
        },
    )

    assert projection == PromptProjection(
        prompt_plan_id="prompt_plan_001",
        frame_id="frame_0001",
        final_prompt="fox cub, storybook",
        character_ids=("char_fox",),
        scene_id="scene_village",
        prop_ids=("prop_lantern", "prop_book"),
        style_id="style_storybook",
        metadata={
            "projection_source": "prompt_plan",
            "trace": {"stage": "stage23", "attempt": 1},
        },
    )
    assert projection.to_dict() == {
        "prompt_plan_id": "prompt_plan_001",
        "frame_id": "frame_0001",
        "final_prompt": "fox cub, storybook",
        "character_ids": ["char_fox"],
        "scene_id": "scene_village",
        "prop_ids": ["prop_lantern", "prop_book"],
        "style_id": "style_storybook",
        "metadata": {
            "projection_source": "prompt_plan",
            "trace": {"stage": "stage23", "attempt": 1},
        },
    }
    assert "storyboard_plan_id" not in projection.to_dict()
    assert "prompt_sections" not in projection.to_dict()
    assert "provider_params" not in projection.to_dict()


@pytest.mark.parametrize(
    ("field_name", "overrides"),
    [
        ("prompt_plan_id", {"prompt_plan_id": r"C:\plans\prompt_plan_001"}),
        ("frame_id", {"frame_id": "frames/frame_0001"}),
        ("character_ids", {"character_ids": ("https://example.test/char_fox",)}),
        ("scene_id", {"scene_id": "../scene_village"}),
        ("prop_ids", {"prop_ids": ("workflows/selfhost/prop.json",)}),
        ("style_id", {"style_id": "style:storybook"}),
    ],
)
def test_prompt_projection_rejects_path_like_and_url_like_public_ids(field_name, overrides):
    plan = build_prompt_plan(**overrides)

    with pytest.raises(ValueError) as exc_info:
        build_prompt_projection(plan)

    assert field_name in str(exc_info.value)


@pytest.mark.parametrize(
    "metadata",
    [
        {"provider_params": {"steps": 20}},
        {"Provider_Params": {"steps": 20}},
        {"trace": {"selected_workflow": "workflows/selfhost/image.json"}},
        {"trace": {"provider_url": "https://provider.example.test"}},
        {"routing": {"provider": "comfyui"}},
        {"trace": {"workflow_path": "workflows/selfhost/image.json"}},
        {"raw_workflow": {"nodes": []}},
    ],
)
def test_prompt_projection_rejects_raw_provider_or_workflow_metadata(metadata):
    plan = build_prompt_plan()

    with pytest.raises(ValueError) as exc_info:
        build_prompt_projection(plan, metadata=metadata)

    assert "metadata" in str(exc_info.value)


def test_prompt_projection_metadata_is_controlled_and_immutable():
    projection = build_prompt_projection(
        build_prompt_plan(),
        metadata={"trace": {"stage": "stage23"}, "asset_count": 4},
    )

    assert projection.metadata["trace"]["stage"] == "stage23"
    with pytest.raises(TypeError):
        projection.metadata["asset_count"] = 5
    with pytest.raises(TypeError):
        projection.metadata["trace"]["stage"] = "changed"
    with pytest.raises(FrozenInstanceError):
        projection.final_prompt = "changed"


def test_prompt_projection_rejects_non_json_metadata_values():
    plan = build_prompt_plan()

    with pytest.raises(ValueError) as exc_info:
        build_prompt_projection(plan, metadata={"observed": object()})

    assert "metadata" in str(exc_info.value)
