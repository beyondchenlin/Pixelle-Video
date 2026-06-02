from web.components import article_concretization_controls


class _FakeExpander:
    def __init__(self, fake_ui, label: str):
        self._fake_ui = fake_ui
        self._label = label

    def __enter__(self):
        self._fake_ui._context_stack.append(self._label)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._fake_ui._context_stack.pop()
        return False


class _FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.checkbox_values: dict[str, bool] = {}
        self.selectbox_values: dict[str, str] = {}
        self.text_area_values: dict[str, str] = {}
        self.expanders: list[dict] = []
        self.checkboxes: list[dict] = []
        self.selectboxes: list[dict] = []
        self.text_areas: list[dict] = []
        self.captions: list[str] = []
        self._context_stack: list[str] = []

    def expander(self, label, expanded=False):
        self.expanders.append(
            {"label": label, "expanded": expanded, "parent": self._current_parent()}
        )
        return _FakeExpander(self, label)

    def checkbox(self, label, value=False, *, key=None, **kwargs):
        self.checkboxes.append({"label": label, "value": value, "key": key, **kwargs})
        return self.checkbox_values.get(key, value)

    def selectbox(self, label, options, *, index=0, key=None, **kwargs):
        options = list(options)
        self.selectboxes.append(
            {
                "label": label,
                "options": options,
                "index": index,
                "key": key,
                **kwargs,
            }
        )
        return self.selectbox_values.get(key, options[index])

    def text_area(self, label, *, value="", key=None, **kwargs):
        self.text_areas.append({"label": label, "value": value, "key": key, **kwargs})
        return self.text_area_values.get(key, value)

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn() for _ in range(count)]

    def caption(self, body):
        self.captions.append(body)

    def _current_parent(self):
        return self._context_stack[-1] if self._context_stack else None


def _fake_tr(key, fallback=None, **_kwargs):
    return fallback if fallback is not None else key


def test_build_payload_default_controls_only():
    payload = article_concretization_controls.build_article_concretization_payload(
        enabled=True,
    )

    assert payload == {
        "article_concretization_enabled": True,
        "cognitive_anchor_kind": "auto",
        "explanation_diagram_grammar": "auto",
        "series_visual_signature_role": "none",
        "diagram_render_style": "auto",
        "diagram_aspect_ratio": "auto",
        "diagram_visible_text_policy": "no_visible_text",
        "diagram_approved_labels": [],
        "diagram_user_intent_hint": None,
    }


def test_build_payload_advanced_controls():
    payload = article_concretization_controls.build_article_concretization_payload(
        enabled=True,
        cognitive_anchor_kind="causal_mechanism",
        explanation_diagram_grammar="process_flow",
        diagram_render_style="xiaohei_handdrawn",
        series_visual_signature_role="guide",
        diagram_aspect_ratio="portrait_4_5",
        diagram_visible_text_policy="approved_labels_only",
        diagram_approved_labels=["cash flow", "risk"],
        diagram_user_intent_hint="show the tradeoff as a decision point",
    )

    assert payload == {
        "article_concretization_enabled": True,
        "cognitive_anchor_kind": "causal_mechanism",
        "explanation_diagram_grammar": "process_flow",
        "series_visual_signature_role": "guide",
        "diagram_render_style": "xiaohei_handdrawn",
        "diagram_aspect_ratio": "portrait_4_5",
        "diagram_visible_text_policy": "approved_labels_only",
        "diagram_approved_labels": ["cash flow", "risk"],
        "diagram_user_intent_hint": "show the tradeoff as a decision point",
    }


def test_build_payload_trims_hint_and_labels():
    payload = article_concretization_controls.build_article_concretization_payload(
        enabled=True,
        diagram_approved_labels=" 增长, 风险\n成本，效率、收益 ,, \n ",
        diagram_user_intent_hint="  make cause and effect visible  ",
    )

    assert payload["diagram_approved_labels"] == [
        "增长",
        "风险",
        "成本",
        "效率",
        "收益",
    ]
    assert payload["diagram_user_intent_hint"] == "make cause and effect visible"


def test_controls_do_not_disable_entire_expander_for_static_template():
    fake_ui = _FakeStreamlit()
    fake_ui.checkbox_values["single_video_article_concretization_enabled"] = True

    payload = article_concretization_controls.render_article_concretization_controls(
        ui=fake_ui,
        translate=_fake_tr,
        key_prefix="single_video",
        selected_template_type_for_storyboard="static",
    )

    assert fake_ui.expanders[0] == {
        "label": "文章具象化解读",
        "expanded": False,
        "parent": None,
    }
    checkbox_by_key = {call["key"]: call for call in fake_ui.checkboxes}
    assert checkbox_by_key["single_video_article_concretization_enabled"].get(
        "disabled", False
    ) is False

    selectbox_disabled = {
        call["key"]: call.get("disabled", False) for call in fake_ui.selectboxes
    }
    assert selectbox_disabled["single_video_cognitive_anchor_kind"] is False
    assert selectbox_disabled["single_video_explanation_diagram_grammar"] is False
    assert selectbox_disabled["single_video_diagram_render_style"] is False
    assert selectbox_disabled["single_video_series_visual_signature_role"] is False
    assert selectbox_disabled["single_video_diagram_visible_text_policy"] is False
    assert selectbox_disabled["single_video_diagram_aspect_ratio"] is True
    assert any("图解面板比例" in caption for caption in fake_ui.captions)
    assert "strict_user_mode" not in {call["key"] for call in fake_ui.selectboxes}
    assert payload["article_concretization_enabled"] is True


def test_static_template_forces_payload_to_follow_template_ratio_even_with_stale_state():
    fake_ui = _FakeStreamlit()
    fake_ui.checkbox_values["single_video_article_concretization_enabled"] = True
    fake_ui.selectbox_values["single_video_diagram_aspect_ratio"] = "landscape_16_9"

    payload = article_concretization_controls.render_article_concretization_controls(
        ui=fake_ui,
        translate=_fake_tr,
        key_prefix="single_video",
        selected_template_type_for_storyboard="static",
    )

    assert payload["diagram_aspect_ratio"] == "template"
    selectbox_disabled = {
        call["key"]: call.get("disabled", False) for call in fake_ui.selectboxes
    }
    assert selectbox_disabled["single_video_diagram_aspect_ratio"] is True
    assert selectbox_disabled["single_video_cognitive_anchor_kind"] is False
    assert selectbox_disabled["single_video_explanation_diagram_grammar"] is False
    assert selectbox_disabled["single_video_diagram_render_style"] is False
    assert selectbox_disabled["single_video_series_visual_signature_role"] is False
    assert selectbox_disabled["single_video_diagram_visible_text_policy"] is False
