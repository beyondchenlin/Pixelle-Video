from __future__ import annotations

import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Protocol

RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ResourceResolverError(ValueError):
    """Base exception for public resource resolver contract failures."""


class ResourceIdInvalidError(ResourceResolverError):
    """Raised when a public resource identifier uses unsafe path/provider syntax."""


class ResourceNotFoundError(ResourceResolverError):
    """Raised when a valid public resource identifier is not configured."""


@dataclass(frozen=True)
class ResolvedResource:
    resource_id: str
    resolved_value: str
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        _validate_resource_id(self.resource_id)
        if not isinstance(self.resolved_value, str):
            raise ResourceResolverError("resolved_value must be a string")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class ResourceResolver(Protocol):
    def resolve_style_id(self, resource_id: str) -> ResolvedResource: ...

    def resolve_template_id(self, resource_id: str) -> ResolvedResource: ...

    def resolve_voice_id(self, resource_id: str) -> ResolvedResource: ...

    def resolve_bgm_id(self, resource_id: str) -> ResolvedResource: ...

    def resolve_workflow_preset_id(self, resource_id: str) -> ResolvedResource: ...

    def resolve_provider_preset_id(self, resource_id: str) -> ResolvedResource: ...


ResourceMapping = Mapping[str, str | ResolvedResource]


class StaticResourceResolver:
    """Dev/test resolver adapter backed by static mappings, not production routing."""

    def __init__(
        self,
        *,
        styles: ResourceMapping | None = None,
        templates: ResourceMapping | None = None,
        voices: ResourceMapping | None = None,
        bgms: ResourceMapping | None = None,
        workflow_presets: ResourceMapping | None = None,
        provider_presets: ResourceMapping | None = None,
    ) -> None:
        self._styles = _freeze_mapping("style", styles)
        self._templates = _freeze_mapping("template", templates)
        self._voices = _freeze_mapping("voice", voices)
        self._bgms = _freeze_mapping("bgm", bgms)
        self._workflow_presets = _freeze_mapping("workflow_preset", workflow_presets)
        self._provider_presets = _freeze_mapping("provider_preset", provider_presets)

    def resolve_style_id(self, resource_id: str) -> ResolvedResource:
        return self._resolve("style", resource_id, self._styles)

    def resolve_template_id(self, resource_id: str) -> ResolvedResource:
        return self._resolve("template", resource_id, self._templates)

    def resolve_voice_id(self, resource_id: str) -> ResolvedResource:
        return self._resolve("voice", resource_id, self._voices)

    def resolve_bgm_id(self, resource_id: str) -> ResolvedResource:
        return self._resolve("bgm", resource_id, self._bgms)

    def resolve_workflow_preset_id(self, resource_id: str) -> ResolvedResource:
        return self._resolve("workflow_preset", resource_id, self._workflow_presets)

    def resolve_provider_preset_id(self, resource_id: str) -> ResolvedResource:
        return self._resolve("provider_preset", resource_id, self._provider_presets)

    def _resolve(
        self,
        resource_type: str,
        resource_id: str,
        mapping: ResourceMapping,
    ) -> ResolvedResource:
        _validate_resource_id(resource_id)
        if resource_id not in mapping:
            raise ResourceNotFoundError(
                f"{resource_type} resource ID is not configured: {resource_id}"
            )

        resolved = mapping[resource_id]
        if isinstance(resolved, ResolvedResource):
            return resolved
        return ResolvedResource(resource_id=resource_id, resolved_value=resolved)


def _validate_resource_id(resource_id: str) -> None:
    if not isinstance(resource_id, str) or not RESOURCE_ID_PATTERN.fullmatch(resource_id):
        raise ResourceIdInvalidError(
            "resource ID must match ^[A-Za-z0-9][A-Za-z0-9_-]*$"
        )


def _freeze_mapping(
    resource_type: str,
    mapping: ResourceMapping | None,
) -> ResourceMapping:
    if mapping is not None and not isinstance(mapping, MappingABC):
        raise ResourceResolverError(f"{resource_type} mapping must be a mapping")

    frozen: dict[str, str | ResolvedResource] = {}
    for resource_id, resolved in (mapping or {}).items():
        _validate_resource_id(resource_id)
        if isinstance(resolved, ResolvedResource) and resolved.resource_id != resource_id:
            raise ResourceResolverError(
                f"{resource_type} resource_id mismatch: "
                f"mapping key {resource_id!r} does not match "
                f"resolved resource_id {resolved.resource_id!r}"
            )
        if not isinstance(resolved, str | ResolvedResource):
            raise ResourceResolverError(
                f"{resource_type} resolved_value must be a string"
            )
        frozen[resource_id] = resolved
    return MappingProxyType(frozen)
