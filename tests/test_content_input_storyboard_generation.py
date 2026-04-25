from web.components import content_input


def test_storyboard_generation_payload_defaults_to_smart_auto():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=5,
        script_length_mode="auto",
        script_target_words=180,
    )

    assert payload == {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "auto",
        "storyboard_scene_count": None,
        "script_length_mode": "auto",
        "script_target_words": None,
    }


def test_storyboard_generation_payload_keeps_manual_count_for_smart_mode():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=6,
        script_length_mode="custom",
        script_target_words=220,
    )

    assert payload == {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "manual",
        "storyboard_scene_count": 6,
        "script_length_mode": "custom",
        "script_target_words": 220,
    }


def test_storyboard_generation_payload_for_deterministic_modes_uses_auto_count():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="sentence",
        storyboard_count_mode="manual",
        storyboard_scene_count=6,
        script_length_mode="short",
        script_target_words=220,
    )

    assert payload == {
        "storyboard_mode": "sentence",
        "storyboard_count_mode": "auto",
        "storyboard_scene_count": None,
        "script_length_mode": "short",
        "script_target_words": None,
    }
