from __future__ import annotations

from types import SimpleNamespace

import pytest

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
)
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
)


def _request(**overrides) -> SeriesVisualSignatureRequest:
    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_profile_id": "dog_1",
        "series_visual_signature_role": "auto",
    }
    payload.update(overrides)
    return SeriesVisualSignatureRequest.from_mapping(payload)


def _ip_profile(**overrides):
    values = {
        "series_visual_signature_profile_id": "dog_1",
        "name": "Dalmatian",
        "identity_lock": (
            "black spots",
            "black sunglasses",
            "red collar",
            "small round ears",
        ),
        "minimal_traits": (),
        "identity_anchors": (),
        "forbidden_elements": (),
        "metadata": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_snapshot_builder_uses_explicit_asset_bible_identity_only() -> None:
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=_request(),
        ip_profile=_ip_profile(),
    )

    assert profile.profile_id == "dog_1"
    assert profile.display_name == "Dalmatian"
    assert profile.identity_traits == (
        "black spots",
        "black sunglasses",
        "red collar",
        "small round ears",
    )


def test_snapshot_builder_does_not_infer_identity_from_prose() -> None:
    profile = _ip_profile(
        identity_lock=(),
        minimal_traits=(),
        identity_anchors=(),
    )
    profile.visual_summary = "a very recognizable dog"

    with pytest.raises(ValueError, match="identity cannot be inferred from prose"):
        SeriesVisualSignatureProfileSnapshotBuilder().build(
            request=_request(),
            ip_profile=profile,
        )


def test_projection_requires_unique_frame_ids() -> None:
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=_request(),
        ip_profile=_ip_profile(),
    )

    with pytest.raises(ValueError, match="unique frame ids"):
        SeriesVisualSignatureProjectionService().project_batch(
            base_prompts=["worker at machine", "owner at desk"],
            frame_ids=["frame-1", "frame-1"],
            frame_contexts=[
                {"primary_subject": "worker"},
                {"primary_subject": "owner"},
            ],
            request=_request(),
            profile=profile,
        )


def test_projection_rejects_empty_subject_facts() -> None:
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=_request(),
        ip_profile=_ip_profile(),
    )

    with pytest.raises(ValueError, match="structured required subjects"):
        SeriesVisualSignatureProjectionService().project_batch(
            base_prompts=["abstract machinery"],
            frame_ids=["frame-1"],
            frame_contexts=[{}],
            request=_request(),
            profile=profile,
        )


def test_projection_preserves_base_prompt_and_all_identity_traits() -> None:
    request = _request(series_visual_signature_role="guide")
    profile = SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=_ip_profile(),
    )
    result = SeriesVisualSignatureProjectionService().project_batch(
        base_prompts=["worker operates assembly machine under warm industrial light"],
        frame_ids=["frame-1"],
        frame_contexts=[
            {
                "frame_source_text": "A worker operates a machine.",
                "primary_subject": "worker",
                "secondary_subjects": ["assembly machine"],
            }
        ],
        request=request,
        profile=profile,
        base_negative_prompts=["low quality"],
    )

    prompt = result.prompts[0]
    assert "worker operates assembly machine under warm industrial light" in prompt
    assert "worker" in prompt
    assert "assembly machine" in prompt
    for trait in profile.identity_traits:
        assert trait in prompt
    assert "low quality" in result.frames[0].bundle.negative_prompt
    assert result.frames[0].signature.max_area_ratio == pytest.approx(0.2)
    audit = result.audit_dict()
    assert audit["all_frames_passed"] is True
    assert "positive_prompt" not in audit["frames"][0]
    assert len(audit["frames"][0]["positive_prompt_sha256"]) == 64
