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


def _conflict_v46_contract() -> FinalVisualPromptContractV46:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    projection = SeriesVisualSignatureProjectionService().project_frame(
        frame_id="frame-conflict",
        base_prompt="思维导图对比复杂问题与简单解决方案",
        frame_context={
            "frame_source_text": "在复杂问题中权衡并找到简单解决方案。",
            "primary_subject": "思维导图",
            "secondary_subjects": ["复杂问题与简单解决方案的对比"],
        },
        request=request,
        profile=_profile(),
    )
    return projection.contract


def _timeline_v46_contract() -> FinalVisualPromptContractV46:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    projection = SeriesVisualSignatureProjectionService().project_frame(
        frame_id="frame-timeline",
        base_prompt=(
            "不同年代的苹果产品以时间轴排列，从Mac到iPhone；"
            "时间轴下方展示乔布斯职业生涯的不同阶段"
        ),
        frame_context={
            "frame_source_text": (
                "苹果产品影响生活，乔布斯也经历过失败和低谷。"
            ),
            "required_subjects": [
                "不同年代的苹果产品, 乔布斯职业生涯的不同阶段插图"
            ],
        },
        request=request,
        profile=_profile(),
    )
    return projection.contract


def _group_v46_contract() -> FinalVisualPromptContractV46:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    projection = SeriesVisualSignatureProjectionService().project_frame(
        frame_id="frame-group",
        base_prompt=(
            "设计团队围绕讨论桌，展示他们反复修改设计方案并最终定稿的过程"
        ),
        frame_context={
            "frame_source_text": "每个按钮和颜色都经过团队无数次推敲。",
            "required_subjects": [
                "设计团队, 讨论, 修改设计方案, 最终定稿"
            ],
        },
        request=request,
        profile=_profile(),
    )
    return projection.contract


def _protagonist_v46_contract() -> FinalVisualPromptContractV46:
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    projection = SeriesVisualSignatureProjectionService().project_frame(
        frame_id="frame-protagonist",
        base_prompt=(
            "乔布斯站在破晓时分，背后是即将升起的太阳，"
            "象征着他在逆境中的态度转变"
        ),
        frame_context={
            "frame_source_text": (
                "但他没有放弃，反而从中学到了很多。"
                "他说，有时候生活给你当头一棒，但这正是你重新开始的机会。"
            ),
            "required_subjects": ["乔布斯, 破晓, 转折点"],
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
    assert "%" not in bundle.positive_prompt


def test_initial_prompt_prevents_extra_identity_instances_before_generation() -> None:
    bundle = FinalVisualPromptCompiler().compile(final_contract=_v46_contract())

    assert bundle.positive_prompt.count("斑点犬") == 1
    assert "其他人物、动物、道具、模型和背景不采用其外观" in (
        bundle.positive_prompt
    )
    assert "全画面仅一个指定角色实体" in bundle.positive_prompt
    assert "第一次修复" not in bundle.positive_prompt
    assert "duplicate recurring visual signature" in bundle.negative_prompt
    assert "multiple or extra 斑点犬 instances" in bundle.negative_prompt
    assert (
        "cloned repeated reflected mirrored or background copies of 斑点犬"
        in bundle.negative_prompt
    )
    assert (
        "other people animals props models or background figures using the "
        "recurring identity appearance or traits"
        in bundle.negative_prompt
    )


def test_conflict_prompt_uses_one_actor_to_point_at_comparison_boundary() -> None:
    contract = _conflict_v46_contract()
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)

    assert (
        contract.mandatory_anchor_contract.participation_plan.participation_mechanism.value
        == "conflict_participant"
    )
    assert "用一只前爪指向对比图中央的分界线并权衡" in bundle.positive_prompt
    assert "拉住并权衡" not in bundle.positive_prompt
    assert contract.mandatory_anchor_contract.placement.horizontal_position.value == "left"
    assert contract.mandatory_anchor_contract.placement.area_ratio == pytest.approx(0.24)

    repaired = MandatoryVisualAnchorPromptRepairService().repair(
        contract=contract,
        failure_codes=("identity_instance_count_not_one",),
        repair_pass=1,
        base_negative_prompt=None,
    )
    assert "用一只前爪指向中央分界线" in repaired.bundle.positive_prompt
    assert "所有动作由这一个身体完成" in repaired.bundle.positive_prompt


def test_timeline_prompt_uses_one_actor_at_one_shared_control_position() -> None:
    contract = _timeline_v46_contract()
    mandatory = contract.mandatory_anchor_contract
    plan = mandatory.participation_plan
    placement = mandatory.placement
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)

    assert plan.participation_mechanism.value == "reader_proxy"
    assert plan.action_verb == (
        "在整条时间线左下方的单一位置，"
        "用一只前爪指向贯穿全部阶段的同一条总线"
    )
    assert plan.scene_binding == (
        "角色固定在整条时间线左下方的一个位置，只指向同一条总线，"
        "不在各年代或阶段重复出现"
    )
    assert "承受并整理" not in bundle.positive_prompt
    assert "不在各年代或阶段重复出现" in bundle.positive_prompt
    assert placement.horizontal_position.value == "left"
    assert placement.depth_position.value == "midground"
    assert placement.visible_extent.value == "full_body"
    assert placement.area_ratio == pytest.approx(0.24)
    assert "在画面中保持中等体量" in bundle.positive_prompt
    assert "%" not in bundle.positive_prompt
    assert len(bundle.positive_prompt) <= 800

    repaired = MandatoryVisualAnchorPromptRepairService().repair(
        contract=contract,
        failure_codes=("identity_instance_count_not_one",),
        repair_pass=1,
        base_negative_prompt=None,
    )
    assert "固定在整条时间线左下方" in repaired.bundle.positive_prompt
    assert "只指向同一条总线" in repaired.bundle.positive_prompt
    assert "不在各阶段重复" in repaired.bundle.positive_prompt
    assert len(repaired.bundle.positive_prompt) <= 800


def test_group_prompt_keeps_one_facilitator_distinct_from_human_team() -> None:
    contract = _group_v46_contract()
    mandatory = contract.mandatory_anchor_contract
    plan = mandatory.participation_plan
    placement = mandatory.placement
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)

    assert plan.action_verb == (
        "固定站在讨论桌旁的地面上，"
        "用一只前爪指向桌面中央同一份定稿方案"
    )
    assert plan.scene_binding == (
        "一个指定角色固定站在讨论桌旁的地面上，只在一个位置主持；"
        "设计团队成员保持为人类，不采用指定角色外观"
    )
    assert placement.horizontal_position.value == "left"
    assert placement.depth_position.value == "midground"
    assert placement.visible_extent.value == "full_body"
    assert placement.area_ratio == pytest.approx(0.24)
    assert placement.support_relation == "feet on existing 地面"
    assert "设计团队成员保持为人类" in bundle.positive_prompt
    assert "feet on existing 桌" not in bundle.positive_prompt
    assert "%" not in bundle.positive_prompt
    assert len(bundle.positive_prompt) <= 800

    repaired = MandatoryVisualAnchorPromptRepairService().repair(
        contract=contract,
        failure_codes=("identity_instance_count_not_one",),
        repair_pass=1,
        base_negative_prompt=None,
    )
    assert "固定站在讨论桌旁" in repaired.bundle.positive_prompt
    assert "其余团队成员保持为人类" in repaired.bundle.positive_prompt
    assert "不采用角色外观" in repaired.bundle.positive_prompt
    assert len(repaired.bundle.positive_prompt) <= 800


def test_named_protagonist_stays_primary_while_one_witness_points_to_turning_point() -> None:
    contract = _protagonist_v46_contract()
    mandatory = contract.mandatory_anchor_contract
    plan = mandatory.participation_plan
    placement = mandatory.placement
    bundle = FinalVisualPromptCompiler().compile(final_contract=contract)

    assert plan.participation_mechanism.value == "observation_gateway"
    assert contract.series_visual_signature.role.value == "guide"
    assert plan.action_verb == (
        "固定站在乔布斯侧后方的地面上，"
        "用一只前爪指向乔布斯身后的同一处破晓日出"
    )
    assert plan.scene_binding == (
        "乔布斯保持为画面中央唯一人类主角；"
        "一个指定角色固定站在侧后方地面，只在一个位置提供指引，"
        "不替代或复制乔布斯"
    )
    assert placement.horizontal_position.value == "right"
    assert placement.depth_position.value == "midground"
    assert placement.visible_extent.value == "full_body"
    assert placement.relative_size.value == "medium_small"
    assert placement.area_ratio == pytest.approx(0.18)
    assert placement.support_relation == "feet on existing 地面"
    assert "乔布斯保持为画面中央唯一人类主角" in bundle.positive_prompt
    assert "不绘制句子、引语、标题或说明文字" in bundle.positive_prompt
    assert "他说" not in bundle.positive_prompt
    assert "覆盖画面主体区域" not in bundle.positive_prompt
    assert "%" not in bundle.positive_prompt
    assert len(bundle.positive_prompt) <= 800

    repaired = MandatoryVisualAnchorPromptRepairService().repair(
        contract=contract,
        failure_codes=(
            "identity_instance_count_not_one",
            "required_subject_missing",
            "anchor_action_mismatch",
            "anchor_replaced_required_subject",
            "unrelated_text_detected",
        ),
        repair_pass=1,
        base_negative_prompt=None,
    )
    assert "乔布斯保持为画面中央清晰可见的唯一人类主角" in (
        repaired.bundle.positive_prompt
    )
    assert "不出现第二个指定角色" in repaired.bundle.positive_prompt
    assert "删除全部句子、引语、标题" in repaired.bundle.positive_prompt
    assert len(repaired.bundle.positive_prompt) <= 800


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


def test_prompt_repair_compacts_many_failures_and_replaces_previous_pass() -> None:
    contract = _v46_contract("frame-many-repairs")
    failure_codes = (
        "review_confidence_below_threshold",
        "identity_instance_count_not_one",
        "required_subject_missing",
        "anchor_action_mismatch",
        "interaction_target_missing",
        "content_claim_not_preserved",
        "support_invalid",
        "contact_invalid",
        "anchor_replaced_required_subject",
    )
    service = MandatoryVisualAnchorPromptRepairService()

    first = service.repair(
        contract=contract,
        failure_codes=failure_codes,
        repair_pass=1,
        base_negative_prompt=None,
    )
    second = service.repair(
        contract=first.contract,
        failure_codes=failure_codes,
        repair_pass=2,
        base_negative_prompt=None,
    )

    assert first.failure_codes == failure_codes
    assert len(first.repair_fragments) == 1
    assert len(first.bundle.positive_prompt) <= 800
    assert "第一次修复" in first.bundle.positive_prompt
    assert len(second.bundle.positive_prompt) <= 800
    assert "第一次修复" not in second.bundle.positive_prompt
    assert second.bundle.positive_prompt.count("第二次修复") == 1
    assert "必要主体与身份特征清晰无遮挡" in second.bundle.positive_prompt
    assert "只画一个指定角色实体" in second.bundle.positive_prompt
    assert "接触上述动作目标并完成约定动作" in second.bundle.positive_prompt


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
