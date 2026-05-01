import json
from pathlib import Path

from pixelle_video.models.render_package import RenderManifest
from pixelle_video.models.text_render_package import TextRenderPackage

FIXTURE_DIR = Path("tests/fixtures/text_rendering")


def test_text_render_package_golden_fixtures_are_versioned():
    for name in [
        "text_render_package_legacy_caption.json",
        "text_render_package_overlay_hybrid.json",
    ]:
        payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        assert payload["version"] == "text_render_package.v1"
        assert payload["caption_settings"]["version"] == "caption_rendering_settings.v1"
        assert "text_style_profiles" in payload


def test_legacy_caption_fixture_contains_single_caption_and_no_overlay_text():
    payload = json.loads(
        (FIXTURE_DIR / "text_render_package_legacy_caption.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(payload["caption_cues"]) == 1
    assert payload["text_tracks"] == []
    assert payload["text_cues"] == []
    assert [profile["id"] for profile in payload["text_style_profiles"]] == [
        "caption-default",
        "title-default",
    ]


def test_overlay_hybrid_fixture_contains_caption_overlay_and_native_hint_diagnostic():
    payload = json.loads(
        (FIXTURE_DIR / "text_render_package_overlay_hybrid.json").read_text(
            encoding="utf-8"
        )
    )

    assert [profile["id"] for profile in payload["text_style_profiles"]] == [
        "caption-default",
        "title-default",
        "overlay-default",
    ]
    assert payload["caption_cues"][0]["style_profile"] == "caption-default"
    assert payload["text_cues"][0]["style_profile"] == "overlay-default"
    assert payload["diagnostics"]["native_hints"]["count"] == 1
    assert payload["diagnostics"]["native_hints"]["source"] == "text_overlay_plan"


def test_render_manifest_with_text_styles_fixture_is_versioned():
    payload = json.loads(
        (FIXTURE_DIR / "render_manifest_with_text_styles.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["version"] == "render_manifest.v1"
    assert [profile["id"] for profile in payload["text_style_profiles"]] == [
        "caption-default",
        "title-default",
        "overlay-default",
    ]
    assert payload["text_cues"][0]["style_profile"] == "overlay-default"


def test_text_render_package_golden_fixtures_round_trip_through_model():
    for name in [
        "text_render_package_legacy_caption.json",
        "text_render_package_overlay_hybrid.json",
    ]:
        payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

        restored = TextRenderPackage.from_dict(payload).to_dict()

        assert restored["version"] == "text_render_package.v1"
        assert restored["task_id"] == payload["task_id"]
        assert restored["caption_settings"]["style_profile"] == "caption-default"
        assert restored["layout_plan"]["version"] == "text_layout_plan.v1"
        assert [profile["id"] for profile in restored["text_style_profiles"]]


def test_render_manifest_with_text_styles_fixture_round_trips_through_model():
    payload = json.loads(
        (FIXTURE_DIR / "render_manifest_with_text_styles.json").read_text(
            encoding="utf-8"
        )
    )

    restored = RenderManifest.from_dict(payload).to_dict()

    assert restored["version"] == "render_manifest.v1"
    assert [profile["id"] for profile in restored["text_style_profiles"]] == [
        "caption-default",
        "title-default",
        "overlay-default",
    ]
