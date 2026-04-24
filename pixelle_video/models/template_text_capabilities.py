from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TextSlotSpec:
    slot: str
    roles: tuple[str, ...]
    style_profiles: tuple[str, ...] = ()
    layer_min: int = 0
    layer_max: int = 99


@dataclass(frozen=True)
class TemplateTextCapabilities:
    template_id: str
    slots: tuple[TextSlotSpec, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TemplateTextCapabilities":
        return cls(
            template_id=str(data["template_id"]),
            slots=tuple(
                TextSlotSpec(
                    slot=str(item["slot"]),
                    roles=tuple(str(role) for role in item.get("roles", ())),
                    style_profiles=tuple(
                        str(style) for style in item.get("style_profiles", ())
                    ),
                    layer_min=int(item.get("layer_min", 0)),
                    layer_max=int(item.get("layer_max", 99)),
                )
                for item in data.get("slots", ())
            ),
        )

    def validate(
        self,
        *,
        slot: str | None,
        role: str,
        style_profile: str | None,
        layer: int,
    ) -> None:
        effective_slot = slot or "center"
        matching = [item for item in self.slots if item.slot == effective_slot]
        if not matching:
            raise ValueError(f"unsupported text slot: {effective_slot}")

        spec = matching[0]
        if role not in spec.roles:
            raise ValueError(f"unsupported text role for slot {effective_slot}: {role}")
        if spec.style_profiles and style_profile and style_profile not in spec.style_profiles:
            raise ValueError(
                f"unsupported text style for slot {effective_slot}: {style_profile}"
            )
        if layer < spec.layer_min or layer > spec.layer_max:
            raise ValueError(f"unsupported text layer for slot {effective_slot}: {layer}")
