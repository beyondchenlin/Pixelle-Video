from pixelle_video.services.text_content_sanitizer import TextContentSanitizer


def test_sanitizer_removes_ass_override_tags_controls_and_dangerous_html():
    raw_text = "Hi\u200b{\\pos(1,2)}<script>alert(1)</script>\x08 there"

    result = TextContentSanitizer().sanitize(raw_text)

    assert result.raw_text == raw_text
    assert result.display_text == "Hi there"
    assert result.requires_html_escape is True
    assert result.requires_ass_escape is True
    assert "<script>" not in result.display_text.lower()
    assert "{\\pos" not in result.display_text


def test_sanitizer_reports_removed_tokens_without_emitting_renderer_strings():
    result = TextContentSanitizer().sanitize(
        "Title {\\an8}<b>bold</b> style=color:red; drawtext=text='x'"
    )

    assert "{\\an8}" in result.removed_tokens
    assert "<b>" in result.removed_tokens
    assert "</b>" in result.removed_tokens
    assert "style=color:red;" in result.removed_tokens
    assert "drawtext=text='x'" in result.removed_tokens
    assert result.display_text == "Title bold"
    assert "style=" not in result.display_text
    assert "drawtext" not in result.display_text
    assert "<" not in result.display_text
    assert "{" not in result.display_text


def test_sanitizer_marks_escape_requirements_for_sensitive_plain_text():
    result = TextContentSanitizer().sanitize("5 < 6 & path {name}")

    assert result.display_text == "5 < 6 & path {name}"
    assert result.requires_html_escape is True
    assert result.requires_ass_escape is True
    assert result.removed_tokens == ()


def test_sanitizer_preserves_explicit_line_breaks_for_backend_parity():
    result = TextContentSanitizer().sanitize("first line\n  second   line")

    assert result.display_text == "first line\nsecond line"


def test_sanitizer_removes_quoted_css_and_ffmpeg_fragments_without_trailing_leakage():
    result = TextContentSanitizer().sanitize(
        'Title style="color: red;" drawtext=text=\'hello world\' keep'
    )

    assert result.display_text == "Title keep"
    assert 'style="color: red;"' in result.removed_tokens
    assert "drawtext=text='hello world'" in result.removed_tokens
    assert "style=" not in result.display_text.lower()
    assert "drawtext=" not in result.display_text.lower()
    assert 'red;"' not in result.display_text
    assert "world'" not in result.display_text


def test_sanitizer_removes_multi_argument_quoted_drawtext_filter():
    fragment = "drawtext=fontfile='C:/foo bar.ttf':text='hello world':fontsize=20"
    result = TextContentSanitizer().sanitize(f"Title {fragment} keep")

    assert result.display_text == "Title keep"
    assert fragment in result.removed_tokens
    assert "drawtext" not in result.display_text.lower()
    assert "fontfile" not in result.display_text.lower()
    assert "fontsize" not in result.display_text.lower()
    assert "hello world" not in result.display_text.lower()
