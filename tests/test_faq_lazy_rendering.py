from web.components import faq


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self, selected=None):
        self.sidebar = _Context()
        self.session_state = {}
        self.selected = selected
        self.markdowns = []
        self.expanded_values = []

    def expander(self, _label, *, expanded=False):
        self.expanded_values.append(expanded)
        return _Context()

    def selectbox(self, _label, options, **_kwargs):
        assert options[0] is None
        return self.selected

    def markdown(self, body, **kwargs):
        self.markdowns.append((body, kwargs))


FAQ_CONTENT = """# FAQ

### First
First answer <img src="https://example.test/first.png" alt="first" />

### Second
Second answer <img src="https://example.test/second.png" alt="second" />
"""


def test_default_faq_does_not_render_hidden_answers_or_images(monkeypatch):
    fake = _FakeStreamlit()
    monkeypatch.setattr(faq, "st", fake)
    monkeypatch.setattr(faq, "get_language", lambda: "en_US")
    monkeypatch.setattr(faq, "load_faq_content", lambda _language: FAQ_CONTENT)
    monkeypatch.setattr(faq, "tr", lambda key, **_kwargs: key)

    faq.render_faq_sidebar()

    rendered = "\n".join(body for body, _kwargs in fake.markdowns)
    assert "example.test" not in rendered
    assert fake.expanded_values == [False]


def test_faq_renders_only_the_selected_answer(monkeypatch):
    fake = _FakeStreamlit(selected="First")
    monkeypatch.setattr(faq, "st", fake)
    monkeypatch.setattr(faq, "get_language", lambda: "en_US")
    monkeypatch.setattr(faq, "load_faq_content", lambda _language: FAQ_CONTENT)
    monkeypatch.setattr(faq, "tr", lambda key, **_kwargs: key)

    faq.render_faq_sidebar()

    rendered = "\n".join(body for body, _kwargs in fake.markdowns)
    assert "https://example.test/first.png" in rendered
    assert "https://example.test/second.png" not in rendered
    assert all(not kwargs.get("unsafe_allow_html") for _body, kwargs in fake.markdowns)


def test_prepare_faq_answer_drops_non_http_image_sources():
    answer = '<img src="javascript:alert(1)" alt="bad" /> safe text'

    assert faq.prepare_faq_answer(answer) == " safe text"


def test_faq_clears_question_state_when_language_options_change(monkeypatch):
    fake = _FakeStreamlit()
    fake.session_state["faq_selected_question"] = "旧语言问题"
    monkeypatch.setattr(faq, "st", fake)
    monkeypatch.setattr(faq, "get_language", lambda: "en_US")
    monkeypatch.setattr(faq, "load_faq_content", lambda _language: FAQ_CONTENT)
    monkeypatch.setattr(faq, "tr", lambda key, **_kwargs: key)

    faq.render_faq_sidebar()

    assert "faq_selected_question" not in fake.session_state
