import pytest

from pixelle_video.models.template_text_policy import (
    normalize_template_text_policy,
    resolve_caption_renderer_text,
    resolve_template_body_text,
    resolve_template_text_policy_for_body_override,
)


def test_template_text_policy_normalization_and_routing():
    assert normalize_template_text_policy(None) == "caption_renderer"
    assert resolve_template_body_text("body", "caption_renderer") == ""
    assert resolve_caption_renderer_text("caption", "caption_renderer") == "caption"
    assert resolve_template_body_text("body", "template_body") == "body"
    assert resolve_caption_renderer_text("caption", "template_body") == ""
    assert resolve_template_body_text("body", "explicit_both") == "body"
    assert resolve_caption_renderer_text("caption", "explicit_both") == "caption"
    assert resolve_template_body_text("body", "none") == ""
    assert resolve_caption_renderer_text("caption", "none") == ""


def test_template_text_policy_override_keeps_legacy_shell_semantics():
    assert resolve_template_text_policy_for_body_override("none", None) == "none"
    assert resolve_template_text_policy_for_body_override("none", "") == "caption_renderer"
    assert resolve_template_text_policy_for_body_override("caption_renderer", "custom") == "template_body"


def test_template_text_policy_rejects_unknown_policy():
    with pytest.raises(ValueError, match="template_text_policy"):
        normalize_template_text_policy("unsafe")
