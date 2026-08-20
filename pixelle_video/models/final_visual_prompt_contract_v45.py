from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from pixelle_video.architecture.legacy_signature_field_guard import (
    reject_deprecated_signature_fields,
)
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.models.visual_entity_placement import (
    DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    VisualEntityPlacement,
    VisualEntitySceneFusion,
    VisualSceneType,
)

FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION = "final_visual_prompt_contract.v4_5"


@dataclass(frozen=True)
class FinalVisualPromptContractV45:
    """Provider-neutral V4.5 final visual prompt contract."""

    contract_id: str
    frame_id: str
    primary_visual_task: str
    required_subjects: Sequence[str]
    article_concretization: Mapping[str, Any] = field(default_factory=dict)
    series_visual_signature: SeriesVisualSignatureContract | Mapping[str, Any] = field(
        default_factory=SeriesVisualSignatureContract.disabled
    )
    diagram_render: Mapping[str, Any] = field(default_factory=dict)
    visible_text_policy: str = "no_visible_text"
    projected_prompt_parts: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    prompt_compiler_name: str = "FinalVisualPromptCompiler"
    entity_placement: VisualEntityPlacement | Mapping[str, Any] | None = None
    scene_fusion: VisualEntitySceneFusion | Mapping[str, Any] | None = None
    contract_version: str = FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION
    contract_content_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _require_text("contract_id", self.contract_id))
        object.__setattr__(self, "frame_id", _require_text("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "primary_visual_task",
            _require_text("primary_visual_task", self.primary_visual_task),
        )
        object.__setattr__(
            self,
            "required_subjects",
            _text_tuple("required_subjects", self.required_subjects, allow_empty=True),
        )
        article_concretization = dict(self.article_concretization or {})
        diagram_render = dict(self.diagram_render or {})
        projected_parts = tuple(dict(part) for part in self.projected_prompt_parts or ())
        reject_deprecated_signature_fields(
            article_concretization,
            context="final visual prompt contract",
        )
        reject_deprecated_signature_fields(
            diagram_render,
            context="final visual prompt contract",
        )
        reject_deprecated_signature_fields(
            projected_parts,
            context="final visual prompt contract",
        )
        signature = SeriesVisualSignatureContract.from_mapping(
            self.series_visual_signature
        )
        placement = (
            VisualEntityPlacement.from_mapping(self.entity_placement)
            if self.entity_placement is not None
            else None
        )
        fusion = (
            VisualEntitySceneFusion.from_mapping(self.scene_fusion)
            if self.scene_fusion is not None
            else None
        )
        if signature.enabled:
            if placement is None:
                raise ValueError(
                    f"frame {self.frame_id}: entity_placement must be present for an enabled signature"
                )
            if fusion is None:
                raise ValueError(
                    f"frame {self.frame_id}: scene_fusion must be present for an enabled signature"
                )
            _validate_signature_placement_contract(
                frame_id=self.frame_id,
                required_subjects=self.required_subjects,
                signature=signature,
                placement=placement,
                fusion=fusion,
            )
        elif placement is not None or fusion is not None:
            raise ValueError(
                f"frame {self.frame_id}: disabled signature must not carry placement or scene fusion"
            )
        object.__setattr__(
            self,
            "article_concretization",
            _freeze_json(article_concretization),
        )
        object.__setattr__(self, "series_visual_signature", signature)
        object.__setattr__(self, "entity_placement", placement)
        object.__setattr__(self, "scene_fusion", fusion)
        object.__setattr__(self, "diagram_render", _freeze_json(diagram_render))
        object.__setattr__(
            self,
            "visible_text_policy",
            _require_text("visible_text_policy", self.visible_text_policy),
        )
        object.__setattr__(
            self,
            "projected_prompt_parts",
            tuple(_freeze_json(part) for part in projected_parts),
        )
        object.__setattr__(
            self,
            "prompt_compiler_name",
            _require_text("prompt_compiler_name", self.prompt_compiler_name),
        )
        contract_version = _require_text("contract_version", self.contract_version)
        if contract_version != FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION:
            raise ValueError(
                f"contract_version must be {FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION}"
            )
        object.__setattr__(self, "contract_version", contract_version)
        content_hash = final_visual_prompt_contract_content_sha256(
            contract_version=contract_version,
            frame_id=self.frame_id,
            required_subjects=self.required_subjects,
            signature=signature,
            placement=placement,
            fusion=fusion,
        )
        supplied_hash = str(self.contract_content_sha256 or "").strip().lower()
        if supplied_hash and supplied_hash != content_hash:
            raise ValueError(
                "contract_content_sha256 must match canonical contract content"
            )
        object.__setattr__(self, "contract_content_sha256", content_hash)

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | "FinalVisualPromptContractV45",
    ) -> "FinalVisualPromptContractV45":
        if isinstance(source, cls):
            return source
        if not isinstance(source, Mapping):
            raise ValueError("final visual prompt contract V4.5 must be a mapping")
        data = dict(source)
        schema_version = data.get("schema_version", "v4.5-signature")
        if schema_version != "v4.5-signature":
            raise ValueError("schema_version must be v4.5-signature")
        return cls(
            contract_id=data.get("contract_id", ""),
            frame_id=data.get("frame_id", ""),
            primary_visual_task=data.get("primary_visual_task", ""),
            required_subjects=data.get("required_subjects") or (),
            article_concretization=data.get("article_concretization") or {},
            series_visual_signature=data.get("series_visual_signature") or {},
            diagram_render=data.get("diagram_render") or {},
            visible_text_policy=data.get("visible_text_policy", "no_visible_text"),
            projected_prompt_parts=data.get("projected_prompt_parts") or (),
            prompt_compiler_name=data.get(
                "prompt_compiler_name",
                "FinalVisualPromptCompiler",
            ),
            entity_placement=data.get("entity_placement"),
            scene_fusion=data.get("scene_fusion"),
            contract_version=data.get(
                "contract_version",
                FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION,
            ),
            contract_content_sha256=data.get("contract_content_sha256", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": "v4.5-signature",
            "contract_id": self.contract_id,
            "frame_id": self.frame_id,
            "primary_visual_task": self.primary_visual_task,
            "required_subjects": list(self.required_subjects),
            "article_concretization": _thaw_json(self.article_concretization),
            "series_visual_signature": self.series_visual_signature.to_dict(),
            "entity_placement": (
                self.entity_placement.to_dict() if self.entity_placement else None
            ),
            "scene_fusion": self.scene_fusion.to_dict() if self.scene_fusion else None,
            "diagram_render": _thaw_json(self.diagram_render),
            "visible_text_policy": self.visible_text_policy,
            "projected_prompt_parts": _thaw_json(self.projected_prompt_parts),
            "prompt_compiler_name": self.prompt_compiler_name,
            "contract_version": self.contract_version,
            "contract_content_sha256": self.contract_content_sha256,
        }
        reject_deprecated_signature_fields(
            payload,
            context="final visual prompt contract",
        )
        return payload


def final_visual_prompt_contract_content_sha256(
    *,
    contract_version: str,
    frame_id: str,
    required_subjects: Sequence[str],
    signature: SeriesVisualSignatureContract,
    placement: VisualEntityPlacement | None,
    fusion: VisualEntitySceneFusion | None,
) -> str:
    profile = signature.profile
    payload = {
        "contract_version": contract_version,
        "frame_id": frame_id,
        "required_subjects": list(required_subjects),
        "identity_content_sha256": (
            profile.identity_content_sha256 if profile is not None else ""
        ),
        "series_visual_signature_role": signature.role.value,
        "entity_placement": placement.to_dict() if placement is not None else None,
        "scene_fusion": fusion.to_dict() if fusion is not None else None,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validate_signature_placement_contract(
    *,
    frame_id: str,
    required_subjects: Sequence[str],
    signature: SeriesVisualSignatureContract,
    placement: VisualEntityPlacement,
    fusion: VisualEntitySceneFusion,
) -> None:
    if placement.frame_id != frame_id:
        raise ValueError(
            f"frame {frame_id}: entity_placement.frame_id must match contract frame_id"
        )
    if fusion.frame_id != frame_id:
        raise ValueError(
            f"frame {frame_id}: scene_fusion.frame_id must match contract frame_id"
        )
    if placement.scene_type is not fusion.scene_type:
        raise ValueError(
            f"frame {frame_id}: entity_placement.scene_type must match scene_fusion.scene_type"
        )
    if placement.relative_size is not signature.relative_size:
        raise ValueError(
            f"frame {frame_id}: entity_placement.relative_size exceeds or conflicts with signature limit"
        )
    if (
        placement.scene_type is VisualSceneType.PHYSICAL_SCENE
        and fusion.contact_relation != placement.support_relation
    ):
        raise ValueError(
            f"frame {frame_id}: scene_fusion.contact_relation must match "
            "entity_placement.support_relation"
        )
    profile = signature.profile
    if profile is None:
        raise ValueError(f"frame {frame_id}: enabled signature profile is missing")
    core_keys = {trait.casefold() for trait in profile.core_identity_traits}
    for index, trait in enumerate(placement.visible_core_traits):
        if trait.casefold() not in core_keys:
            raise ValueError(
                f"frame {frame_id}: entity_placement.visible_core_traits[{index}] "
                "must come from core_identity_traits"
            )
    protected_keys = {subject.casefold() for subject in fusion.protected_subjects}
    for index, subject in enumerate(required_subjects):
        if subject.casefold() not in protected_keys:
            raise ValueError(
                f"frame {frame_id}: scene_fusion.protected_subjects is missing "
                f"required_subjects[{index}]"
            )
    forbidden_keys = {
        item.casefold() for item in fusion.forbidden_compositions
    }
    for index, composition in enumerate(
        DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS
    ):
        if composition.casefold() not in forbidden_keys:
            raise ValueError(
                f"frame {frame_id}: scene_fusion.forbidden_compositions is "
                f"missing required composition[{index}]"
            )


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return unicodedata.normalize("NFC", " ".join(value.strip().split()))


def _text_tuple(
    field_name: str,
    values: Sequence[Any],
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    result = tuple(_require_text(field_name, value) for value in values)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(child) for key, child in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            "FinalVisualPromptContractV45 values must not contain non-finite floats"
        )
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(
        f"FinalVisualPromptContractV45 values must be JSON-compatible, got {type(value).__name__}"
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


__all__ = [
    "FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION",
    "FinalVisualPromptContractV45",
    "final_visual_prompt_contract_content_sha256",
]
