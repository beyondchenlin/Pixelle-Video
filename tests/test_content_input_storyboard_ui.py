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


class _FakeStreamlit:
    def __init__(self) -> None:
        self.expanders: list[dict] = []
        self.markdowns: list[dict] = []
        self._context_stack: list[str] = []

    def expander(self, label, expanded=False):
        self.expanders.append({"label": label, "expanded": expanded, "parent": self._current_parent()})
        return _FakeExpander(self, label)

    def markdown(self, body, **kwargs):
        self.markdowns.append({"body": body, "parent": self._current_parent(), **kwargs})

    def radio(self, _label, options, *, index=0, **_kwargs):
        return list(options)[index]

    def selectbox(self, _label, options, *, index=0, **_kwargs):
        return list(options)[index]

    def slider(self, _label, *, value, **_kwargs):
        return value

    def number_input(self, _label, *, value, **_kwargs):
        return value

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
    assert "max_tokens" in zh["storyboard.generation.explanation.body"]
    assert "不是分镜数量" in zh["storyboard.generation.explanation.body"]


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
        "script_length_mode": "auto",
        "script_target_words": None,
    }
