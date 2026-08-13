from __future__ import annotations

from urllib.parse import unquote
from xml.etree import ElementTree

import pytest

from web.components import layout_preview_media_source as media_source_module
from web.components.layout_preview_media_source import (
    LayoutPreviewMediaSource,
    build_layout_preview_placeholder_uri,
    resolve_layout_preview_media_source,
)


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (1280, 720),
        (720, 1280),
        (1024, 1024),
    ],
)
def test_missing_preview_media_uses_current_generation_dimensions(width, height):
    source = resolve_layout_preview_media_source(
        {},
        fallback_width=width,
        fallback_height=height,
    )

    assert source == LayoutPreviewMediaSource(
        uri=build_layout_preview_placeholder_uri(width=width, height=height),
        fallback_width=width,
        fallback_height=height,
        kind="placeholder",
    )
    decoded_svg = unquote(source.uri.split(",", 1)[1])
    assert f'width="{width}"' in decoded_svg
    assert f'height="{height}"' in decoded_svg
    assert f'viewBox="0 0 {width} {height}"' in decoded_svg


def test_placeholder_uri_is_cached_for_repeated_streamlit_reruns():
    first = build_layout_preview_placeholder_uri(width=1280, height=720)
    second = build_layout_preview_placeholder_uri(width=1280, height=720)

    assert first is second


def test_cached_placeholder_does_not_treat_boolean_as_integer_dimension():
    build_layout_preview_placeholder_uri(width=1, height=2)

    with pytest.raises(ValueError, match="positive integer"):
        build_layout_preview_placeholder_uri(width=True, height=2)


def test_placeholder_svg_remains_valid_for_small_positive_dimensions():
    uri = build_layout_preview_placeholder_uri(width=1, height=2)

    svg = unquote(uri.split(",", 1)[1])
    root = ElementTree.fromstring(svg)
    rectangles = root.findall("{http://www.w3.org/2000/svg}rect")

    assert rectangles
    assert all(float(rectangle.attrib["width"]) >= 0 for rectangle in rectangles)
    assert all(float(rectangle.attrib["height"]) >= 0 for rectangle in rectangles)


def test_placeholder_svg_bounds_extreme_dimensions_without_changing_fallback_contract():
    source = resolve_layout_preview_media_source(
        {},
        fallback_width=100_000,
        fallback_height=50_000,
    )

    svg = unquote(source.uri.split(",", 1)[1])
    assert 'width="4096"' in svg
    assert 'height="2048"' in svg
    assert 'viewBox="0 0 4096 2048"' in svg
    assert source.fallback_width == 100_000
    assert source.fallback_height == 50_000


def test_explicit_local_preview_media_preserves_real_asset_source(tmp_path):
    image_path = tmp_path / "square source.png"
    image_path.write_bytes(b"image")

    source = resolve_layout_preview_media_source(
        {"layout_preview_media_path": str(image_path)},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.uri == image_path.resolve().as_uri()
    assert source.fallback_width == 1280
    assert source.fallback_height == 720
    assert source.kind == "provided"


def test_structured_asset_candidate_resolves_supported_path_field(tmp_path):
    image_path = tmp_path / "generated.png"
    image_path.write_bytes(b"image")

    source = resolve_layout_preview_media_source(
        {"image_assets": [{"asset_path": str(image_path)}]},
        fallback_width=720,
        fallback_height=1280,
    )

    assert source.uri == image_path.resolve().as_uri()
    assert source.kind == "provided"


@pytest.mark.parametrize(
    "candidate",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://example.com/image.png",
    ],
)
def test_unsafe_preview_media_scheme_falls_back_to_generated_placeholder(candidate):
    source = resolve_layout_preview_media_source(
        {"layout_preview_media_path": candidate},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.kind == "placeholder"
    assert source.uri.startswith("data:image/svg+xml")


def test_file_uri_must_resolve_to_an_existing_regular_file(tmp_path):
    source = resolve_layout_preview_media_source(
        {"layout_preview_media_path": tmp_path.resolve().as_uri()},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.kind == "placeholder"


def test_existing_local_file_uri_remains_compatible(tmp_path):
    image_path = tmp_path / "preview.png"
    image_path.write_bytes(b"image")

    source = resolve_layout_preview_media_source(
        {"layout_preview_media_path": image_path.resolve().as_uri()},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.uri == image_path.resolve().as_uri()
    assert source.kind == "provided"


def test_relative_local_file_path_remains_compatible(tmp_path, monkeypatch):
    image_path = tmp_path / "preview.png"
    image_path.write_bytes(b"image")
    monkeypatch.chdir(tmp_path)

    source = resolve_layout_preview_media_source(
        {"layout_preview_media_path": "preview.png"},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.uri == image_path.resolve().as_uri()
    assert source.kind == "provided"


def test_remote_host_file_uri_is_rejected():
    source = resolve_layout_preview_media_source(
        {"layout_preview_media_path": "file://example.com/share/preview.png"},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.kind == "placeholder"


def test_valid_https_preview_media_remains_compatible():
    source = resolve_layout_preview_media_source(
        {"preview_media_ref": "https://example.com/generated.png"},
        fallback_width=1920,
        fallback_height=1080,
    )

    assert source.uri == "https://example.com/generated.png"
    assert source.kind == "provided"


def test_valid_raster_data_uri_remains_compatible():
    source = resolve_layout_preview_media_source(
        {"preview_media_ref": "data:image/png;base64,aW1hZ2U="},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.uri == "data:image/png;base64,aW1hZ2U="
    assert source.kind == "provided"


def test_valid_svg_data_uri_remains_compatible():
    uri = "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'/%3E"

    source = resolve_layout_preview_media_source(
        {"preview_media_ref": uri},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.uri == uri
    assert source.kind == "provided"


def test_oversized_data_uri_falls_back_without_embedding_unbounded_payload(monkeypatch):
    monkeypatch.setattr(media_source_module, "_MAX_DATA_IMAGE_URI_LENGTH", 32)

    source = resolve_layout_preview_media_source(
        {"preview_media_ref": f"data:image/png;base64,{'a' * 64}"},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.kind == "placeholder"


def test_oversized_remote_uri_falls_back_without_embedding_unbounded_url(monkeypatch):
    monkeypatch.setattr(media_source_module, "_MAX_REMOTE_MEDIA_URI_LENGTH", 32)

    source = resolve_layout_preview_media_source(
        {"preview_media_ref": f"https://example.com/{'a' * 64}.png"},
        fallback_width=1280,
        fallback_height=720,
    )

    assert source.kind == "placeholder"


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0, 720),
        (1280, 0),
        (-1, 720),
        (1280, -1),
        (True, 720),
        (1280.5, 720),
    ],
)
def test_preview_media_source_rejects_non_positive_fallback_dimensions(width, height):
    with pytest.raises(ValueError, match="positive"):
        resolve_layout_preview_media_source(
            {},
            fallback_width=width,
            fallback_height=height,
        )


def test_preview_media_source_normalizes_manual_uri_values():
    source = LayoutPreviewMediaSource(
        uri="  https://example.com/preview.png  ",
        fallback_width=1280,
        fallback_height=720,
        kind="provided",
    )

    assert source.uri == "https://example.com/preview.png"
