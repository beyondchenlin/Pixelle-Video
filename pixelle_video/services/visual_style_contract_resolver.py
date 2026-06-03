from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from pixelle_video.models.visual_style_contract import (
    VisualStyleLayerContract,
    default_mixed_style_world_contract,
    visual_style_contract_from_style_profile,
)


@dataclass(frozen=True)
class VisualStyleContractResolver:
    def resolve(
        self,
        *,
        resolved_style: Any = None,
        active_style_item: Mapping[str, Any] | None = None,
        fallback_to_default_world: bool = True,
    ) -> VisualStyleLayerContract:
        contracts: list[VisualStyleLayerContract] = []
        item_contract = _contract_from_active_item(active_style_item)
        if item_contract is not None:
            contracts.append(item_contract)
        style_contract = getattr(resolved_style, "visual_style_contract", None)
        if isinstance(style_contract, VisualStyleLayerContract) and _has_contract_content(style_contract):
            contracts.append(style_contract)
        elif isinstance(style_contract, Mapping):
            mapped_contract = VisualStyleLayerContract.from_dict(style_contract)
            if _has_contract_content(mapped_contract):
                contracts.append(mapped_contract)
            elif resolved_style is not None:
                contracts.append(_contract_from_resolved_style(resolved_style))
        elif resolved_style is not None:
            contracts.append(_contract_from_resolved_style(resolved_style))
        if not contracts and fallback_to_default_world:
            return default_mixed_style_world_contract()
        if not contracts:
            return VisualStyleLayerContract()
        merged = contracts[0]
        for contract in contracts[1:]:
            merged = merged.merge(contract)
        return merged


def _contract_from_active_item(active_style_item: Mapping[str, Any] | None) -> VisualStyleLayerContract | None:
    if not isinstance(active_style_item, Mapping):
        return None
    raw_contract = active_style_item.get("visual_style_contract")
    if isinstance(raw_contract, Mapping):
        return VisualStyleLayerContract.from_dict(raw_contract)
    if active_style_item.get("style_contract_kind") == "visual_style_contract":
        layers = active_style_item.get("visual_style_layers")
        if layers:
            return VisualStyleLayerContract.from_dict(
                {
                    "layers": layers,
                    "integration_rules": active_style_item.get("integration_rules") or (),
                    "negative_rules": active_style_item.get("negative_rules") or (),
                }
            )
    return None


def _has_contract_content(contract: VisualStyleLayerContract) -> bool:
    return bool(contract.layers or contract.integration_rules or contract.negative_rules)


def _contract_from_resolved_style(resolved_style: Any) -> VisualStyleLayerContract:
    profile = dict(getattr(resolved_style, "style_profile", {}) or {})
    template_clause = _style_clause_from_prompt_template(
        getattr(resolved_style, "prompt_template", "") or ""
    )
    if template_clause and not _profile_has_visual_rules(profile):
        profile["consistency_anchor"] = template_clause
    return visual_style_contract_from_style_profile(profile)


def _profile_has_visual_rules(profile: Mapping[str, Any]) -> bool:
    return any(
        str(profile.get(key) or "").strip()
        for key in (
            "shape_language",
            "material",
            "palette",
            "lighting",
            "world_elements",
            "consistency_anchor",
        )
    )


def _style_clause_from_prompt_template(prompt_template: str) -> str:
    text = str(prompt_template or "").replace("{prompt}", " ")
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,.:;")


__all__ = ["VisualStyleContractResolver"]
