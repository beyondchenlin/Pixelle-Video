from pathlib import Path

from pixelle_video.services.template_media_lint import lint_media_template


def test_lint_accepts_standard_media_layer_placeholder(tmp_path):
    template = tmp_path / "image_standard.html"
    template.write_text(
        "<html><body><div class='stage'>{{pixelle_media_layer}}</div></body></html>",
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert result.errors == []


def test_lint_rejects_bare_image_tag(tmp_path):
    template = tmp_path / "image_bad.html"
    template.write_text('<html><body><img src="{{image}}"></body></html>', encoding="utf-8")

    result = lint_media_template(template)

    assert any("bare {{image}}" in error for error in result.errors)


def test_lint_rejects_background_image_main_media(tmp_path):
    template = tmp_path / "image_bad_background.html"
    template.write_text(
        '<html><style>.hero{background-image:url("{{image}}")}</style></html>',
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert any("background-image" in error for error in result.errors)


def test_lint_rejects_script_image_injection(tmp_path):
    template = tmp_path / "asset_bad.html"
    template.write_text(
        '<html><body>{{pixelle_media_layer}}<script>var imageUrl = "{{image}}";</script></body></html>',
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert any("raw {{image}}" in error for error in result.errors)


def test_lint_does_not_accept_standard_layer_placeholder_only_in_comment(tmp_path):
    template = tmp_path / "image_comment.html"
    template.write_text(
        "<html><body><!-- {{pixelle_media_layer}} --></body></html>",
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert any("missing {{pixelle_media_layer}}" in error for error in result.errors)


def test_lint_rejects_template_owned_standard_media_geometry(tmp_path):
    template = tmp_path / "image_bad_geometry.html"
    template.write_text(
        "<html><style>.card .pixelle-media-box { width: 50%; object-fit: cover; }"
        "</style><body>{{pixelle_media_layer}}</body></html>",
        encoding="utf-8",
    )

    result = lint_media_template(template)

    assert any("protected standard media geometry" in error for error in result.errors)


def test_all_repository_image_video_and_asset_templates_use_standard_layer():
    failures = {}
    for path in sorted(Path("templates").rglob("*.html")):
        if not path.name.startswith(("image_", "video_", "asset_")):
            continue
        result = lint_media_template(path)
        if result.errors:
            failures[str(path)] = result.errors

    assert failures == {}
