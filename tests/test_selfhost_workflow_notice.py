from pathlib import Path

import web.components.selfhost_workflow_notice as selfhost_notice


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.container_calls = []
        self.markdown_calls = []
        self.warning_calls = []

    def container(self, **kwargs):
        self.container_calls.append(kwargs)
        return _FakeContext()

    def markdown(self, body, **_kwargs):
        self.markdown_calls.append(body)

    def warning(self, body, **_kwargs):
        self.warning_calls.append(body)


def test_selfhost_workflow_notice_renders_inline_guidance(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(selfhost_notice, "st", fake_st)
    monkeypatch.setattr(
        selfhost_notice.config_manager,
        "get_comfyui_config",
        lambda: {"comfyui_url": "http://127.0.0.1:8000"},
    )

    def _tr(key, **kwargs):
        if key == "selfhost.warning.message":
            return f"run {kwargs['workflow_path']} at {kwargs['comfyui_url']}"
        return key

    monkeypatch.setattr(selfhost_notice, "tr", _tr)

    rendered = selfhost_notice.render_selfhost_workflow_notice(
        "selfhost/image_z_image_turbo.json",
    )

    assert rendered is True
    assert fake_st.container_calls == [{"border": True}]
    inline_markdown = "\n".join(fake_st.markdown_calls)
    assert "selfhost.warning.inline_title" in inline_markdown
    assert "workflows/selfhost/image_z_image_turbo.json" in inline_markdown
    assert "http://127.0.0.1:8000" in inline_markdown
    assert fake_st.warning_calls == ["selfhost.warning.hint"]


def test_selfhost_workflow_notice_ignores_runninghub_workflows(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(selfhost_notice, "st", fake_st)

    rendered = selfhost_notice.render_selfhost_workflow_notice(
        "runninghub/image_flux.json",
    )

    assert rendered is False
    assert fake_st.container_calls == []


def test_legacy_popup_warning_api_is_removed_from_web_code():
    legacy_name = "check_and_warn" + "_selfhost_workflow"
    web_files = [
        path
        for path in Path("web").rglob("*.py")
        if "__pycache__" not in path.parts
    ]

    offenders = [
        str(path)
        for path in web_files
        if legacy_name in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
