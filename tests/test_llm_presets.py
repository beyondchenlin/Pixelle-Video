from pixelle_video.llm_presets import get_preset


def test_qwen_preset_keeps_legacy_default_and_exposes_long_context_variant():
    assert get_preset("Qwen")["model"] == "qwen-max"
    assert get_preset("Qwen 3.6 Plus")["model"] == "qwen3.6-plus"
