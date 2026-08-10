from __future__ import annotations

from dataclasses import replace

import pytest

from pixelle_video.models.series_visual_signature import (
    SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
    SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
    SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS,
    SeriesVisualSignatureRequest,
    is_supported_series_visual_signature_pipeline_version,
)
from pixelle_video.models.series_visual_signature_request import (
    SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION as COMPAT_LEGACY_VERSION,
    SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION as COMPAT_CURRENT_VERSION,
    SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS as COMPAT_SUPPORTED_VERSIONS,
    is_supported_series_visual_signature_pipeline_version as compat_is_supported,
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
    assert COMPAT_LEGACY_VERSION == SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION
    assert COMPAT_CURRENT_VERSION == SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION
    assert COMPAT_SUPPORTED_VERSIONS is SUPPORTED_SERIES_VISUAL_SIGNATURE_PIPELINE_VERSIONS
    assert compat_is_supported is is_supported_series_visual_signature_pipeline_version


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
