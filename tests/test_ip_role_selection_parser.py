import json

import pytest
from pydantic import ValidationError

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.ip_prompt_planning import IPRoleSlot
from pixelle_video.models.ip_role_selection import IPRoleSelectionResponse
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.prompts.ip_role_selection import parse_ip_role_selection_response
from pixelle_video.services.ip_usage_planner import IPFrameAppearancePlanner


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Market Guide",
        identity_lock=("white rabbit body", "long ears"),
        identity_anchors=("blue necktie",),
        variable_slots=("action", "expression", "prop"),
        semantic_boundary=("must remain a guide character",),
    )


def _plan(frame: StoryboardPlanFrame) -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=frame.source_text,
        frames=[frame],
    )


def test_parse_ip_role_selection_accepts_structured_model_instance():
    response = IPRoleSelectionResponse.model_validate(
        {
            "role_selections": [
                {
                    "frame_index": 0,
                    "role_slot": "supporting",
                    "role_label": "side guide",
                    "presence_level": "half body",
                    "appearance_description": "white rabbit guide stands near the stall",
                    "reason": "supports the source subject",
                }
            ]
        }
    )

    parsed = parse_ip_role_selection_response(response)

    assert parsed == [
        {
            "frame_index": 0,
            "role_slot": "supporting",
            "role_label": "side guide",
            "presence_level": "half body",
            "appearance_description": "white rabbit guide stands near the stall",
            "reason": "supports the source subject",
        }
    ]


def test_ip_role_selection_model_rejects_absent_with_appearance_description():
    with pytest.raises(ValidationError):
        IPRoleSelectionResponse.model_validate(
            {
                "role_selections": [
                    {
                        "frame_index": 0,
                        "role_slot": "absent",
                        "role_label": "offscreen",
                        "presence_level": "not visible",
                        "appearance_description": "white rabbit appears in the background",
                    }
                ]
            }
        )


def test_parse_ip_role_selection_accepts_wrapped_alias_fields():
    raw = json.dumps(
        {
            "role_selections": [
                {
                    "frameIndex": "frame_0",
                    "role": "配角",
                    "label": "side guide",
                    "visibility": "half body",
                    "appearance": "white rabbit guide stays near the market stall",
                    "rationale": "supports the route narrative",
                },
                {
                    "frame": 1,
                    "roleSlot": "background extra",
                    "roleName": "market witness",
                    "presence": "small cameo",
                    "description": "blue necktie appears in the distant crowd",
                },
            ]
        },
        ensure_ascii=False,
    )

    parsed = parse_ip_role_selection_response(raw)

    assert parsed is not None
    assert [item["role_slot"] for item in parsed] == ["supporting", "passerby"]
    assert parsed[0]["frame_index"] == 0
    assert parsed[0]["role_label"] == "side guide"
    assert parsed[0]["appearance_description"] == "white rabbit guide stays near the market stall"
    assert parsed[0]["reason"] == "supports the route narrative"


def test_parse_ip_role_selection_accepts_embedded_nested_items():
    raw = """
    The role plan is:
    ```json
    {
      "data": {
        "items": [
          {
            "index": "0",
            "slot": "main character",
            "appearanceDescription": "white rabbit guide leads from the foreground"
          }
        ]
      }
    }
    ```
    """

    parsed = parse_ip_role_selection_response(raw)

    assert parsed is not None
    assert parsed[0]["role_slot"] == "protagonist"
    assert parsed[0]["role_label"] == "protagonist"
    assert parsed[0]["appearance_description"] == "white rabbit guide leads from the foreground"


def test_parse_ip_role_selection_accepts_keyed_frame_mapping():
    raw = json.dumps(
        {
            "1": {"role_slot": "passerby", "appearance": "distant blue necktie detail"},
            "0": {"role_slot": "supporting", "appearance": "side guide near the stall"},
        }
    )

    parsed = parse_ip_role_selection_response(raw)

    assert parsed is not None
    assert [item["role_slot"] for item in parsed] == ["supporting", "passerby"]
    assert parsed[0]["appearance_description"] == "side guide near the stall"
    assert parsed[1]["appearance_description"] == "distant blue necktie detail"


def test_parse_ip_role_selection_rejects_unknown_role_slot():
    raw = json.dumps([{"frame_index": 0, "role_slot": "logo_takeover"}])

    assert parse_ip_role_selection_response(raw) is None


@pytest.mark.asyncio
async def test_appearance_planner_uses_wrapped_llm_role_selection_response():
    captured: dict[str, object] = {}

    async def fake_llm(prompt: str, **kwargs) -> str:
        captured.update(kwargs)
        return json.dumps(
            {
                "data": [
                    {
                        "frameIndex": 0,
                        "role": "主角",
                        "roleLabel": "headline guide",
                        "presenceLevel": "foreground",
                        "appearanceDescription": "LLM selected hero guide with a blue necktie",
                    }
                ]
            },
            ensure_ascii=False,
        )

    frame = StoryboardPlanFrame(
        index=1,
        frame_id="frame_1",
        source_text="A quiet market route opens around a stone gate.",
        visual_goal="show the market route",
        prompt_intent="travel opening",
        primary_subject="stone gate and market",
    )

    packages = await IPFrameAppearancePlanner(llm_client=fake_llm).plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )

    assert packages[0].role_slot is IPRoleSlot.PROTAGONIST
    assert packages[0].appearance_description == "LLM selected hero guide with a blue necktie"
    assert captured["response_type"] is IPRoleSelectionResponse
    assert captured["temperature"] == 0.2
    assert captured["max_tokens"] == 1200
