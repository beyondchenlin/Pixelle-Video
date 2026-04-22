from web.components.style_config import build_storyboard_control_payload


def test_build_storyboard_control_payload_includes_storyboard_fields():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
        consistency_strength="strong",
        content_mode="concept_explainer",
        role_strategy="auto",
        role_locking_strength="strong",
        shot_strategy="strict",
        frame_overrides=[
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "shot_preset_id": "balanced_explainer",
        "consistency_strength": "strong",
        "content_mode": "concept_explainer",
        "role_strategy": "auto",
        "role_locking_strength": "strong",
        "shot_strategy": "strict",
        "frame_overrides": [
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    }
