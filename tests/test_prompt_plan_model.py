from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.prompt_plan import (
    ImagePromptDraft,
    PromptPlan,
    PromptProjection,
)


def test_image_prompt_draft_round_trips_frame_prompt_and_trace_link():
    draft = ImagePromptDraft(
        image_prompt_draft_id="draft_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        prompt_text="warm storybook village, soft light",
        source_trace_id="trace_001",
        metadata={"composer": "stage1a"},
    )

    assert ImagePromptDraft.from_dict(draft.to_dict()) == draft
    assert draft.to_dict() == {
        "image_prompt_draft_id": "draft_001",
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "prompt_text": "warm storybook village, soft light",
        "source_trace_id": "trace_001",
        "metadata": {"composer": "stage1a"},
    }

    with pytest.raises(FrozenInstanceError):
        draft.frame_id = "changed"
    with pytest.raises(TypeError):
        draft.metadata["composer"] = "changed"


def test_prompt_plan_uses_canonical_stage1a_shape():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={
            "subject": "a fox cub looking at lanterns",
            "style": "warm storybook illustration",
            "camera": "medium shot",
        },
        final_prompt="a fox cub looking at lanterns, warm storybook illustration, medium shot",
        source_trace_id="trace_001",
        character_ids=("char_fox",),
        scene_id="scene_village",
        prop_ids=("prop_lantern",),
        style_id="style_storybook",
    )

    payload = plan.to_dict()

    assert payload == {
        "prompt_plan_id": "prompt_plan_001",
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_001",
        "prompt_sections": {
            "subject": "a fox cub looking at lanterns",
            "style": "warm storybook illustration",
            "camera": "medium shot",
        },
        "final_prompt": "a fox cub looking at lanterns, warm storybook illustration, medium shot",
        "final_negative_prompt": None,
        "identity_content_sha256": None,
        "contract_content_sha256": None,
        "contract_version": None,
        "source_trace_id": "trace_001",
        "character_ids": ["char_fox"],
        "scene_id": "scene_village",
        "prop_ids": ["prop_lantern"],
        "style_id": "style_storybook",
        "metadata": {},
    }
    assert "panel_prompt" not in payload
    assert "base_prompt" not in payload
    assert "positive_prompt" not in payload
    assert PromptPlan.from_dict(payload) == plan


@pytest.mark.parametrize(
    "missing_field",
    (
        "identity_content_sha256",
        "contract_content_sha256",
        "contract_version",
    ),
)
def test_prompt_plan_requires_complete_lineage_metadata(missing_field):
    lineage = {
        "identity_content_sha256": "a" * 64,
        "contract_content_sha256": "b" * 64,
        "contract_version": "final_visual_prompt_contract.v4_6",
    }
    lineage.pop(missing_field)

    with pytest.raises(ValueError, match="must be provided together"):
        PromptPlan(
            prompt_plan_id="prompt_plan_001",
            storyboard_plan_id="storyboard_plan_001",
            frame_id="frame_0001",
            image_prompt_draft_id="draft_001",
            prompt_sections={"subject": "fox cub"},
            final_prompt="fox cub",
            **lineage,
        )


@pytest.mark.parametrize(
    "contract_version",
    ("../private/contract", "contract version", "v" * 129),
)
def test_prompt_plan_rejects_invalid_contract_version(contract_version):
    with pytest.raises(ValueError, match="contract_version"):
        PromptPlan(
            prompt_plan_id="prompt_plan_001",
            storyboard_plan_id="storyboard_plan_001",
            frame_id="frame_0001",
            image_prompt_draft_id="draft_001",
            prompt_sections={"subject": "fox cub"},
            final_prompt="fox cub",
            identity_content_sha256="a" * 64,
            contract_content_sha256="b" * 64,
            contract_version=contract_version,
        )


def test_prompt_projection_is_read_model_for_generation_and_stage2_refs():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"subject": "fox cub", "style": "storybook"},
        final_prompt="fox cub, storybook",
        character_ids=("char_fox",),
        scene_id="scene_village",
        prop_ids=("prop_lantern", "prop_book"),
        style_id="style_storybook",
    )

    projection = PromptProjection.from_prompt_plan(plan)

    assert projection.to_dict() == {
        "prompt_plan_id": "prompt_plan_001",
        "frame_id": "frame_0001",
        "final_prompt": "fox cub, storybook",
        "character_ids": ["char_fox"],
        "scene_id": "scene_village",
        "prop_ids": ["prop_lantern", "prop_book"],
        "style_id": "style_storybook",
        "metadata": {},
    }
    assert "prompt_sections" not in projection.to_dict()
    assert "provider_params" not in projection.to_dict()


def test_prompt_plan_round_trips_ip_summary_metadata():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"subject": "fox cub", "style": "storybook"},
        final_prompt="fox cub, storybook",
        metadata={
            "ip_presence_type": "scene_integrated",
            "image_text_plan": {
                "summary_text": "Changle Gate",
                "visible_text_whitelist": ["Changle Gate"],
            },
        },
    )

    restored = PromptPlan.from_dict(plan.to_dict())

    assert restored == plan
    assert restored.to_dict()["metadata"]["ip_presence_type"] == "scene_integrated"
    assert restored.to_dict()["metadata"]["image_text_plan"] == {
        "summary_text": "Changle Gate",
        "visible_text_whitelist": ["Changle Gate"],
    }


def test_prompt_projection_rejects_structured_ip_or_text_plan_metadata():
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"subject": "fox cub", "style": "storybook"},
        final_prompt="fox cub, storybook",
        metadata={
            "ip_presence_type": "scene_integrated",
            "image_text_plan": {"summary_text": "Changle Gate"},
            "ip_adaptation": {"identity_anchors_visible": ["blue tie"]},
        },
    )

    with pytest.raises(ValueError, match="image_text_plan|ip_adaptation"):
        PromptProjection.from_prompt_plan(plan, metadata=plan.metadata)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prompt_plan_id": "", "final_prompt": "x", "prompt_sections": {"subject": "x"}},
        {"prompt_plan_id": "plan", "final_prompt": "", "prompt_sections": {"subject": "x"}},
        {"prompt_plan_id": "plan", "final_prompt": "x", "prompt_sections": {}},
        {"prompt_plan_id": "plan", "final_prompt": "x", "prompt_sections": {"": "x"}},
        {"prompt_plan_id": "plan", "final_prompt": "x", "prompt_sections": {"subject": ""}},
    ],
)
def test_prompt_plan_rejects_missing_canonical_fields(kwargs):
    base = {
        "storyboard_plan_id": "storyboard_plan_001",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_001",
    }

    with pytest.raises(ValueError):
        PromptPlan(**base, **kwargs)
