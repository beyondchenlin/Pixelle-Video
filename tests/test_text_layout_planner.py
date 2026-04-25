from pixelle_video.services.text_layout_planner import TextLayoutPlanner


def test_layout_planner_wraps_cjk_by_display_width_and_reports_safe_area_slot():
    result = TextLayoutPlanner().plan_text(
        "你好世界和平",
        max_display_width=6,
        slot="bottom",
        layer="caption",
    )

    assert result.wrapped_lines == ("你好世", "界和平")
    assert result.safe_area == "caption_safe_area"
    assert result.slot == "bottom"
    assert result.layer == "caption"
    assert result.diagnostics["line_display_widths"] == (6, 6)
    assert result.diagnostics["max_display_width"] == 6
    assert "css" not in str(result.to_dict()).lower()
    assert "ffmpeg" not in str(result.to_dict()).lower()
    assert "force_style" not in str(result.to_dict()).lower()


def test_layout_planner_preserves_short_ascii_and_records_display_width():
    result = TextLayoutPlanner().plan_text(
        "Short ASCII",
        max_display_width=20,
        slot="center",
        layer="overlay",
    )

    assert result.wrapped_lines == ("Short ASCII",)
    assert result.safe_area == "text_safe_area"
    assert result.diagnostics["raw_display_width"] == 11
    assert result.diagnostics["line_display_widths"] == (11,)


def test_layout_planner_wraps_mixed_width_text_without_splitting_by_bytes():
    result = TextLayoutPlanner().plan_text("AB中文CD", max_display_width=4)

    assert result.wrapped_lines == ("AB中", "文CD")
    assert result.diagnostics["line_display_widths"] == (4, 4)


def test_layout_planner_sanitizes_renderer_private_strings_before_wrapping():
    result = TextLayoutPlanner().plan_text(
        "Title {\\an8}<b>bold</b> drawtext=text='x' style=color:red;",
        max_display_width=40,
    )

    serialized = str(result.to_dict()).lower()

    assert result.wrapped_lines == ("Title bold",)
    assert "{\\an8}" not in serialized
    assert "<b>" not in serialized
    assert "</b>" not in serialized
    assert "drawtext=" not in serialized
    assert "style=" not in serialized


def test_layout_planner_wraps_combining_mark_grapheme_clusters_together():
    result = TextLayoutPlanner().plan_text("e\u0301e\u0301", max_display_width=1)

    assert result.wrapped_lines == ("e\u0301", "e\u0301")
    assert result.diagnostics["line_display_widths"] == (1, 1)


def test_layout_planner_serialization_omits_quoted_renderer_fragments():
    result = TextLayoutPlanner().plan_text(
        'Title style="color: red;" drawtext=text=\'hello world\' keep',
        max_display_width=40,
    )

    serialized = str(result.to_dict()).lower()

    assert result.wrapped_lines == ("Title keep",)
    assert "style=" not in serialized
    assert "drawtext=" not in serialized
    assert 'red;"' not in serialized
    assert "world'" not in serialized
