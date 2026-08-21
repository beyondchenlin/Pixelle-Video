from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION,
)
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRequest
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
)
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
)

_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "mandatory_content_bound_visual_anchor"
    / "acceptance_matrix.json"
)
_INTERNAL_ENUM_TOKENS = (
    "action_executor",
    "reader_proxy",
    "observation_gateway",
    "system_component",
    "conflict_participant",
    "scale_reference",
    "explanation_director",
    "transformation_medium",
    "cross_frame",
    "full_frame",
    "midground",
    "foreground",
    "background",
    "full_body",
    "half_body",
    "recognizable_detail",
)


def _request() -> SeriesVisualSignatureRequest:
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "anchor_dog_1",
            "series_visual_signature_role": "auto",
            "mandatory_content_bound_anchor": True,
            "series_visual_signature_contract_version": (
                FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION
            ),
        }
    )


def _profile(request: SeriesVisualSignatureRequest):
    return SeriesVisualSignatureProfileSnapshotBuilder().build(
        request=request,
        ip_profile=SimpleNamespace(
            series_visual_signature_profile_id="anchor_dog_1",
            name="斑点犬锚点",
            identity_lock=("黑白斑点", "黑色圆框护目镜", "红色窄项圈"),
            minimal_traits=(),
            identity_anchors=(),
            forbidden_elements=(),
            metadata={},
        ),
    )


def _load_cases() -> tuple[dict, list[dict]]:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    cases: list[dict] = []
    for category in fixture["categories"]:
        subjects = category["structured_subject_truth"]
        for frame_number, variant in enumerate(fixture["frame_variants"], start=1):
            target = subjects[variant["target_index"] % len(subjects)]
            cases.append(
                {
                    "category": category,
                    "variant": variant,
                    "frame_id": f"{category['id']}-{frame_number:02d}",
                    "target": target,
                    "frame_context": {
                        "frame_source_text": category["original_copy"],
                        "local_claim": category["original_copy"],
                        "primary_subject": subjects[0],
                        "secondary_subjects": subjects[1:],
                        "required_subjects": subjects,
                        "override_source": "fixed_acceptance_fixture",
                        "mandatory_anchor_area_ratio": variant["area_ratio"],
                        "mandatory_anchor_horizontal_position": variant["horizontal"],
                        "mandatory_anchor_depth_position": variant["depth"],
                        "mandatory_anchor_visible_extent": variant["extent"],
                        "mandatory_anchor_action_verb": variant["action"],
                        "mandatory_anchor_interaction_target": target,
                    },
                }
            )
    return fixture, cases


def test_fixed_acceptance_fixture_defines_nine_categories_and_seventy_two_frames() -> None:
    fixture, cases = _load_cases()

    assert fixture["schema_version"] == (
        "mandatory_content_bound_visual_anchor_acceptance.v1"
    )
    assert len(fixture["categories"]) == 9
    assert len(fixture["frame_variants"]) == 8
    assert len(cases) == 72
    assert Counter(case["category"]["id"] for case in cases) == {
        category["id"]: 8 for category in fixture["categories"]
    }
    assert {variant["horizontal"] for variant in fixture["frame_variants"]} == {
        "left",
        "center",
        "right",
        "cross_frame",
    }
    assert min(variant["area_ratio"] for variant in fixture["frame_variants"]) < 0.16
    assert max(variant["area_ratio"] for variant in fixture["frame_variants"]) == 1.0
    for category in fixture["categories"]:
        assert category["original_copy"]
        assert category["structured_subject_truth"]
        assert category["allowed_anchor_roles"]
        assert category["forbidden_replacements"]
        assert category["manual_checklist"]


def test_seventy_two_frame_contract_acceptance_is_complete_and_deterministic() -> None:
    _, cases = _load_cases()
    request = _request()
    profile = _profile(request)
    service = SeriesVisualSignatureProjectionService()
    call = {
        "base_prompts": [case["category"]["base_scene"] for case in cases],
        "frame_ids": [case["frame_id"] for case in cases],
        "frame_contexts": [case["frame_context"] for case in cases],
        "request": request,
        "profile": profile,
    }

    first = service.project_batch(**call)
    second = service.project_batch(**call)

    assert len(first.frames) == 72
    assert first.metrics.all_frames_passed is True
    assert [frame.contract.contract_content_sha256 for frame in first.frames] == [
        frame.contract.contract_content_sha256 for frame in second.frames
    ]
    assert first.prompts == second.prompts

    for case, projection in zip(cases, first.frames, strict=True):
        category = case["category"]
        variant = case["variant"]
        contract = projection.contract
        mandatory = contract.mandatory_anchor_contract
        plan = mandatory.participation_plan
        placement = mandatory.placement
        prompt = projection.bundle.positive_prompt
        budget = projection.bundle.metadata["prompt_budget"]

        assert contract.contract_version == FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION
        assert mandatory.frame_id == case["frame_id"]
        assert mandatory.required_subjects
        assert all(subject.evidence_span_ids for subject in mandatory.required_subjects)
        assert all(subject.loss_policy == "must_keep" for subject in mandatory.required_subjects)
        assert set(mandatory.required_subject_labels) == set(
            category["structured_subject_truth"]
        )
        assert projection.signature.role.value in category["allowed_anchor_roles"]
        assert plan.action_verb == variant["action"]
        assert plan.interaction_target == case["target"]
        assert plan.user_override_source == "fixed_acceptance_fixture"
        assert set(plan.user_override_fields) == {
            "mandatory_anchor_area_ratio",
            "mandatory_anchor_horizontal_position",
            "mandatory_anchor_depth_position",
            "mandatory_anchor_visible_extent",
            "mandatory_anchor_action_verb",
            "mandatory_anchor_interaction_target",
        }
        assert placement.area_ratio == pytest.approx(variant["area_ratio"])
        assert placement.horizontal_position.value == variant["horizontal"]
        assert placement.depth_position.value == variant["depth"]
        assert placement.visible_extent.value == variant["extent"]
        assert placement.relation_target == case["target"]
        assert len(prompt) <= 800
        assert budget["positive_prompt_limit"] == 800
        assert budget["main_content_ratio"] >= 0.35
        assert budget["identity_ratio"] <= 0.30
        assert budget["hard_truncated"] is False
        assert "…" not in prompt
        assert "..." not in prompt
        assert all(token not in prompt for token in _INTERNAL_ENUM_TOKENS)
        assert all(subject in prompt for subject in category["structured_subject_truth"])
        assert variant["action"] in prompt
        assert case["target"] in prompt

        if category["id"] == "serious_content":
            assert plan.serious_content_strategy.startswith(
                "neutral_explanation_space_only"
            )
