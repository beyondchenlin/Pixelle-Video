from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VisualLayerTarget(str, Enum):
    IP_CHARACTER = "ip_character"
    HUMAN_CHARACTER = "human_character"
    NON_IP_WORLD = "non_ip_world"
    ALL_NON_HUMAN = "all_non_human"
    ANIMAL = "animal"
    PROP = "prop"
    ENVIRONMENT = "environment"
    TEXT_BOARD = "text_board"
    BACKGROUND = "background"
    GLOBAL = "global"


class VisualRenderingStyle(str, Enum):
    STYLE_INHERITED = "style_inherited"
    PHOTOREALISTIC_HUMAN = "photorealistic_human"
    FLAT_MONOCHROME_ILLUSTRATION = "flat_monochrome_illustration"
    FLAT_ILLUSTRATION = "flat_illustration"
    CINEMATIC_REALISM = "cinematic_realism"
    STYLIZED_CHARACTER = "stylized_character"


@dataclass(frozen=True)
class VisualStyleLayer:
    layer_id: str
    targets: tuple[VisualLayerTarget, ...]
    rendering_style: VisualRenderingStyle
    positive_rules: tuple[str, ...] = ()
    boundary_rules: tuple[str, ...] = ()
    priority: int = 100
    exclusive: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "layer_id", _require_non_empty("layer_id", self.layer_id))
        object.__setattr__(self, "targets", _normalize_targets(self.targets))
        object.__setattr__(self, "rendering_style", VisualRenderingStyle(self.rendering_style))
        object.__setattr__(self, "positive_rules", _normalize_text_tuple("positive_rules", self.positive_rules))
        object.__setattr__(self, "boundary_rules", _normalize_text_tuple("boundary_rules", self.boundary_rules))
        object.__setattr__(self, "priority", int(self.priority))
        object.__setattr__(self, "exclusive", bool(self.exclusive))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "targets": [target.value for target in self.targets],
            "rendering_style": self.rendering_style.value,
            "positive_rules": list(self.positive_rules),
            "boundary_rules": list(self.boundary_rules),
            "priority": self.priority,
            "exclusive": self.exclusive,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VisualStyleLayer":
        if not isinstance(payload, Mapping):
            raise ValueError("VisualStyleLayer payload must be a mapping")
        return cls(
            layer_id=str(payload.get("layer_id") or ""),
            targets=tuple(payload.get("targets") or ()),
            rendering_style=payload.get("rendering_style") or VisualRenderingStyle.STYLE_INHERITED,
            positive_rules=tuple(payload.get("positive_rules") or ()),
            boundary_rules=tuple(payload.get("boundary_rules") or ()),
            priority=int(payload.get("priority", 100)),
            exclusive=bool(payload.get("exclusive", False)),
            metadata=payload.get("metadata") or {},
        )

    def prompt_clause(self) -> str:
        target_clause = ", ".join(_target_prompt_label(target) for target in self.targets)
        style_clause = _rendering_style_prompt_label(self.rendering_style)
        rules = ", ".join(_dedupe([*self.positive_rules, *self.boundary_rules]))
        if rules:
            return f"{target_clause}: {style_clause}, {rules}"
        return f"{target_clause}: {style_clause}"


@dataclass(frozen=True)
class VisualStyleLayerContract:
    layers: tuple[VisualStyleLayer, ...] = ()
    integration_rules: tuple[str, ...] = ()
    negative_rules: tuple[str, ...] = ()
    version: str = "visual_style_layer_contract.v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "layers", _normalize_layers(self.layers))
        object.__setattr__(self, "integration_rules", _normalize_text_tuple("integration_rules", self.integration_rules))
        object.__setattr__(self, "negative_rules", _normalize_text_tuple("negative_rules", self.negative_rules))
        object.__setattr__(self, "version", _require_non_empty("version", self.version))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def ordered_layers(self) -> tuple[VisualStyleLayer, ...]:
        return tuple(sorted(self.layers, key=lambda layer: layer.priority))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "layers": [layer.to_dict() for layer in self.layers],
            "integration_rules": list(self.integration_rules),
            "negative_rules": list(self.negative_rules),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "VisualStyleLayerContract":
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise ValueError("VisualStyleLayerContract payload must be a mapping")
        return cls(
            version=str(payload.get("version") or "visual_style_layer_contract.v1"),
            layers=tuple(VisualStyleLayer.from_dict(item) for item in payload.get("layers") or ()),
            integration_rules=tuple(payload.get("integration_rules") or ()),
            negative_rules=tuple(payload.get("negative_rules") or ()),
            metadata=payload.get("metadata") or {},
        )

    def merge(self, *others: "VisualStyleLayerContract") -> "VisualStyleLayerContract":
        layers_by_id: dict[str, VisualStyleLayer] = {layer.layer_id: layer for layer in self.layers}
        integration_rules = list(self.integration_rules)
        negative_rules = list(self.negative_rules)
        metadata = dict(self.metadata)
        for other in others:
            if other is None:
                continue
            for layer in other.layers:
                layers_by_id[layer.layer_id] = layer
            integration_rules.extend(other.integration_rules)
            negative_rules.extend(other.negative_rules)
            metadata.update(dict(other.metadata or {}))
        return VisualStyleLayerContract(
            layers=tuple(layers_by_id.values()),
            integration_rules=tuple(_dedupe(integration_rules)),
            negative_rules=tuple(_dedupe(negative_rules)),
            version=self.version,
            metadata=metadata,
        )

    def prompt_layer_clause(self, *targets: VisualLayerTarget) -> str:
        requested = set(targets)
        clauses = [
            layer.prompt_clause()
            for layer in self.ordered_layers()
            if not requested or requested.intersection(set(layer.targets))
        ]
        return "; ".join(_dedupe(clauses))


def visual_style_contract_from_style_profile(style_profile: Mapping[str, Any] | None) -> VisualStyleLayerContract:
    profile = style_profile or {}
    visual_rules = _dedupe(
        [
            str(profile.get("shape_language") or "").strip(),
            str(profile.get("material") or "").strip(),
            str(profile.get("palette") or "").strip(),
            str(profile.get("lighting") or "").strip(),
            str(profile.get("world_elements") or "").strip(),
            str(profile.get("consistency_anchor") or "").strip(),
        ]
    )
    if not visual_rules:
        return VisualStyleLayerContract()
    negative_rules = _split_rule_string(str(profile.get("negative_rules") or ""))
    style_kind = str(profile.get("style_kind") or "visual_only")
    layer = VisualStyleLayer(
        layer_id=f"style_resolution_{style_kind}",
        targets=(VisualLayerTarget.NON_IP_WORLD, VisualLayerTarget.ALL_NON_HUMAN),
        rendering_style=_infer_rendering_style(visual_rules),
        positive_rules=tuple(visual_rules),
        boundary_rules=(),
        priority=50,
    )
    return VisualStyleLayerContract(
        layers=(layer,),
        negative_rules=negative_rules,
        metadata={"source": "style_profile_adapter", "style_kind": style_kind},
    )


def default_mixed_style_world_contract() -> VisualStyleLayerContract:
    return VisualStyleLayerContract(
        layers=(
            VisualStyleLayer(
                layer_id="non_ip_world_flat_monochrome_default",
                targets=(VisualLayerTarget.ALL_NON_HUMAN, VisualLayerTarget.NON_IP_WORLD),
                rendering_style=VisualRenderingStyle.FLAT_MONOCHROME_ILLUSTRATION,
                positive_rules=(
                    "flat monochrome educational illustration",
                    "simple elegant silhouettes",
                    "smooth flowing lines",
                    "flat two-dimensional shapes",
                    "no texture",
                    "black-white-gray palette",
                    "soft diffused lighting",
                ),
                boundary_rules=("do not render non-IP world elements photorealistically",),
                priority=20,
            ),
        ),
        integration_rules=("single unified image", "not a split-screen", "not a collage"),
        negative_rules=(
            "fully photorealistic scene",
            "realistic background",
            "cartoon human",
            "split-screen",
            "collage",
        ),
        metadata={"source": "default_mixed_style_world_contract"},
    )


def _infer_rendering_style(rules: Sequence[str]) -> VisualRenderingStyle:
    joined = " ".join(rules).lower()
    if "monochrome" in joined and "flat" in joined:
        return VisualRenderingStyle.FLAT_MONOCHROME_ILLUSTRATION
    if "flat" in joined or "illustration" in joined:
        return VisualRenderingStyle.FLAT_ILLUSTRATION
    if "photoreal" in joined or "realistic" in joined:
        return VisualRenderingStyle.CINEMATIC_REALISM
    return VisualRenderingStyle.STYLE_INHERITED


def _target_prompt_label(target: VisualLayerTarget) -> str:
    labels = {
        VisualLayerTarget.IP_CHARACTER: "IP character layer",
        VisualLayerTarget.HUMAN_CHARACTER: "human character layer",
        VisualLayerTarget.NON_IP_WORLD: "non-IP world layer",
        VisualLayerTarget.ALL_NON_HUMAN: "non-IP animals, props, background, and environment",
        VisualLayerTarget.ANIMAL: "non-IP animals",
        VisualLayerTarget.PROP: "props",
        VisualLayerTarget.ENVIRONMENT: "environment",
        VisualLayerTarget.TEXT_BOARD: "teaching boards and readable visual boards",
        VisualLayerTarget.BACKGROUND: "background",
        VisualLayerTarget.GLOBAL: "whole image",
    }
    return labels[target]


def _rendering_style_prompt_label(style: VisualRenderingStyle) -> str:
    labels = {
        VisualRenderingStyle.STYLE_INHERITED: "inherited visual style",
        VisualRenderingStyle.PHOTOREALISTIC_HUMAN: "photorealistic real-human style",
        VisualRenderingStyle.FLAT_MONOCHROME_ILLUSTRATION: "flat monochrome illustration",
        VisualRenderingStyle.FLAT_ILLUSTRATION: "flat illustration",
        VisualRenderingStyle.CINEMATIC_REALISM: "cinematic realism",
        VisualRenderingStyle.STYLIZED_CHARACTER: "stylized character style",
    }
    return labels[style]


def _normalize_targets(values: Sequence[Any]) -> tuple[VisualLayerTarget, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError("targets must be a list or tuple")
    normalized = tuple(VisualLayerTarget(value) for value in values)
    if not normalized:
        raise ValueError("targets must not be empty")
    return tuple(dict.fromkeys(normalized))


def _normalize_layers(values: Sequence[Any]) -> tuple[VisualStyleLayer, ...]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError("layers must be a list or tuple")
    layers = tuple(item if isinstance(item, VisualStyleLayer) else VisualStyleLayer.from_dict(item) for item in values)
    layer_ids = [layer.layer_id for layer in layers]
    if len(layer_ids) != len(set(layer_ids)):
        raise ValueError("visual style layer ids must be unique")
    return layers


def _normalize_text_tuple(field_name: str, values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    return tuple(_dedupe(str(value).strip() for value in values if str(value).strip()))


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _split_rule_string(value: str) -> tuple[str, ...]:
    return tuple(_dedupe(part.strip() for part in value.split(",") if part.strip()))


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


__all__ = [
    "VisualLayerTarget",
    "VisualRenderingStyle",
    "VisualStyleLayer",
    "VisualStyleLayerContract",
    "default_mixed_style_world_contract",
    "visual_style_contract_from_style_profile",
]
