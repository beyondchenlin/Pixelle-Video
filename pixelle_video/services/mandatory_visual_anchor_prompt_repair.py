from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from pixelle_video.models.content_bound_ip import IPParticipationMechanism
from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FinalVisualPromptContractV46,
)
from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler
from pixelle_video.services.structured_group_composition import (
    is_structured_group_scene,
)
from pixelle_video.services.structured_timeline_composition import (
    is_structured_timeline_scene,
)

_REPAIR_MARKERS = ("；第一次修复：", "；第二次修复：")


@dataclass(frozen=True)
class MandatoryVisualAnchorRepairResult:
    contract: FinalVisualPromptContractV46
    bundle: FinalVisualPromptBundle
    repair_pass: int
    failure_codes: tuple[str, ...]
    repair_fragments: tuple[str, ...]
    before_contract_sha256: str
    after_contract_sha256: str

    def audit_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "mandatory_visual_anchor_prompt_repair.v1",
            "repair_pass": self.repair_pass,
            "failure_codes": list(self.failure_codes),
            "repair_fragments": list(self.repair_fragments),
            "changed_fields": ["mandatory_anchor_contract.final_scene_description"],
            "before_contract_sha256": self.before_contract_sha256,
            "after_contract_sha256": self.after_contract_sha256,
            "positive_prompt_chars": len(self.bundle.positive_prompt),
            "negative_prompt_chars": len(self.bundle.negative_prompt),
        }


class MandatoryVisualAnchorPromptRepairService:
    def repair(
        self,
        *,
        contract: FinalVisualPromptContractV46,
        failure_codes: Sequence[str],
        repair_pass: int,
        base_negative_prompt: str | None,
    ) -> MandatoryVisualAnchorRepairResult:
        contract = FinalVisualPromptContractV46.from_mapping(contract)
        if repair_pass not in {1, 2}:
            raise ValueError("mandatory visual anchor repair_pass must be 1 or 2")
        normalized_codes = tuple(
            dict.fromkeys(str(value or "").strip() for value in failure_codes)
        )
        if not normalized_codes or any(not value for value in normalized_codes):
            raise ValueError("mandatory visual anchor repair requires failure codes")
        if "inspection_unavailable" in normalized_codes:
            raise ValueError(
                "inspection unavailability cannot be repaired by rewriting the prompt"
            )
        mandatory = contract.mandatory_anchor_contract
        repair_clause = _repair_clause(
            normalized_codes,
            contract=contract,
            repair_pass=repair_pass,
        )
        fragments = (repair_clause,)
        scene = _scene_without_previous_repair(
            mandatory.final_scene_description
        ).rstrip(" .。；;")
        scene = "；".join((scene, repair_clause))
        repaired_mandatory = replace(
            mandatory,
            final_scene_description=scene,
            contract_content_sha256="",
        )
        repaired_contract = replace(
            contract,
            mandatory_anchor_contract=repaired_mandatory,
            contract_content_sha256="",
        )
        bundle = FinalVisualPromptCompiler().compile(
            final_contract=repaired_contract,
            base_negative_prompt=base_negative_prompt,
        )
        return MandatoryVisualAnchorRepairResult(
            contract=repaired_contract,
            bundle=bundle,
            repair_pass=repair_pass,
            failure_codes=normalized_codes,
            repair_fragments=fragments,
            before_contract_sha256=contract.contract_content_sha256,
            after_contract_sha256=repaired_contract.contract_content_sha256,
        )


def _repair_clause(
    failure_codes: Sequence[str],
    *,
    contract: FinalVisualPromptContractV46,
    repair_pass: int,
) -> str:
    mandatory = contract.mandatory_anchor_contract
    plan = mandatory.participation_plan
    code_set = set(failure_codes)
    supported_codes = {
        "review_confidence_below_threshold",
        "identity_instance_count_not_one",
        "identity_traits_not_visible",
        "identity_area_ratio_exceeded",
        "required_subject_missing",
        "anchor_action_mismatch",
        "interaction_target_missing",
        "content_claim_not_preserved",
        "anchor_replaced_required_subject",
        "support_invalid",
        "contact_invalid",
        "occlusion_invalid",
        "lighting_invalid",
        "perspective_invalid",
        "anatomy_invalid",
        "duplicate_body_detected",
        "sticker_edge_detected",
        "unrelated_text_detected",
    }
    unsupported_codes = code_set - supported_codes
    if unsupported_codes:
        unsupported = sorted(unsupported_codes)[0]
        raise ValueError(
            f"unsupported mandatory visual anchor failure code: {unsupported}"
        )

    fragments: list[str] = []
    if code_set & {
        "review_confidence_below_threshold",
        "identity_traits_not_visible",
        "required_subject_missing",
        "content_claim_not_preserved",
        "anchor_replaced_required_subject",
        "occlusion_invalid",
    }:
        clarity = "必要主体与身份特征清晰无遮挡，原文主张不变"
        if "anchor_replaced_required_subject" in code_set:
            clarity += "，指定角色不替代主体"
        fragments.append(clarity)

    if code_set & {
        "identity_instance_count_not_one",
        "identity_area_ratio_exceeded",
        "duplicate_body_detected",
    }:
        if is_structured_group_scene(
            plan.interaction_target,
            plan.physical_metaphor,
        ):
            fragments.append(
                "只画一个指定角色实体，固定站在讨论桌旁；"
                "其余团队成员保持为人类且不采用角色外观"
            )
        elif is_structured_timeline_scene(
            plan.interaction_target,
            plan.physical_metaphor,
        ):
            fragments.append(
                "只画一个指定角色实体，固定在整条时间线左下方，只指向同一条总线，"
                "不在各阶段重复"
            )
        elif plan.participation_mechanism is IPParticipationMechanism.CONFLICT_PARTICIPANT:
            fragments.append(
                "只画一个指定角色实体，位于对比图一侧，用一只前爪指向中央分界线，"
                "所有动作由这一个身体完成"
            )
        else:
            fragments.append("只画一个指定角色实体，无副本或倒影，并保持计划画面占比")

    if code_set & {
        "anchor_action_mismatch",
        "interaction_target_missing",
        "support_invalid",
        "contact_invalid",
        "anatomy_invalid",
    }:
        fragments.append("指定角色接触上述动作目标并完成约定动作，支撑与肢体自然")

    if code_set & {
        "lighting_invalid",
        "perspective_invalid",
        "sticker_edge_detected",
    }:
        fragments.append("角色透视、光照与材质服从场景，无贴纸边缘")

    if "unrelated_text_detected" in code_set:
        fragments.append("删除无关文字、字母和伪文字纹理")

    prefix = "第二次修复" if repair_pass == 2 else "第一次修复"
    return f"{prefix}：{'；'.join(fragments)}"


def _scene_without_previous_repair(scene: str) -> str:
    repair_starts = tuple(
        position
        for marker in _REPAIR_MARKERS
        if (position := scene.find(marker)) >= 0
    )
    if repair_starts:
        return scene[: min(repair_starts)]
    return scene


__all__ = [
    "MandatoryVisualAnchorPromptRepairService",
    "MandatoryVisualAnchorRepairResult",
]
