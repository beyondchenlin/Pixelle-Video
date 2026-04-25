from types import SimpleNamespace

from pixelle_video.tts_audio_strategy import SUPPORTED_TTS_AUDIO_STRATEGIES
from pixelle_video.tts_split_strategy import SUPPORTED_TTS_SPLIT_MODES
from web.components import style_config


class _FakeStreamlit:
    def __init__(self) -> None:
        self.radio_calls = []
        self.captions = []

    def radio(
        self,
        label,
        options,
        *,
        index,
        horizontal,
        format_func,
        key,
        help,
        **_kwargs,
    ):
        options = list(options)
        self.radio_calls.append(
            {
                "label": label,
                "options": options,
                "index": index,
                "horizontal": horizontal,
                "format_func": format_func,
                "key": key,
                "help": help,
            }
        )
        return options[index]

    def caption(self, value):
        self.captions.append(value)

    def checkbox(self, _label, *, value, **_kwargs):
        return value

    def selectbox(self, _label, options, *, index, **_kwargs):
        return list(options)[index]

    def number_input(self, _label, *, value, **_kwargs):
        return value


def _fake_config_manager() -> SimpleNamespace:
    timing_config = SimpleNamespace(
        tts_audio_strategy="auto",
        tts_split_mode="internal_only",
        max_chars_per_tts_segment=120,
        tts_split_overflow_policy="hard_limit",
        tts_boundary_search_radius=24,
        tts_soft_overflow_chars=12,
        tts_audio_boundary_fade_ms=8,
        tts_sentence_joiner_mode="direct",
        caption_punctuation_mode="strip_all",
        preserve_natural_punctuation=True,
    )
    return SimpleNamespace(
        config=SimpleNamespace(render=SimpleNamespace(timing=timing_config))
    )


def test_tts_selectors_render_as_inline_radio_groups(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "config_manager", _fake_config_manager())

    selected_strategy = style_config.render_tts_audio_strategy_selector()
    split_settings = style_config.render_tts_split_settings()

    assert selected_strategy == "auto"
    assert split_settings["tts_split_mode"] == "internal_only"

    radio_calls_by_key = {call["key"]: call for call in fake_st.radio_calls}
    assert radio_calls_by_key["tts_audio_strategy_select"]["horizontal"] is True
    assert radio_calls_by_key["tts_audio_strategy_select"]["options"] == list(
        SUPPORTED_TTS_AUDIO_STRATEGIES
    )
    assert radio_calls_by_key["tts_split_mode_select"]["horizontal"] is True
    assert radio_calls_by_key["tts_split_mode_select"]["options"] == list(
        SUPPORTED_TTS_SPLIT_MODES
    )


def test_tts_selector_functions_route_through_shared_inline_radio(monkeypatch):
    fake_st = _FakeStreamlit()
    inline_radio_calls = []

    def fake_render_inline_radio(
        label,
        options,
        *,
        index,
        format_func,
        key,
        help_text,
    ):
        options = list(options)
        inline_radio_calls.append(
            {
                "label": label,
                "options": options,
                "index": index,
                "format_func": format_func,
                "key": key,
                "help_text": help_text,
            }
        )
        return options[index]

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "config_manager", _fake_config_manager())
    monkeypatch.setattr(style_config, "_render_tts_inline_radio", fake_render_inline_radio)

    style_config.render_tts_audio_strategy_selector()
    style_config.render_tts_split_settings()

    assert [
        {
            "label": call["label"],
            "options": call["options"],
            "index": call["index"],
            "key": call["key"],
            "help_text": call["help_text"],
        }
        for call in inline_radio_calls
    ] == [
        {
            "label": "tts_audio_strategy.label",
            "options": list(SUPPORTED_TTS_AUDIO_STRATEGIES),
            "index": 0,
            "key": "tts_audio_strategy_select",
            "help_text": "tts_audio_strategy.help",
        },
        {
            "label": "tts_split_mode.label",
            "options": list(SUPPORTED_TTS_SPLIT_MODES),
            "index": 0,
            "key": "tts_split_mode_select",
            "help_text": "tts_split_mode.help",
        },
    ]
