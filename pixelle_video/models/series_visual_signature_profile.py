from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.series_visual_signature_identity import (
    SeriesVisualSignatureIdentityContract,
)


@dataclass(frozen=True)
class SeriesVisualSignatureProfile:
    profile_id: str
    display_name: str
    identity_kernel: tuple[str, ...]
    appearance_traits: tuple[str, ...]
    action_affordances: tuple[str, ...]
    primary_role_affordances: tuple[str, ...]
    supporting_role_affordances: tuple[str, ...]
    forbidden_role_forms: tuple[str, ...]
    reference_assets: tuple[str, ...] = ()
    identity_contract: SeriesVisualSignatureIdentityContract | Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "series_visual_signature_profile.v4_1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _require_text("profile_id", self.profile_id))
        object.__setattr__(self, "display_name", _require_text("display_name", self.display_name))
        for field_name in (
            "identity_kernel",
            "appearance_traits",
            "action_affordances",
            "primary_role_affordances",
            "supporting_role_affordances",
            "forbidden_role_forms",
            "reference_assets",
        ):
            object.__setattr__(self, field_name, _normalize_text_tuple(getattr(self, field_name)))
        if not self.identity_kernel:
            raise ValueError("identity_kernel must not be empty")
        metadata = dict(self.metadata or {})
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(
            self,
            "identity_contract",
            _resolve_identity_contract(
                identity_contract=self.identity_contract,
                metadata=metadata,
                display_name=self.display_name,
                identity_kernel=self.identity_kernel,
                forbidden_role_forms=self.forbidden_role_forms,
                reference_assets=self.reference_assets,
            ),
        )
        object.__setattr__(self, "version", _require_text("version", self.version))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "identity_kernel": list(self.identity_kernel),
            "appearance_traits": list(self.appearance_traits),
            "action_affordances": list(self.action_affordances),
            "primary_role_affordances": list(self.primary_role_affordances),
            "supporting_role_affordances": list(self.supporting_role_affordances),
            "forbidden_role_forms": list(self.forbidden_role_forms),
            "reference_assets": list(self.reference_assets),
            "identity_contract": self.identity_contract.to_dict(),
            "metadata": dict(self.metadata),
        }


def _require_text(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_text_tuple(values: Sequence[str] | None) -> tuple[str, ...]:
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


def _resolve_identity_contract(
    *,
    identity_contract: SeriesVisualSignatureIdentityContract | Mapping[str, Any] | None,
    metadata: Mapping[str, Any],
    display_name: str,
    identity_kernel: Sequence[str],
    forbidden_role_forms: Sequence[str],
    reference_assets: Sequence[str],
) -> SeriesVisualSignatureIdentityContract:
    if isinstance(identity_contract, SeriesVisualSignatureIdentityContract):
        return identity_contract
    if isinstance(identity_contract, Mapping):
        return SeriesVisualSignatureIdentityContract.from_dict(identity_contract)
    metadata_contract = metadata.get("identity_contract")
    if isinstance(metadata_contract, SeriesVisualSignatureIdentityContract):
        return metadata_contract
    if isinstance(metadata_contract, Mapping):
        return SeriesVisualSignatureIdentityContract.from_dict(metadata_contract)
    return SeriesVisualSignatureIdentityContract.fallback(
        canonical_identity_name=display_name,
        identity_kernel=identity_kernel,
        forbidden_role_forms=forbidden_role_forms,
        reference_assets=reference_assets,
    )


__all__ = ["SeriesVisualSignatureProfile"]
