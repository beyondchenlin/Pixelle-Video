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
from pixelle_video.models.series_visual_signature_projection_policy import (
    DEFAULT_MAX_REQUIRED_SUBJECT_CHARS,
    DEFAULT_MAX_REQUIRED_SUBJECTS,
)
from pixelle_video.models.visual_entity_placement import (
    DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    MAX_VISUAL_ENTITY_FRAME_ID_CHARS,
    VisualEntityPlacement,
    VisualEntitySceneFusion,
    VisualSceneType,
)

FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION = "final_visual_prompt_contract.v4_5"
MAX_V45_CONTRACT_ID_CHARS = 512
MAX_V45_PRIMARY_VISUAL_TASK_CHARS = 256
MAX_V45_PROTOCOL_TEXT_CHARS = 128
MAX_V45_PROJECTED_PROMPT_PARTS = 256
MAX_V45_JSON_DEPTH = 16
MAX_V45_JSON_NODES = 4096
MAX_V45_JSON_TEXT_CHARS = 200_000


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
        object.__setattr__(
            self,
            "contract_id",
            _require_text(
                "contract_id",
                self.contract_id,
                max_chars=MAX_V45_CONTRACT_ID_CHARS,
            ),
        )
        object.__setattr__(
            self,
            "frame_id",
            _require_text(
                "frame_id",
                self.frame_id,
                max_chars=MAX_VISUAL_ENTITY_FRAME_ID_CHARS,
            ),
        )
        object.__setattr__(
            self,
            "primary_visual_task",
            _require_text(
                "primary_visual_task",
                self.primary_visual_task,
                max_chars=MAX_V45_PRIMARY_VISUAL_TASK_CHARS,
            ),
        )
        object.__setattr__(
            self,
            "required_subjects",
            _text_tuple(
                "required_subjects",
                self.required_subjects,
                allow_empty=True,
                max_items=DEFAULT_MAX_REQUIRED_SUBJECTS,
                max_chars=DEFAULT_MAX_REQUIRED_SUBJECT_CHARS,
            ),
        )
        article_concretization = _freeze_json(
            self.article_concretization or {},
            field_name="article_concretization",
        )
        diagram_render = _freeze_json(
            self.diagram_render or {},
            field_name="diagram_render",
        )
        projected_parts_source = self.projected_prompt_parts or ()
        if (
            isinstance(projected_parts_source, (str, bytes, bytearray))
            or not isinstance(projected_parts_source, Sequence)
        ):
            raise ValueError("projected_prompt_parts must be a sequence of mappings")
        if len(projected_parts_source) > MAX_V45_PROJECTED_PROMPT_PARTS:
            raise ValueError(
                "projected_prompt_parts must contain at most "
                f"{MAX_V45_PROJECTED_PROMPT_PARTS} items"
            )
        if any(not isinstance(part, Mapping) for part in projected_parts_source):
            raise ValueError("projected_prompt_parts must contain only mappings")
        projected_parts = _freeze_json(
            tuple(projected_parts_source),
            field_name="projected_prompt_parts",
        )
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
        signature_source = self.series_visual_signature
        if isinstance(signature_source, SeriesVisualSignatureContract):
            signature_source = signature_source.to_dict()
        signature = SeriesVisualSignatureContract.from_mapping(signature_source)
        placement = (
            VisualEntityPlacement.from_mapping(
                self.entity_placement.to_dict()
                if isinstance(self.entity_placement, VisualEntityPlacement)
                else self.entity_placement
            )
            if self.entity_placement is not None
            else None
        )
        fusion = (
            VisualEntitySceneFusion.from_mapping(
                self.scene_fusion.to_dict()
                if isinstance(self.scene_fusion, VisualEntitySceneFusion)
                else self.scene_fusion
            )
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
            article_concretization,
        )
        object.__setattr__(self, "series_visual_signature", signature)
        object.__setattr__(self, "entity_placement", placement)
        object.__setattr__(self, "scene_fusion", fusion)
        object.__setattr__(self, "diagram_render", diagram_render)
        object.__setattr__(
            self,
            "visible_text_policy",
            _require_text(
                "visible_text_policy",
                self.visible_text_policy,
                max_chars=MAX_V45_PROTOCOL_TEXT_CHARS,
            ),
        )
        object.__setattr__(
            self,
            "projected_prompt_parts",
            projected_parts,
        )
        object.__setattr__(
            self,
            "prompt_compiler_name",
            _require_text(
                "prompt_compiler_name",
                self.prompt_compiler_name,
                max_chars=MAX_V45_PROTOCOL_TEXT_CHARS,
            ),
        )
        contract_version = _require_text(
            "contract_version",
            self.contract_version,
            max_chars=MAX_V45_PROTOCOL_TEXT_CHARS,
        )
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
    normalized_contract_version = _require_text(
        "contract_version",
        contract_version,
        max_chars=MAX_V45_PROTOCOL_TEXT_CHARS,
    )
    if normalized_contract_version != FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION:
        raise ValueError(
            f"contract_version must be {FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION}"
        )
    normalized_frame_id = _require_text(
        "frame_id",
        frame_id,
        max_chars=MAX_VISUAL_ENTITY_FRAME_ID_CHARS,
    )
    normalized_required_subjects = _text_tuple(
        "required_subjects",
        required_subjects,
        allow_empty=True,
        max_items=DEFAULT_MAX_REQUIRED_SUBJECTS,
        max_chars=DEFAULT_MAX_REQUIRED_SUBJECT_CHARS,
    )
    normalized_signature = SeriesVisualSignatureContract.from_mapping(
        signature.to_dict()
    )
    normalized_placement = (
        VisualEntityPlacement.from_mapping(placement.to_dict())
        if placement is not None
        else None
    )
    normalized_fusion = (
        VisualEntitySceneFusion.from_mapping(fusion.to_dict())
        if fusion is not None
        else None
    )
    if normalized_signature.enabled:
        if normalized_placement is None or normalized_fusion is None:
            raise ValueError(
                "enabled signature contract hash requires placement and scene fusion"
            )
        _validate_signature_placement_contract(
            frame_id=normalized_frame_id,
            required_subjects=normalized_required_subjects,
            signature=normalized_signature,
            placement=normalized_placement,
            fusion=normalized_fusion,
        )
    elif normalized_placement is not None or normalized_fusion is not None:
        raise ValueError(
            "disabled signature contract hash must not include placement or scene fusion"
        )
    profile = normalized_signature.profile
    payload = {
        "contract_version": normalized_contract_version,
        "frame_id": normalized_frame_id,
        "required_subjects": list(normalized_required_subjects),
        "identity_content_sha256": (
            profile.identity_content_sha256 if profile is not None else ""
        ),
        "series_visual_signature_role": normalized_signature.role.value,
        "entity_placement": (
            normalized_placement.to_dict()
            if normalized_placement is not None
            else None
        ),
        "scene_fusion": (
            normalized_fusion.to_dict() if normalized_fusion is not None else None
        ),
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


def _require_text(
    field_name: str,
    value: Any,
    *,
    max_chars: int | None = None,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if max_chars is not None and len(normalized) > max_chars:
        raise ValueError(f"{field_name} must be <= {max_chars} characters")
    return normalized


def _text_tuple(
    field_name: str,
    values: Sequence[Any],
    *,
    allow_empty: bool,
    max_items: int | None = None,
    max_chars: int | None = None,
) -> tuple[str, ...]:
    if values is None:
        values = ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    if max_items is not None and len(values) > max_items:
        raise ValueError(f"{field_name} must contain at most {max_items} items")
    result = tuple(
        _require_text(field_name, value, max_chars=max_chars) for value in values
    )
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _freeze_json(value: Any, *, field_name: str) -> Any:
    node_count = 0
    text_char_count = 0
    active_containers: set[int] = set()

    def visit(current: Any, *, depth: int) -> Any:
        nonlocal node_count, text_char_count
        node_count += 1
        if node_count > MAX_V45_JSON_NODES:
            raise ValueError(
                f"{field_name} exceeds {MAX_V45_JSON_NODES} JSON nodes"
            )
        if depth > MAX_V45_JSON_DEPTH:
            raise ValueError(
                f"{field_name} exceeds JSON nesting depth {MAX_V45_JSON_DEPTH}"
            )
        if isinstance(current, Mapping):
            container_id = id(current)
            if container_id in active_containers:
                raise ValueError(f"{field_name} must not contain cyclic mappings")
            active_containers.add(container_id)
            try:
                frozen: dict[str, Any] = {}
                for key, child in current.items():
                    if not isinstance(key, str):
                        raise ValueError(
                            f"{field_name} JSON object keys must be strings"
                        )
                    normalized_key = unicodedata.normalize("NFC", key)
                    text_char_count += len(normalized_key)
                    if text_char_count > MAX_V45_JSON_TEXT_CHARS:
                        raise ValueError(
                            f"{field_name} exceeds {MAX_V45_JSON_TEXT_CHARS} JSON text characters"
                        )
                    if normalized_key in frozen:
                        raise ValueError(
                            f"{field_name} contains duplicate normalized JSON keys"
                        )
                    frozen[normalized_key] = visit(child, depth=depth + 1)
                return MappingProxyType(frozen)
            finally:
                active_containers.remove(container_id)
        if isinstance(current, (list, tuple)):
            container_id = id(current)
            if container_id in active_containers:
                raise ValueError(f"{field_name} must not contain cyclic sequences")
            active_containers.add(container_id)
            try:
                return tuple(visit(child, depth=depth + 1) for child in current)
            finally:
                active_containers.remove(container_id)
        if isinstance(current, float) and not math.isfinite(current):
            raise ValueError(
                "FinalVisualPromptContractV45 values must not contain non-finite floats"
            )
        if isinstance(current, str):
            text_char_count += len(current)
            if text_char_count > MAX_V45_JSON_TEXT_CHARS:
                raise ValueError(
                    f"{field_name} exceeds {MAX_V45_JSON_TEXT_CHARS} JSON text characters"
                )
            return current
        if isinstance(current, (int, float, bool)) or current is None:
            return current
        raise ValueError(
            "FinalVisualPromptContractV45 values must be JSON-compatible, "
            f"got {type(current).__name__}"
        )

    return visit(value, depth=0)


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


__all__ = [
    "FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION",
    "FinalVisualPromptContractV45",
    "MAX_V45_JSON_DEPTH",
    "MAX_V45_JSON_NODES",
    "MAX_V45_JSON_TEXT_CHARS",
    "final_visual_prompt_contract_content_sha256",
]
