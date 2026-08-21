from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.content_bound_ip import ContentBoundIPPresencePlan
from pixelle_video.models.mandatory_content_bound_visual_anchor import (
    MandatoryContentBoundVisualAnchorContract,
)
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.models.visual_entity_placement import (
    VisualEntityPlacement,
    VisualEntitySceneFusion,
)

FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION = "final_visual_prompt_contract.v4_6"
FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA = "v4.6-content-bound-anchor"


@dataclass(frozen=True)
class FinalVisualPromptContractV46:
    contract_id: str
    frame_id: str
    primary_visual_task: str
    mandatory_anchor_contract: MandatoryContentBoundVisualAnchorContract | Mapping[str, Any]
    article_concretization: Mapping[str, Any] = field(default_factory=dict)
    diagram_render: Mapping[str, Any] = field(default_factory=dict)
    visible_text_policy: str = "no_visible_text"
    projected_prompt_parts: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    prompt_compiler_name: str = "FinalVisualPromptCompiler"
    contract_version: str = FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION
    contract_content_sha256: str = ""

    def __post_init__(self) -> None:
        contract_id = _text(self.contract_id, "contract_id", 512)
        frame_id = _text(self.frame_id, "frame_id", 256)
        primary_visual_task = _text(
            self.primary_visual_task,
            "primary_visual_task",
            256,
        )
        mandatory = MandatoryContentBoundVisualAnchorContract.from_mapping(
            self.mandatory_anchor_contract
        )
        if mandatory.frame_id != frame_id:
            raise ValueError(
                f"frame {frame_id}: mandatory anchor contract frame id must match"
            )
        object.__setattr__(self, "contract_id", contract_id)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "primary_visual_task", primary_visual_task)
        object.__setattr__(self, "mandatory_anchor_contract", mandatory)
        object.__setattr__(
            self,
            "article_concretization",
            _json_mapping(self.article_concretization, "article_concretization"),
        )
        object.__setattr__(
            self,
            "diagram_render",
            _json_mapping(self.diagram_render, "diagram_render"),
        )
        if isinstance(self.projected_prompt_parts, (str, bytes)) or not isinstance(
            self.projected_prompt_parts, Sequence
        ):
            raise ValueError("projected_prompt_parts must be a sequence of mappings")
        parts = tuple(
            _json_mapping(value, "projected_prompt_parts")
            for value in self.projected_prompt_parts
        )
        object.__setattr__(self, "projected_prompt_parts", parts)
        object.__setattr__(
            self,
            "visible_text_policy",
            _text(self.visible_text_policy, "visible_text_policy", 128),
        )
        object.__setattr__(
            self,
            "prompt_compiler_name",
            _text(self.prompt_compiler_name, "prompt_compiler_name", 128),
        )
        version = _text(self.contract_version, "contract_version", 128)
        if version != FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION:
            raise ValueError(
                f"contract_version must be {FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION}"
            )
        object.__setattr__(self, "contract_version", version)
        content_hash = _hash(self._canonical_payload())
        supplied_hash = str(self.contract_content_sha256 or "").strip().lower()
        if supplied_hash and supplied_hash != content_hash:
            raise ValueError("contract_content_sha256 must match canonical content")
        object.__setattr__(self, "contract_content_sha256", content_hash)

    @property
    def required_subjects(self) -> tuple[str, ...]:
        return self.mandatory_anchor_contract.required_subject_labels

    @property
    def structured_required_subjects(self) -> tuple[Any, ...]:
        return tuple(self.mandatory_anchor_contract.required_subjects)

    @property
    def series_visual_signature(self) -> SeriesVisualSignatureContract:
        return self.mandatory_anchor_contract.identity_contract

    @property
    def entity_placement(self) -> VisualEntityPlacement:
        return self.mandatory_anchor_contract.placement

    @property
    def scene_fusion(self) -> VisualEntitySceneFusion:
        return self.mandatory_anchor_contract.scene_fusion

    @property
    def content_bound_plan(self) -> ContentBoundIPPresencePlan:
        return self.mandatory_anchor_contract.participation_plan

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | FinalVisualPromptContractV46,
    ) -> FinalVisualPromptContractV46:
        if isinstance(source, cls):
            return source
        if not isinstance(source, Mapping):
            raise ValueError("final visual prompt contract V4.6 must be a mapping")
        schema = source.get("schema_version", FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA)
        if schema != FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA:
            raise ValueError(
                f"schema_version must be {FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA}"
            )
        return cls(
            contract_id=source.get("contract_id", ""),
            frame_id=source.get("frame_id", ""),
            primary_visual_task=source.get("primary_visual_task", ""),
            mandatory_anchor_contract=source.get("mandatory_anchor_contract") or {},
            article_concretization=source.get("article_concretization") or {},
            diagram_render=source.get("diagram_render") or {},
            visible_text_policy=source.get("visible_text_policy", "no_visible_text"),
            projected_prompt_parts=source.get("projected_prompt_parts") or (),
            prompt_compiler_name=source.get(
                "prompt_compiler_name", "FinalVisualPromptCompiler"
            ),
            contract_version=source.get(
                "contract_version", FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION
            ),
            contract_content_sha256=source.get("contract_content_sha256", ""),
        )

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "frame_id": self.frame_id,
            "primary_visual_task": self.primary_visual_task,
            "mandatory_anchor_contract_sha256": (
                self.mandatory_anchor_contract.contract_content_sha256
            ),
            "article_concretization": self.article_concretization,
            "diagram_render": self.diagram_render,
            "visible_text_policy": self.visible_text_policy,
            "projected_prompt_parts": list(self.projected_prompt_parts),
            "prompt_compiler_name": self.prompt_compiler_name,
            "contract_version": self.contract_version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA,
            "contract_id": self.contract_id,
            "frame_id": self.frame_id,
            "primary_visual_task": self.primary_visual_task,
            "required_subjects": [
                subject.to_dict() for subject in self.structured_required_subjects
            ],
            "article_concretization": dict(self.article_concretization),
            "series_visual_signature": self.series_visual_signature.to_dict(),
            "entity_placement": self.entity_placement.to_dict(),
            "scene_fusion": self.scene_fusion.to_dict(),
            "content_bound_ip_presence_plan": self.content_bound_plan.to_dict(),
            "mandatory_anchor_contract": self.mandatory_anchor_contract.to_dict(),
            "diagram_render": dict(self.diagram_render),
            "visible_text_policy": self.visible_text_policy,
            "projected_prompt_parts": [dict(value) for value in self.projected_prompt_parts],
            "prompt_compiler_name": self.prompt_compiler_name,
            "contract_version": self.contract_version,
            "contract_content_sha256": self.contract_content_sha256,
        }


def _text(value: Any, field_name: str, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    text = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if len(text) > max_chars:
        raise ValueError(f"{field_name} must be <= {max_chars} characters")
    return text


def _json_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    try:
        serialized = json.dumps(
            dict(value),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain JSON-compatible values") from exc


def _hash(value: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


__all__ = [
    "FINAL_VISUAL_PROMPT_CONTRACT_V46_SCHEMA",
    "FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION",
    "FinalVisualPromptContractV46",
]
