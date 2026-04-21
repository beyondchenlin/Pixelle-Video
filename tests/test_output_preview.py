from web.components.output_preview import build_video_preview_css


def test_build_video_preview_css_targets_local_preview_container():
    css = build_video_preview_css("output_preview_media", scale_percent=50)

    assert ".st-key-output_preview_media [data-testid=\"stVideo\"]" in css
    assert "width: 50%;" in css
    assert "margin-inline: auto;" in css
    assert ".st-key-output_preview_media [data-testid=\"stVideo\"] video" in css
    assert "width: 100%;" in css
