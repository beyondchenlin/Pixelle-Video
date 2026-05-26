from __future__ import annotations

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
        if isinstance(style_contract, VisualStyleLayerContract):
            contracts.append(style_contract)
        elif isinstance(style_contract, Mapping):
            contracts.append(VisualStyleLayerContract.from_dict(style_contract))
        elif resolved_style is not None:
            contracts.append(visual_style_contract_from_style_profile(getattr(resolved_style, "style_profile", {}) or {}))
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


__all__ = ["VisualStyleContractResolver"]
