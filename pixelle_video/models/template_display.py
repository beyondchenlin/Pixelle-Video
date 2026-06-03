from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

TEMPLATE_SIGNATURE_TEXT_PARAM_NAMES = frozenset(
    {"brand", "author", "describe", "footer", "author_desc"}
)
TEMPLATE_DISPLAY_CONTROL_PARAM_NAMES = frozenset(
    {"show_title", "show_signature"}
)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


@dataclass(frozen=True)
class TemplateDisplaySettings:
    show_title: bool = False
    show_signature: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "show_title", _coerce_bool(self.show_title))
        object.__setattr__(
            self,
            "show_signature",
            _coerce_bool(self.show_signature),
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "show_title": self.show_title,
            "show_signature": self.show_signature,
        }

    @classmethod
    def from_mapping(
        cls,
        value: "TemplateDisplaySettings | Mapping[str, Any] | None",
    ) -> "TemplateDisplaySettings":
        if isinstance(value, TemplateDisplaySettings):
            return value
        payload = dict(value or {}) if isinstance(value, Mapping) else {}
        return cls(
            show_title=_coerce_bool(payload.get("show_title"), False),
            show_signature=_coerce_bool(payload.get("show_signature"), False),
        )

    def render_title(self, title: str) -> str:
        return str(title) if self.show_title else ""

    def render_template_params(
        self,
        template_params: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        params = dict(template_params or {})
        if not self.show_signature:
            for key in TEMPLATE_SIGNATURE_TEXT_PARAM_NAMES:
                params[key] = ""
        return params


def resolve_template_params_and_display(
    template_params: Mapping[str, Any] | None,
    template_display: TemplateDisplaySettings | Mapping[str, Any] | None = None,
    *,
    default_display: TemplateDisplaySettings | Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], TemplateDisplaySettings]:
    params = dict(template_params or {})
    display_payload: TemplateDisplaySettings | Mapping[str, Any] | None
    if template_display is None:
        display_payload = default_display
    elif isinstance(template_display, TemplateDisplaySettings):
        display_payload = template_display
    else:
        display_payload = dict(template_display)
    return params, TemplateDisplaySettings.from_mapping(display_payload)
