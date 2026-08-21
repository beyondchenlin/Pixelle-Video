from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from pixelle_video.models.final_visual_prompt_bundle import FinalVisualPromptBundle
from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FinalVisualPromptContractV46,
)
from pixelle_video.services.final_visual_prompt_compiler import FinalVisualPromptCompiler
from pixelle_video.services.series_visual_signature_rendering import (
    rendered_provider_participation_text,
)


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
        fragments = tuple(
            _repair_fragment(
                code,
                contract=contract,
                repair_pass=repair_pass,
            )
            for code in normalized_codes
        )
        scene = mandatory.final_scene_description.rstrip(" .。；;")
        additions = tuple(fragment for fragment in fragments if fragment not in scene)
        if additions:
            scene = "；".join((scene, *additions))
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


def _repair_fragment(
    failure_code: str,
    *,
    contract: FinalVisualPromptContractV46,
    repair_pass: int,
) -> str:
    mandatory = contract.mandatory_anchor_contract
    plan = mandatory.participation_plan
    subjects = "、".join(mandatory.required_subject_labels)
    fragments = {
        "review_confidence_below_threshold": "构图关系必须清楚、无遮挡、可直接核验",
        "identity_instance_count_not_one": "只画一个指定角色实体，画面、反射、海报和屏幕中都不出现副本",
        "identity_traits_not_visible": "完整露出身份核心特征且不遮挡内容主体",
        "identity_area_ratio_exceeded": f"指定角色严格保持约{mandatory.placement.area_ratio:.0%}的计划画面占比",
        "required_subject_missing": f"清晰完整呈现全部必要主体：{subjects}",
        "anchor_action_mismatch": (
            f"定格在指定角色{plan.action_verb}{plan.interaction_target}并产生"
            f"{rendered_provider_participation_text(plan.action_result)}的瞬间"
        ),
        "interaction_target_missing": f"完整露出动作目标{plan.interaction_target}",
        "content_claim_not_preserved": f"画面必须继续表达原文主张：{mandatory.content_claim}",
        "anchor_replaced_required_subject": f"指定角色不得冒充或替代必要主体：{subjects}",
        "support_invalid": f"指定角色通过{mandatory.placement.support_relation}获得明确支撑",
        "contact_invalid": f"指定角色与{plan.interaction_target}形成清楚可见的物理接触",
        "occlusion_invalid": "调整前后层级，身份特征和必要主体均不被遮挡",
        "lighting_invalid": "指定角色受光方向、色温和强度与场景主光一致",
        "perspective_invalid": "指定角色尺寸、落点和地平线严格服从场景透视",
        "anatomy_invalid": "指定角色肢体、关节和身体结构完整自然",
        "duplicate_body_detected": "删除多余身体、头部、肢体、倒影和相似副本",
        "sticker_edge_detected": "消除贴纸边缘，让指定角色共享场景材质、光影和接触阴影",
        "unrelated_text_detected": "删除无关文字、字母和伪文字纹理",
    }
    if failure_code not in fragments:
        raise ValueError(f"unsupported mandatory visual anchor failure code: {failure_code}")
    fragment = fragments[failure_code]
    if repair_pass == 2:
        return "第二次修复：" + fragment
    return "第一次修复：" + fragment


__all__ = [
    "MandatoryVisualAnchorPromptRepairService",
    "MandatoryVisualAnchorRepairResult",
]
