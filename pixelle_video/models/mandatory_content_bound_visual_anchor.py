from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.article_understanding import SubjectAnchor
from pixelle_video.models.content_bound_ip import ContentBoundIPPresencePlan
from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.models.visual_entity_placement import (
    DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS,
    VisualEntityPlacement,
    VisualEntitySceneFusion,
)

MANDATORY_CONTENT_BOUND_VISUAL_ANCHOR_VERSION = (
    "mandatory_content_bound_visual_anchor.v1"
)


class SemanticRemovalMode(str, Enum):
    ANCHOR_DISTINCT_FROM_SUBJECT = "anchor_distinct_from_subject"
    ANCHOR_IS_ARTICLE_SUBJECT = "anchor_is_article_subject"


@dataclass(frozen=True)
class SemanticRemovalTest:
    mode: SemanticRemovalMode | str
    content_survives_without_anchor_or_brand_identity: bool
    anchor_contribution_is_meaningful: bool
    content_survival_evidence: str
    anchor_contribution_evidence: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _enum(self.mode, SemanticRemovalMode, "mode"))
        if not isinstance(self.content_survives_without_anchor_or_brand_identity, bool):
            raise ValueError(
                "content_survives_without_anchor_or_brand_identity must be a boolean"
            )
        if not self.content_survives_without_anchor_or_brand_identity:
            raise ValueError("semantic removal content-survival test must pass")
        if not isinstance(self.anchor_contribution_is_meaningful, bool):
            raise ValueError("anchor_contribution_is_meaningful must be a boolean")
        if not self.anchor_contribution_is_meaningful:
            raise ValueError("semantic removal anchor-contribution test must pass")
        object.__setattr__(
            self,
            "content_survival_evidence",
            _text(self.content_survival_evidence, "content_survival_evidence"),
        )
        object.__setattr__(
            self,
            "anchor_contribution_evidence",
            _text(self.anchor_contribution_evidence, "anchor_contribution_evidence"),
        )

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | SemanticRemovalTest,
    ) -> SemanticRemovalTest:
        if isinstance(source, cls):
            return source
        if not isinstance(source, Mapping):
            raise ValueError("semantic_removal_test must be a mapping")
        return cls(
            mode=source.get("mode", ""),
            content_survives_without_anchor_or_brand_identity=source.get(
                "content_survives_without_anchor_or_brand_identity"
            ),
            anchor_contribution_is_meaningful=source.get(
                "anchor_contribution_is_meaningful"
            ),
            content_survival_evidence=source.get("content_survival_evidence", ""),
            anchor_contribution_evidence=source.get(
                "anchor_contribution_evidence", ""
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "content_survives_without_anchor_or_brand_identity": (
                self.content_survives_without_anchor_or_brand_identity
            ),
            "anchor_contribution_is_meaningful": (
                self.anchor_contribution_is_meaningful
            ),
            "content_survival_evidence": self.content_survival_evidence,
            "anchor_contribution_evidence": self.anchor_contribution_evidence,
        }


@dataclass(frozen=True)
class MandatoryContentBoundVisualAnchorContract:
    frame_id: str
    content_claim: str
    required_subjects: Sequence[SubjectAnchor | Mapping[str, Any]]
    visual_thesis: str
    participation_plan: ContentBoundIPPresencePlan | Mapping[str, Any]
    identity_contract: SeriesVisualSignatureContract | Mapping[str, Any]
    placement: VisualEntityPlacement | Mapping[str, Any]
    scene_fusion: VisualEntitySceneFusion | Mapping[str, Any]
    semantic_removal_test: SemanticRemovalTest | Mapping[str, Any]
    final_scene_description: str
    forbidden_compositions: Sequence[str] = field(
        default_factory=lambda: DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS
    )
    anchor_subject_overlap: bool = False
    version: str = MANDATORY_CONTENT_BOUND_VISUAL_ANCHOR_VERSION
    contract_content_sha256: str = ""

    def __post_init__(self) -> None:
        frame_id = _text(self.frame_id, "frame_id", max_chars=256)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(
            self,
            "content_claim",
            _text(self.content_claim, "content_claim", max_chars=2000),
        )
        subjects = _subjects(self.required_subjects)
        if not subjects:
            raise ValueError(
                f"frame {frame_id}: structured required subjects must not be empty"
            )
        object.__setattr__(self, "required_subjects", subjects)
        object.__setattr__(
            self,
            "visual_thesis",
            _text(self.visual_thesis, "visual_thesis", max_chars=4000),
        )
        plan = (
            self.participation_plan
            if isinstance(self.participation_plan, ContentBoundIPPresencePlan)
            else ContentBoundIPPresencePlan.from_mapping(self.participation_plan)
        )
        if plan.frame_id != frame_id:
            raise ValueError(
                f"frame {frame_id}: participation_plan.frame_id must match frame_id"
            )
        object.__setattr__(self, "participation_plan", plan)
        identity = SeriesVisualSignatureContract.from_mapping(self.identity_contract)
        if not identity.enabled or identity.profile is None:
            raise ValueError(
                f"frame {frame_id}: mandatory anchor requires an enabled identity contract"
            )
        object.__setattr__(self, "identity_contract", identity)
        placement = VisualEntityPlacement.from_mapping(self.placement)
        fusion = VisualEntitySceneFusion.from_mapping(self.scene_fusion)
        if placement.frame_id != frame_id or fusion.frame_id != frame_id:
            raise ValueError(
                f"frame {frame_id}: placement and scene_fusion frame ids must match"
            )
        if placement.scene_type is not fusion.scene_type:
            raise ValueError(
                f"frame {frame_id}: placement and scene_fusion scene types must match"
            )
        if placement.instance_count != 1:
            raise ValueError(f"frame {frame_id}: mandatory anchor instance count must be 1")
        if placement.relation_target.casefold() != plan.interaction_target.casefold():
            raise ValueError(
                f"frame {frame_id}: placement relation target must match participation target"
            )
        if placement.action.casefold() != plan.semantic_action.casefold():
            raise ValueError(
                f"frame {frame_id}: placement action must match participation action"
            )
        if abs(placement.area_ratio - plan.recommended_area_ratio) > 0.0001:
            raise ValueError(
                f"frame {frame_id}: placement area ratio must match semantic plan"
            )
        protected = {value.casefold() for value in fusion.protected_subjects}
        for subject in subjects:
            if subject.label.casefold() not in protected:
                raise ValueError(
                    f"frame {frame_id}: scene fusion is missing protected subject {subject.subject_id}"
                )
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "scene_fusion", fusion)
        removal = SemanticRemovalTest.from_mapping(self.semantic_removal_test)
        if self.anchor_subject_overlap and (
            removal.mode is not SemanticRemovalMode.ANCHOR_IS_ARTICLE_SUBJECT
        ):
            raise ValueError(
                f"frame {frame_id}: anchor overlap requires anchor-is-subject removal mode"
            )
        if not self.anchor_subject_overlap and (
            removal.mode is not SemanticRemovalMode.ANCHOR_DISTINCT_FROM_SUBJECT
        ):
            raise ValueError(
                f"frame {frame_id}: distinct anchor requires distinct-subject removal mode"
            )
        object.__setattr__(self, "semantic_removal_test", removal)
        object.__setattr__(
            self,
            "final_scene_description",
            _text(
                self.final_scene_description,
                "final_scene_description",
                max_chars=20_000,
            ),
        )
        forbidden = _strings(self.forbidden_compositions, "forbidden_compositions")
        required_forbidden = {
            value.casefold() for value in DEFAULT_VISUAL_ENTITY_FORBIDDEN_COMPOSITIONS
        }
        if not required_forbidden.issubset(
            {value.casefold() for value in forbidden}
        ):
            raise ValueError(
                f"frame {frame_id}: forbidden compositions must include product defaults"
            )
        object.__setattr__(self, "forbidden_compositions", forbidden)
        if not isinstance(self.anchor_subject_overlap, bool):
            raise ValueError("anchor_subject_overlap must be a boolean")
        version = _text(self.version, "version", max_chars=128)
        if version != MANDATORY_CONTENT_BOUND_VISUAL_ANCHOR_VERSION:
            raise ValueError(
                "mandatory content-bound visual anchor version is not supported"
            )
        object.__setattr__(self, "version", version)
        content_hash = _contract_hash(self._canonical_payload())
        supplied_hash = str(self.contract_content_sha256 or "").strip().lower()
        if supplied_hash and supplied_hash != content_hash:
            raise ValueError("contract_content_sha256 must match canonical content")
        object.__setattr__(self, "contract_content_sha256", content_hash)

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | MandatoryContentBoundVisualAnchorContract,
    ) -> MandatoryContentBoundVisualAnchorContract:
        if isinstance(source, cls):
            return source
        if not isinstance(source, Mapping):
            raise ValueError("mandatory visual anchor contract must be a mapping")
        return cls(
            frame_id=source.get("frame_id", ""),
            content_claim=source.get("content_claim", ""),
            required_subjects=source.get("required_subjects") or (),
            visual_thesis=source.get("visual_thesis", ""),
            participation_plan=source.get("participation_plan") or {},
            identity_contract=source.get("identity_contract") or {},
            placement=source.get("placement") or {},
            scene_fusion=source.get("scene_fusion") or {},
            semantic_removal_test=source.get("semantic_removal_test") or {},
            final_scene_description=source.get("final_scene_description", ""),
            forbidden_compositions=source.get("forbidden_compositions") or (),
            anchor_subject_overlap=source.get("anchor_subject_overlap", False),
            version=source.get(
                "version", MANDATORY_CONTENT_BOUND_VISUAL_ANCHOR_VERSION
            ),
            contract_content_sha256=source.get("contract_content_sha256", ""),
        )

    @property
    def required_subject_labels(self) -> tuple[str, ...]:
        return tuple(subject.label for subject in self.required_subjects)

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frame_id": self.frame_id,
            "content_claim": self.content_claim,
            "required_subjects": [subject.to_dict() for subject in self.required_subjects],
            "visual_thesis": self.visual_thesis,
            "participation_plan": self.participation_plan.to_dict(),
            "identity_contract": self.identity_contract.to_dict(),
            "placement": self.placement.to_dict(),
            "scene_fusion": self.scene_fusion.to_dict(),
            "semantic_removal_test": self.semantic_removal_test.to_dict(),
            "final_scene_description": self.final_scene_description,
            "forbidden_compositions": list(self.forbidden_compositions),
            "anchor_subject_overlap": self.anchor_subject_overlap,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._canonical_payload(),
            "contract_content_sha256": self.contract_content_sha256,
        }


def build_subject_anchors(
    *,
    frame_id: str,
    values: Sequence[Any],
    evidence_source: str = "required_subject",
) -> tuple[SubjectAnchor, ...]:
    subjects: list[SubjectAnchor] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        if isinstance(value, SubjectAnchor):
            subject = value
        elif isinstance(value, Mapping):
            subject = SubjectAnchor(**dict(value))
        else:
            label = " ".join(str(value or "").strip().split())
            if not label:
                continue
            digest = hashlib.sha256(label.casefold().encode("utf-8")).hexdigest()[:12]
            subject = SubjectAnchor(
                subject_id=f"{frame_id}:subject:{digest}",
                label=label,
                source_phrase=label,
                evidence_span_ids=(f"{frame_id}:{evidence_source}:{index}",),
                importance="required",
                visual_presence="explicit_visible",
                loss_policy="must_keep",
            )
        if subject.subject_id in seen:
            continue
        seen.add(subject.subject_id)
        subjects.append(subject)
    return tuple(subjects)


def _subjects(values: Sequence[Any]) -> tuple[SubjectAnchor, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("required_subjects must be a sequence of SubjectAnchor values")
    subjects: list[SubjectAnchor] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, SubjectAnchor):
            subject = value
        elif isinstance(value, Mapping):
            subject = SubjectAnchor(**dict(value))
        else:
            raise ValueError("required_subjects must contain structured subjects")
        if subject.subject_id in seen:
            raise ValueError("required_subjects must have unique subject ids")
        seen.add(subject.subject_id)
        subjects.append(subject)
    return tuple(subjects)


def _enum(value: Any, enum_cls: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = str(getattr(value, "value", value) or "").strip()
    for item in enum_cls:
        if text in {item.value, item.name}:
            return item
    raise ValueError(f"{field_name} must be a supported {enum_cls.__name__}")


def _text(value: Any, field_name: str, *, max_chars: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if len(normalized) > max_chars:
        raise ValueError(f"{field_name} must be <= {max_chars} characters")
    return normalized


def _strings(values: Sequence[Any], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value, field_name, max_chars=512)
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            result.append(text)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return tuple(result)


def _contract_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


__all__ = [
    "MANDATORY_CONTENT_BOUND_VISUAL_ANCHOR_VERSION",
    "MandatoryContentBoundVisualAnchorContract",
    "SemanticRemovalMode",
    "SemanticRemovalTest",
    "build_subject_anchors",
]
