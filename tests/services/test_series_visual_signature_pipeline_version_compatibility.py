from __future__ import annotations

from dataclasses import replace

import pytest

from pixelle_video.models import series_visual_signature_request as compatibility
from pixelle_video.models.series_visual_signature import (
    SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
    SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
    SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS,
    SeriesVisualSignatureRequest,
    is_supported_series_visual_signature_pipeline_version,
)


def _request() -> SeriesVisualSignatureRequest:
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "asset",
            "series_visual_signature_profile_id": "sparrow",
        }
    )


def test_pipeline_version_is_real_canonical_dataclass_field() -> None:
    request = _request()
    legacy = replace(
        request,
        pipeline_version=SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
    )

    assert request.pipeline_version == SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION
    assert legacy.pipeline_version == SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION
    assert legacy.to_dict()["pipeline_version"] == SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION


def test_compatibility_module_reexports_canonical_pipeline_facts() -> None:
    assert (
        compatibility.SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION
        == SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION
    )
    assert (
        compatibility.SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION
        == SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION
    )
    assert (
        compatibility.SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS
        is SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS
    )
    assert (
        compatibility.is_supported_series_visual_signature_pipeline_version
        is is_supported_series_visual_signature_pipeline_version
    )


def test_request_mapping_can_restore_legacy_pipeline_version() -> None:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "asset",
            "series_visual_signature_profile_id": "sparrow",
            "pipeline_version": SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
        }
    )

    assert request.pipeline_version == SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION


def test_unknown_pipeline_version_is_rejected() -> None:
    assert is_supported_series_visual_signature_pipeline_version("unknown") is False
    with pytest.raises(ValueError, match="supported series visual signature pipeline version"):
        replace(_request(), pipeline_version="unknown")
