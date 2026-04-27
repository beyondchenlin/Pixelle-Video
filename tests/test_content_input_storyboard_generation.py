from web.components import content_input


def test_storyboard_generation_payload_defaults_to_smart_auto():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=5,
    )

    assert payload == {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "auto",
        "storyboard_scene_count": None,
        "storyboard_prompt_language": "zh_CN",
    }


def test_storyboard_generation_payload_keeps_manual_count_for_smart_mode():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=6,
    )

    assert payload == {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "manual",
        "storyboard_scene_count": 6,
        "storyboard_prompt_language": "zh_CN",
    }


def test_storyboard_generation_payload_for_deterministic_modes_uses_auto_count():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="sentence",
        storyboard_count_mode="manual",
        storyboard_scene_count=6,
    )

    assert payload == {
        "storyboard_mode": "sentence",
        "storyboard_count_mode": "auto",
        "storyboard_scene_count": None,
        "storyboard_prompt_language": "zh_CN",
    }


def test_storyboard_generation_payload_keeps_prompt_language_for_basic_controls():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
        storyboard_prompt_language="zh_CN",
    )

    assert payload["storyboard_prompt_language"] == "zh_CN"


def test_storyboard_generation_payload_normalizes_unknown_prompt_language_to_chinese_default():
    payload = content_input.build_storyboard_generation_payload(
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
        storyboard_prompt_language="unexpected",
    )

    assert payload["storyboard_prompt_language"] == "zh_CN"


def test_script_generation_payload_uses_custom_target_words_for_generate_mode():
    payload = content_input.build_script_generation_payload(
        mode="generate",
        script_target_words=200,
    )

    assert payload == {
        "script_length_mode": "custom",
        "script_target_words": 200,
    }


def test_script_generation_payload_omits_target_words_for_fixed_mode():
    payload = content_input.build_script_generation_payload(
        mode="fixed",
        script_target_words=200,
    )

    assert payload == {
        "script_length_mode": "auto",
        "script_target_words": None,
    }


def test_script_generation_target_words_are_clamped_to_supported_ui_range():
    assert content_input.build_script_generation_payload(
        mode="generate",
        script_target_words=1,
    )["script_target_words"] == 50
    assert content_input.build_script_generation_payload(
        mode="generate",
        script_target_words=3000,
    )["script_target_words"] == 2000
