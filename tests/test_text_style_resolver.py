import pytest

from pixelle_video.models.render_package import TextCue, TextTrack
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
)
from pixelle_video.services.text_style_resolver import TextStyleResolver


def _cue(**overrides):
    payload = {
        "id": "cue-1",
        "track_id": "track-1",
        "text": "Visible text",
        "start": 0,
        "end": 1,
        "role": "keyword",
    }
    payload.update(overrides)
    return TextCue(**payload)


def _track(**overrides):
    payload = {
        "id": "track-1",
        "kind": "overlay",
        "name": "Overlay",
        "renderer_targets": ("hyperframes",),
    }
    payload.update(overrides)
    return TextTrack(**payload)


def test_resolver_prefers_cue_style_then_track_style_then_role_default():
    resolver = TextStyleResolver(
        profiles=(
            TextStyleProfile(id="cue-style", name="Cue"),
            TextStyleProfile(id="track-style", name="Track"),
        )
    )

    assert (
        resolver.resolve_for_cue(
            cue=_cue(style_profile="cue-style"),
            track=_track(style_profile="track-style"),
        ).id
        == "cue-style"
    )
    assert (
        resolver.resolve_for_cue(
            cue=_cue(style_profile=None),
            track=_track(style_profile="track-style"),
        ).id
        == "track-style"
    )
    assert (
        resolver.resolve_for_cue(
            cue=_cue(style_profile=None, role="subtitle"),
            track=_track(style_profile=None, kind="subtitle"),
        ).id
        == DEFAULT_CAPTION_STYLE_ID
    )


def test_resolver_records_fallback_for_missing_requested_style():
    resolver = TextStyleResolver(profiles=())

    profile = resolver.resolve_for_cue(
        cue=_cue(role="subtitle"),
        track=_track(kind="subtitle", style_profile="missing-style"),
    )

    assert profile.id == DEFAULT_CAPTION_STYLE_ID
    assert resolver.diagnostics["fallbacks"] == [
        {
            "cue_id": "cue-1",
            "missing_style_id": "missing-style",
            "resolved_style_id": DEFAULT_CAPTION_STYLE_ID,
        }
    ]


def test_resolver_records_fallback_when_missing_cue_style_resolves_to_track_style():
    resolver = TextStyleResolver(
        profiles=(TextStyleProfile(id="track-style", name="Track"),)
    )

    profile = resolver.resolve_for_cue(
        cue=_cue(style_profile="missing-cue-style"),
        track=_track(style_profile="track-style"),
    )

    assert profile.id == "track-style"
    assert resolver.diagnostics["fallbacks"] == [
        {
            "cue_id": "cue-1",
            "missing_style_id": "missing-cue-style",
            "resolved_style_id": "track-style",
        }
    ]


def test_resolver_records_full_missing_style_chain_when_falling_back_to_default():
    resolver = TextStyleResolver(profiles=())

    profile = resolver.resolve_for_cue(
        cue=_cue(style_profile="missing-cue", role="subtitle"),
        track=_track(kind="subtitle", style_profile="missing-track"),
    )

    assert profile.id == DEFAULT_CAPTION_STYLE_ID
    assert resolver.diagnostics["fallbacks"] == [
        {
            "cue_id": "cue-1",
            "missing_style_id": "missing-cue",
            "missing_style_ids": ["missing-cue", "missing-track"],
            "resolved_style_id": DEFAULT_CAPTION_STYLE_ID,
        }
    ]


def test_overlay_role_defaults_to_overlay_profile():
    resolver = TextStyleResolver(profiles=())

    profile = resolver.resolve_for_cue(cue=_cue(role="keyword"), track=_track())

    assert profile.id == DEFAULT_OVERLAY_STYLE_ID


def test_custom_profile_overrides_default_profile_of_same_id():
    resolver = TextStyleResolver(
        profiles=(
            TextStyleProfile(
                id=DEFAULT_CAPTION_STYLE_ID,
                name="Custom Caption",
                font_size=88,
                primary_color="#FFFF00",
            ),
        )
    )

    profile = resolver.resolve_for_cue(
        cue=_cue(role="caption"),
        track=_track(kind="subtitle"),
    )

    assert profile.id == DEFAULT_CAPTION_STYLE_ID
    assert profile.name == "Custom Caption"
    assert profile.font_size == 88
    assert profile.primary_color == "#FFFF00"


def test_strict_resolver_raises_when_requested_and_default_styles_are_unusable():
    resolver = TextStyleResolver(profiles=(), strict=True)
    resolver.profiles_by_id.clear()

    with pytest.raises(ValueError, match="No usable text style profile"):
        resolver.resolve_for_cue(cue=_cue(role="subtitle"), track=_track())
