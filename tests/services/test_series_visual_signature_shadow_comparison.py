from __future__ import annotations

from types import SimpleNamespace

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.services.series_visual_signature_shadow_comparison import (
    build_series_visual_signature_shadow_report,
)


def _value(value: str):
    return SimpleNamespace(value=value)


def _plan(frame_id: str = "frame-1", *, required_subjects=("worker", "machine")):
    anchor = SimpleNamespace(
        required_subjects=tuple(required_subjects),
        to_dict=lambda: {
            "anchor_kind": "causal_mechanism",
            "anchor_claim": "a production bottleneck",
            "required_subjects": list(required_subjects),
        },
    )
    visible_text = SimpleNamespace(effective_policy=_value("no_visible_text"))
    diagram = SimpleNamespace(
        grammar=_value("process_flow"),
        primary_visual_task=_value("process_walkthrough"),
        visual_metaphor="worker operates machine through a bottleneck",
        visible_text=visible_text,
        to_dict=lambda: {
            "grammar": "process_flow",
            "primary_visual_task": "process_walkthrough",
            "visual_metaphor": "worker operates machine through a bottleneck",
        },
    )
    resolution = SimpleNamespace(
        effective_anchor_kind=_value("causal_mechanism"),
        effective_diagram_grammar=_value("process_flow"),
    )
    render = SimpleNamespace(
        to_dict=lambda: {"render_style": "clean_vector"},
    )
    return SimpleNamespace(
        plan_id=f"plan-{frame_id}",
        frame_id=frame_id,
        anchor=anchor,
        diagram=diagram,
        resolution=resolution,
        render=render,
    )


def _profile(profile_id: str = "dog_1"):
    identity_contract = SimpleNamespace(
        required_identity_traits=("black spots", "black sunglasses"),
    )
    return SimpleNamespace(
        profile_id=profile_id,
        display_name="Dalmatian",
        identity_contract=identity_contract,
        identity_kernel=("black spots", "black sunglasses"),
        appearance_traits=(),
        forbidden_role_forms=(),
        reference_assets=(),
    )


def _request(profile_id: str = "dog_1") -> SeriesVisualSignatureRequest:
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": profile_id,
            "series_visual_signature_role": "auto",
        }
    )


def test_shadow_candidate_passes_without_mutating_production_prompt() -> None:
    production_prompt = "legacy production prompt without canonical identity wording"
    report = build_series_visual_signature_shadow_report(
        production_prompts=[production_prompt],
        frame_ids=["frame-1"],
        article_concretization_plans=[_plan()],
        request=_request(),
        legacy_profile=_profile(),
    )

    assert report.ready_for_cutover is True
    assert report.coverage_rate == 1.0
    assert report.candidate_pass_rate == 1.0
    assert report.frame_results[0].production_prompt == production_prompt
    assert report.frame_results[0].candidate_prompt != production_prompt
    assert report.frame_results[0].candidate_source_kind == "article_concretization_plan"
    assert "worker" in report.frame_results[0].candidate_prompt
    assert "machine" in report.frame_results[0].candidate_prompt
    assert "Dalmatian" in report.frame_results[0].candidate_prompt
    assert "black spots" in report.frame_results[0].candidate_prompt
    assert report.frame_results[0].production_identity_terms_present["Dalmatian"] is False
    assert report.frame_results[0].final_gate_passed is True
    assert report.frame_results[0].provider_projection_passed is True


def test_shadow_non_article_frame_uses_storyboard_context() -> None:
    production_prompt = "worker demonstrates the assembly machine on a factory floor"
    report = build_series_visual_signature_shadow_report(
        production_prompts=[production_prompt],
        frame_ids=["frame-1"],
        article_concretization_plans=[],
        request=_request(),
        legacy_profile=_profile(),
        fallback_frame_contexts={
            "frame-1": {
                "frame_id": "frame-1",
                "frame_source_text": "A worker demonstrates a machine.",
                "visual_goal": "show the factory process",
                "primary_subject": "worker",
                "secondary_subjects": ["assembly machine"],
            }
        },
    )

    result = report.frame_results[0]
    assert report.ready_for_cutover is True
    assert result.candidate_source_kind == "storyboard_frame_context"
    assert result.production_prompt == production_prompt
    assert production_prompt in result.candidate_prompt
    assert "worker" in result.candidate_prompt
    assert "assembly machine" in result.candidate_prompt
    assert "Dalmatian" in result.candidate_prompt


def test_shadow_requires_full_same_frame_coverage_before_cutover() -> None:
    report = build_series_visual_signature_shadow_report(
        production_prompts=["old one", "old two"],
        frame_ids=["frame-1", "frame-2"],
        article_concretization_plans=[_plan("frame-1")],
        request=_request(),
        legacy_profile=_profile(),
    )

    assert report.ready_for_cutover is False
    assert report.coverage_rate == 0.5
    assert report.failed_frame_count == 1
    assert report.frame_results[1].status == "blocked"
    assert "same-frame" in report.frame_results[1].candidate_error


def test_shadow_profile_failure_is_observed_not_raised() -> None:
    report = build_series_visual_signature_shadow_report(
        production_prompts=["old prompt"],
        frame_ids=["frame-1"],
        article_concretization_plans=[_plan()],
        request=_request("dog_1"),
        legacy_profile=_profile("dog_2"),
    )

    assert report.ready_for_cutover is False
    assert report.global_errors
    assert report.frame_results[0].status == "blocked"
    assert "does not match request profile_id" in report.frame_results[0].candidate_error


def test_shadow_candidate_failure_is_recorded_without_falling_back() -> None:
    over_budget_subjects = tuple(
        f"required subject {index} " + ("x" * 70)
        for index in range(20)
    )
    report = build_series_visual_signature_shadow_report(
        production_prompts=["old prompt remains usable"],
        frame_ids=["frame-1"],
        article_concretization_plans=[_plan(required_subjects=over_budget_subjects)],
        request=_request(),
        legacy_profile=_profile(),
    )

    result = report.frame_results[0]
    assert report.ready_for_cutover is False
    assert result.status == "failed"
    assert result.candidate_error is not None
    assert "protected visual prompt semantics exceed" in result.candidate_error
    assert result.production_prompt == "old prompt remains usable"


def test_shadow_report_reserves_render_comparison_without_double_generation() -> None:
    report = build_series_visual_signature_shadow_report(
        production_prompts=["old prompt"],
        frame_ids=["frame-1"],
        article_concretization_plans=[_plan()],
        request=_request(),
        legacy_profile=_profile(),
    )

    payload = report.to_dict()
    assert payload["comparison_level"] == "prompt_contract_shadow"
    assert payload["candidate_media_generation"] == "disabled"
    assert payload["frames"][0]["production_render_result"] is None
    assert payload["frames"][0]["candidate_render_result"] is None
