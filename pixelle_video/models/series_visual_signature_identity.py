from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SeriesVisualSignatureStructureMode(str, Enum):
    AUTO = "auto"
    WORKFLOW = "workflow"
    SYSTEM_PART = "system_part"
    BEFORE_AFTER = "before_after"
    ROLE_STATE = "role_state"
    CONCEPT_METAPHOR = "concept_metaphor"
    METHOD_LAYERS = "method_layers"
    MAP_ROUTE = "map_route"
    COMIC_SEQUENCE = "comic_sequence"
    PLAIN_SCENE = "plain_scene"
    PRODUCT_DEMO = "product_demo"
    HOST_EXPLAINER = "host_explainer"

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        default: "SeriesVisualSignatureStructureMode" | None = None,
    ) -> "SeriesVisualSignatureStructureMode":
        return _enum_from_value(value, cls, default or cls.AUTO)


class SeriesVisualSignatureParticipationMode(str, Enum):
    AUTO = "auto"
    HOST_EXPLAINER = "host_explainer"
    GUIDE_EXPLAINER = "guide_explainer"
    OPERATOR_DEMONSTRATOR = "operator_demonstrator"
    POINTER_ANNOTATOR = "pointer_annotator"
    COMPANION_WITNESS = "companion_witness"
    EVIDENCE_CURATOR = "evidence_curator"
    CONTRAST_JUDGE = "contrast_judge"
    EMOTIONAL_PROXY = "emotional_proxy"
    METAPHOR_SYMBOL = "metaphor_symbol"
    STRUCTURE_CARRIER = "structure_carrier"
    RELATIONSHIP_MEDIATOR = "relationship_mediator"
    NAVIGATOR_PATHFINDER = "navigator_pathfinder"
    MECHANIC_REPAIRER = "mechanic_repairer"
    THRESHOLD_GUARDIAN = "threshold_guardian"
    BACKGROUND_SIGNATURE = "background_signature"
    COMIC_COUNTERPOINT = "comic_counterpoint"
    ENVIRONMENT_BRANDING = "environment_branding"

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        default: "SeriesVisualSignatureParticipationMode" | None = None,
    ) -> "SeriesVisualSignatureParticipationMode":
        return _enum_from_value(value, cls, default or cls.AUTO)


@dataclass(frozen=True)
class SeriesVisualSignatureIdentityContract:
    canonical_identity_name: str
    required_identity_traits: tuple[str, ...]
    fixed_identity_clause: str = ""
    important_identity_traits: tuple[str, ...] = ()
    optional_appearance_traits: tuple[str, ...] = ()
    forbidden_identity_loss_rules: tuple[str, ...] = ()
    reference_assets: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "series_visual_signature_identity_contract.v4_2"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_identity_name",
            _require_text("canonical_identity_name", self.canonical_identity_name),
        )
        for field_name in (
            "required_identity_traits",
            "important_identity_traits",
            "optional_appearance_traits",
            "forbidden_identity_loss_rules",
            "reference_assets",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_text_tuple(getattr(self, field_name)),
            )
        if not self.required_identity_traits:
            raise ValueError("required_identity_traits must not be empty")
        fixed_clause = str(self.fixed_identity_clause or "").strip()
        if not fixed_clause:
            fixed_clause = _default_fixed_identity_clause(
                self.canonical_identity_name,
                self.required_identity_traits,
            )
        object.__setattr__(self, "fixed_identity_clause", fixed_clause)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "version", _require_text("version", self.version))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SeriesVisualSignatureIdentityContract":
        return cls(
            canonical_identity_name=payload.get("canonical_identity_name") or payload.get("display_name") or "",
            required_identity_traits=_normalize_text_tuple(payload.get("required_identity_traits")),
            fixed_identity_clause=str(payload.get("fixed_identity_clause") or "").strip(),
            important_identity_traits=_normalize_text_tuple(payload.get("important_identity_traits")),
            optional_appearance_traits=_normalize_text_tuple(payload.get("optional_appearance_traits")),
            forbidden_identity_loss_rules=_normalize_text_tuple(
                payload.get("forbidden_identity_loss_rules")
                or payload.get("forbidden_role_forms")
            ),
            reference_assets=_normalize_text_tuple(payload.get("reference_assets")),
            metadata=dict(payload.get("metadata") or {}),
            version=str(payload.get("version") or "series_visual_signature_identity_contract.v4_2"),
        )

    @classmethod
    def fallback(
        cls,
        *,
        canonical_identity_name: str,
        identity_kernel: Sequence[str],
        forbidden_role_forms: Sequence[str] = (),
        reference_assets: Sequence[str] = (),
    ) -> "SeriesVisualSignatureIdentityContract":
        required_traits = _normalize_text_tuple(identity_kernel) or (
            _require_text("canonical_identity_name", canonical_identity_name),
        )
        return cls(
            canonical_identity_name=canonical_identity_name,
            required_identity_traits=required_traits,
            forbidden_identity_loss_rules=_normalize_text_tuple(forbidden_role_forms),
            reference_assets=_normalize_text_tuple(reference_assets),
            metadata={"source": "SeriesVisualSignatureProfile.fallback"},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "canonical_identity_name": self.canonical_identity_name,
            "required_identity_traits": list(self.required_identity_traits),
            "important_identity_traits": list(self.important_identity_traits),
            "optional_appearance_traits": list(self.optional_appearance_traits),
            "fixed_identity_clause": self.fixed_identity_clause,
            "forbidden_identity_loss_rules": list(self.forbidden_identity_loss_rules),
            "reference_assets": list(self.reference_assets),
            "metadata": dict(self.metadata),
        }


def _default_fixed_identity_clause(
    canonical_identity_name: str,
    required_identity_traits: Sequence[str],
) -> str:
    traits = ", ".join(_normalize_text_tuple(required_identity_traits))
    return f"Fixed IP identity: {canonical_identity_name}; required identity traits: {traits}."


def _enum_from_value(value: Any, enum_cls: type[Enum], default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    return default


def _require_text(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_text_tuple(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
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
    return tuple(result)


__all__ = [
    "SeriesVisualSignatureIdentityContract",
    "SeriesVisualSignatureParticipationMode",
    "SeriesVisualSignatureStructureMode",
]
