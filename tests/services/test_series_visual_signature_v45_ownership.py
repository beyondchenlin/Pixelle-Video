from __future__ import annotations

from types import SimpleNamespace

import pytest

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.services import visual_prompt_planning_service as planning_module
from pixelle_video.services.visual_prompt_planning_service import (
    VisualPromptPlanningService,
    _legacy_anchor_inputs,
)


def _enabled_request() -> SeriesVisualSignatureRequest:
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
        }
    )


def test_v45_request_disables_all_legacy_anchor_inputs() -> None:
    anchor_profile = object()
    base_package = object()

    enabled, profile, packages, disabled_by_v45 = _legacy_anchor_inputs(
        visual_anchor_enabled=True,
        anchor_profile=anchor_profile,  # type: ignore[arg-type]
        base_anchor_packages=(base_package,),  # type: ignore[arg-type]
        series_visual_signature_request=_enabled_request(),
    )

    assert enabled is False
    assert profile is None
    assert packages == ()
    assert disabled_by_v45 is True


def test_legacy_request_keeps_legacy_anchor_inputs() -> None:
    anchor_profile = object()
    base_package = object()

    enabled, profile, packages, disabled_by_v45 = _legacy_anchor_inputs(
        visual_anchor_enabled=True,
        anchor_profile=anchor_profile,  # type: ignore[arg-type]
        base_anchor_packages=(base_package,),  # type: ignore[arg-type]
        series_visual_signature_request=None,
    )

    assert enabled is True
    assert profile is anchor_profile
    assert packages == (base_package,)
    assert disabled_by_v45 is False


def test_disabled_canonical_request_does_not_steal_legacy_ownership() -> None:
    disabled_request = SeriesVisualSignatureRequest.disabled()
    anchor_profile = object()

    enabled, profile, packages, disabled_by_v45 = _legacy_anchor_inputs(
        visual_anchor_enabled=True,
        anchor_profile=anchor_profile,  # type: ignore[arg-type]
        base_anchor_packages=(),
        series_visual_signature_request=disabled_request,
    )

    assert enabled is True
    assert profile is anchor_profile
    assert packages == ()
    assert disabled_by_v45 is False


@pytest.mark.asyncio
async def test_v45_planning_flow_never_invokes_legacy_anchor_planners(
    monkeypatch,
) -> None:
    brief = BaseVisualBrief(
        frame_id="frame-1",
        core_message="worker operates machine",
        visual_moment="worker beside assembly machine",
        main_subjects=("worker", "assembly machine"),
        base_image_prompt="worker beside assembly machine",
    )

    class _FakeBriefPlanner:
        def plan_batch(self, **kwargs):
            return (brief,)

    def _legacy_planner_must_not_run(*args, **kwargs):
        raise AssertionError("V4.5 must not construct a legacy visual-anchor planner")

    projector_calls: list[dict[str, object]] = []

    class _IdentityNeutralProjector:
        def project(self, **kwargs):
            projector_calls.append(kwargs)
            return SimpleNamespace(metadata_to_dict=lambda: {})

    monkeypatch.setattr(planning_module, "BaseVisualBriefPlanner", _FakeBriefPlanner)
    monkeypatch.setattr(
        planning_module,
        "VisualSignatureFallbackPlanner",
        _legacy_planner_must_not_run,
    )
    monkeypatch.setattr(
        planning_module,
        "VisualAnchorIntegrationPlanner",
        _legacy_planner_must_not_run,
    )
    monkeypatch.setattr(
        planning_module,
        "ProviderPromptProjector",
        _IdentityNeutralProjector,
    )

    result = await VisualPromptPlanningService().plan_image_prompts(
        base_prompts=("worker beside assembly machine",),
        frame_contexts=({},),
        visual_anchor_enabled=True,
        anchor_profile=object(),  # type: ignore[arg-type]
        base_anchor_packages=(object(),),  # type: ignore[arg-type]
        series_visual_signature_request=_enabled_request(),
    )

    assert result.visual_anchor_plans == ()
    assert result.anchor_packages == ()
    assert result.legacy_visual_anchor_disabled is True
    assert len(projector_calls) == 1
    assert projector_calls[0]["anchor_profile"] is None
    assert projector_calls[0]["visual_anchor_plan"] is None
