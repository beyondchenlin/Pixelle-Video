from __future__ import annotations

import pytest

from pixelle_video.models.final_visual_prompt_contract_reader import (
    read_final_visual_prompt_contract,
)
from pixelle_video.models.final_visual_prompt_contract_v45 import (
    FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION,
    FinalVisualPromptContractV45,
)
from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION,
    FinalVisualPromptContractV46,
)
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler
from pixelle_video.services.mandatory_visual_anchor_prompt_repair import (
    MandatoryVisualAnchorPromptRepairService,
)
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
)


def _profile() -> VisualSignatureProfileSnapshot:
    return VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="斑点犬",
        core_identity_traits=("黑白斑点", "黑色圆框护目镜", "红色窄项圈"),
    )


def _v46_contract(frame_id: str = "frame-v46") -> FinalVisualPromptContractV46:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    projection = SeriesVisualSignatureProjectionService().project_frame(
        frame_id=frame_id,
        base_prompt="操作台上的输入模块经过过滤器后连接输出模块",
        frame_context={
            "frame_source_text": "输入模块经过过滤器形成输出模块。",
            "primary_subject": "输入模块",
            "secondary_subjects": ["过滤器", "输出模块"],
        },
        request=request,
        profile=_profile(),
    )
    return projection.contract


def _v45_contract() -> FinalVisualPromptContractV45:
    return FinalVisualPromptContractV45(
        contract_id="legacy:frame-1",
        frame_id="legacy-frame-1",
        primary_visual_task="legacy_display_only",
        required_subjects=(),
        series_visual_signature=SeriesVisualSignatureContract.disabled(),
    )


def test_v46_contract_round_trip_preserves_structured_contract_and_hashes() -> None:
    contract = _v46_contract()

    restored = FinalVisualPromptContractV46.from_mapping(contract.to_dict())

    assert restored.contract_version == FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION
    assert restored.contract_content_sha256 == contract.contract_content_sha256
    assert (
        restored.mandatory_anchor_contract.contract_content_sha256
        == contract.mandatory_anchor_contract.contract_content_sha256
    )
    assert restored.structured_required_subjects
    assert all(
        subject.evidence_span_ids for subject in restored.structured_required_subjects
    )
    assert restored.to_dict() == contract.to_dict()


def test_provider_prompt_leads_with_explicit_role_without_internal_anchor_jargon() -> None:
    bundle = FinalVisualPromptCompiler().compile(final_contract=_v46_contract())

    assert bundle.positive_prompt.startswith("画面必须清晰出现且仅出现一个斑点犬")
    assert bundle.positive_prompt.index("斑点犬") < bundle.positive_prompt.index(
        "文案主画面"
    )
    assert "锚点" not in bundle.positive_prompt


def test_v46_contract_rejects_empty_subjects_and_tampered_hash() -> None:
    contract = _v46_contract()
    empty_subjects = contract.to_dict()
    empty_subjects["mandatory_anchor_contract"]["required_subjects"] = []
    empty_subjects["mandatory_anchor_contract"]["contract_content_sha256"] = ""
    empty_subjects["contract_content_sha256"] = ""

    with pytest.raises(ValueError, match="structured required subjects"):
        FinalVisualPromptContractV46.from_mapping(empty_subjects)

    tampered = contract.to_dict()
    tampered["mandatory_anchor_contract"]["content_claim"] = "被篡改的主张"
    with pytest.raises(ValueError, match="contract_content_sha256"):
        FinalVisualPromptContractV46.from_mapping(tampered)


def test_contract_reader_keeps_v45_readable_but_requires_v46_to_resume() -> None:
    legacy = _v45_contract()
    current = _v46_contract()

    restored_legacy = read_final_visual_prompt_contract(legacy.to_dict())
    assert restored_legacy.contract_version == FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION
    with pytest.raises(ValueError, match="read-only"):
        read_final_visual_prompt_contract(
            legacy.to_dict(),
            resume_generation=True,
        )
    assert (
        read_final_visual_prompt_contract(
            current.to_dict(),
            resume_generation=True,
        ).contract_content_sha256
        == current.contract_content_sha256
    )


def test_prompt_repair_changes_only_scene_description_and_recompiles_contract() -> None:
    contract = _v46_contract("frame-repair")
    mandatory = contract.mandatory_anchor_contract

    repaired = MandatoryVisualAnchorPromptRepairService().repair(
        contract=contract,
        failure_codes=("required_subject_missing", "anchor_action_mismatch"),
        repair_pass=1,
        base_negative_prompt="低质量",
    )

    assert repaired.before_contract_sha256 == contract.contract_content_sha256
    assert repaired.after_contract_sha256 != contract.contract_content_sha256
    assert repaired.contract.mandatory_anchor_contract.required_subjects == (
        mandatory.required_subjects
    )
    assert (
        repaired.contract.mandatory_anchor_contract.participation_plan
        == mandatory.participation_plan
    )
    assert (
        repaired.contract.mandatory_anchor_contract.identity_contract
        == mandatory.identity_contract
    )
    assert (
        repaired.contract.mandatory_anchor_contract.placement
        == mandatory.placement
    )
    assert repaired.contract.mandatory_anchor_contract.final_scene_description != (
        mandatory.final_scene_description
    )
    assert "第一次修复" in repaired.bundle.positive_prompt
    assert "锚点" not in repaired.bundle.positive_prompt
    assert mandatory.participation_plan.action_verb in repaired.bundle.positive_prompt
    assert mandatory.participation_plan.interaction_target in repaired.bundle.positive_prompt
    assert len(repaired.bundle.positive_prompt) <= 800
    assert repaired.audit_dict()["changed_fields"] == [
        "mandatory_anchor_contract.final_scene_description"
    ]


def test_prompt_repair_rejects_unavailable_inspection_and_fourth_attempt() -> None:
    contract = _v46_contract("frame-no-repair")
    service = MandatoryVisualAnchorPromptRepairService()

    with pytest.raises(ValueError, match="cannot be repaired"):
        service.repair(
            contract=contract,
            failure_codes=("inspection_unavailable",),
            repair_pass=1,
            base_negative_prompt=None,
        )
    with pytest.raises(ValueError, match="must be 1 or 2"):
        service.repair(
            contract=contract,
            failure_codes=("required_subject_missing",),
            repair_pass=3,
            base_negative_prompt=None,
        )
