import json
from pathlib import Path

from web.components import content_input


LOCALE_DIR = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"


def _load_translations(locale_name: str) -> dict:
    with (LOCALE_DIR / f"{locale_name}.json").open(encoding="utf-8") as file:
        return json.load(file)["t"]


class _FakeExpander:
    def __init__(self, fake_st, label: str):
        self._fake_st = fake_st
        self._label = label

    def __enter__(self):
        self._fake_st._context_stack.append(self._label)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._fake_st._context_stack.pop()
        return False


class _FakeColumn:
    def __init__(self, fake_st):
        self._fake_st = fake_st

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.expanders: list[dict] = []
        self.markdowns: list[dict] = []
        self.sliders: list[dict] = []
        self.number_inputs: list[dict] = []
        self.radio_values: dict[str, str] = {}
        self.checkbox_values: dict[str, bool] = {}
        self.checkbox_calls: list[dict] = []
        self.session_state: dict[str, int] = {}
        self._context_stack: list[str] = []

    def expander(self, label, expanded=False):
        self.expanders.append({"label": label, "expanded": expanded, "parent": self._current_parent()})
        return _FakeExpander(self, label)

    def markdown(self, body, **kwargs):
        self.markdowns.append({"body": body, "parent": self._current_parent(), **kwargs})

    def radio(self, _label, options, *, index=0, key=None, **_kwargs):
        return self.radio_values.get(key, list(options)[index])

    def checkbox(self, label, value=False, *, key=None, **kwargs):
        self.checkbox_calls.append({"label": label, "value": value, "key": key, **kwargs})
        return self.checkbox_values.get(key, value)

    def selectbox(self, _label, options, *, index=0, **_kwargs):
        return list(options)[index]

    def slider(self, label, *, value=None, **kwargs):
        self.sliders.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key is not None and key in self.session_state:
            return self.session_state[key]
        return value

    def number_input(self, label, *, value=None, **kwargs):
        self.number_inputs.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key is not None and key in self.session_state:
            return self.session_state[key]
        return value

    def columns(self, spec):
        return [_FakeColumn(self) for _ in spec]

    def caption(self, *_args, **_kwargs):
        return None

    def _current_parent(self):
        return self._context_stack[-1] if self._context_stack else None


def _fake_tr(key, fallback=None, **_kwargs):
    return fallback if fallback is not None else key


def test_storyboard_generation_explanation_has_locale_entries():
    en = _load_translations("en_US")
    zh = _load_translations("zh_CN")

    assert en["storyboard.generation.explanation.title"] == "Settings guide"
    assert "max_tokens" in en["storyboard.generation.explanation.body"]
    assert "not the storyboard frame count" in en["storyboard.generation.explanation.body"]
    assert "deployment cap" in en["storyboard.generation.explanation.body"]
    assert "up to 200 to avoid errors" not in en["storyboard.generation.explanation.body"]
    assert "max_tokens" in zh["storyboard.generation.explanation.body"]
    assert "不是分镜数量" in zh["storyboard.generation.explanation.body"]
    assert "部署" in zh["storyboard.generation.explanation.body"]


def test_storyboard_generation_controls_are_collapsed_with_nested_explanation(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)

    payload = content_input.render_storyboard_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert fake_st.expanders == [
        {"label": "🧭 分镜规划", "expanded": False, "parent": None},
        {"label": "设置说明", "expanded": False, "parent": "🧭 分镜规划"},
    ]
    assert any(
        "max_tokens" in call["body"] and "不是分镜数量" in call["body"]
        for call in fake_st.markdowns
    )
    assert payload == {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "auto",
        "storyboard_scene_count": None,
        "storyboard_max_scene_count": None,
        "storyboard_prompt_language": "zh_CN",
    }


def test_storyboard_generation_manual_slider_uses_configured_limits(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.radio_values["single_video_storyboard_count_mode"] = "manual"
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)
    monkeypatch.setattr(
        content_input,
        "get_storyboard_generation_limits",
        lambda: content_input.StoryboardGenerationLimits(
            min_scene_count=2,
            max_scene_count=8,
        ),
    )

    payload = content_input.render_storyboard_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert fake_st.sliders[0]["min_value"] == 2
    assert fake_st.sliders[0]["max_value"] == 8
    assert payload["storyboard_scene_count"] == 5


def test_storyboard_generation_controls_include_prompt_language_in_base_payload(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.radio_values["single_video_storyboard_prompt_language"] = "en_US"
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)

    payload = content_input.render_storyboard_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert payload["storyboard_prompt_language"] == "en_US"
    assert "world_preset_id" not in payload
    assert any(call["label"] == "storyboard.advanced_enabled" for call in fake_st.checkbox_calls)


def test_punctuation_storyboard_generation_controls_show_max_scene_slider(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.radio_values["single_video_storyboard_mode"] = "punctuation"
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)

    payload = content_input.render_storyboard_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert fake_st.sliders[0]["key"] == "single_video_storyboard_max_scene_count"
    assert fake_st.sliders[0]["min_value"] == 1
    assert fake_st.sliders[0]["max_value"] == 200
    assert fake_st.sliders[0]["value"] == 60
    assert payload["storyboard_max_scene_count"] == 60


def test_sentence_storyboard_generation_controls_show_max_scene_slider(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.radio_values["single_video_storyboard_mode"] = "sentence"
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)

    payload = content_input.render_storyboard_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert fake_st.sliders[0]["key"] == "single_video_storyboard_max_scene_count"
    assert fake_st.sliders[0]["min_value"] == 1
    assert fake_st.sliders[0]["max_value"] == 200
    assert fake_st.sliders[0]["value"] == 60
    assert payload["storyboard_max_scene_count"] == 60


def test_deterministic_storyboard_slider_uses_configured_limit_cap(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.radio_values["single_video_storyboard_mode"] = "punctuation"
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)
    monkeypatch.setattr(
        content_input,
        "get_storyboard_generation_limits",
        lambda: content_input.StoryboardGenerationLimits(
            min_scene_count=1,
            max_scene_count=4,
            deterministic_max_scene_count_limit=80,
        ),
    )

    payload = content_input.render_storyboard_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert fake_st.sliders[0]["min_value"] == 1
    assert fake_st.sliders[0]["max_value"] == 80
    assert fake_st.sliders[0]["value"] == 60
    assert payload["storyboard_max_scene_count"] == 60


def test_script_generation_target_words_control_uses_default_range_and_custom_payload(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)

    payload = content_input.render_script_generation_controls(
        mode="generate",
        key_prefix="single_video",
    )

    assert fake_st.sliders == [
        {
            "label": "script.target_words",
            "value": None,
            "min_value": 50,
            "max_value": 10000,
            "step": 50,
            "key": "single_video_script_target_words_slider",
            "help": "script.target_words_help",
            "on_change": content_input._sync_script_target_words_state,
            "kwargs": {
                "source_key": "single_video_script_target_words_slider",
                "target_key": "single_video_script_target_words_input",
            },
        }
    ]
    assert fake_st.number_inputs == [
        {
            "label": "script.target_words_input",
            "value": None,
            "min_value": 50,
            "max_value": 10000,
            "step": 50,
            "key": "single_video_script_target_words_input",
            "label_visibility": "collapsed",
            "on_change": content_input._sync_script_target_words_state,
            "kwargs": {
                "source_key": "single_video_script_target_words_input",
                "target_key": "single_video_script_target_words_slider",
            },
        }
    ]
    assert fake_st.session_state == {
        "single_video_script_target_words_slider": 200,
        "single_video_script_target_words_input": 200,
    }
    assert payload == {
        "script_length_mode": "custom",
        "script_target_words": 200,
    }


def test_script_generation_target_words_control_is_hidden_for_fixed_mode(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(content_input, "st", fake_st)
    monkeypatch.setattr(content_input, "tr", _fake_tr)

    payload = content_input.render_script_generation_controls(
        mode="fixed",
        key_prefix="single_video",
    )

    assert fake_st.sliders == []
    assert fake_st.number_inputs == []
    assert payload == {
        "script_length_mode": "auto",
        "script_target_words": None,
    }
