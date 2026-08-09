from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pixelle_video.utils.secret_redaction import is_sensitive_key

DIRECT_MEDIA_SOURCE = "provider"
_PARAMETER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PARAMETER_CONTRACT_KEYS = frozenset({"enum", "type"})
_PARAMETER_TYPES = frozenset({"boolean", "integer", "number", "string"})


class DirectMediaDescriptor(BaseModel):
    """Trusted local descriptor for one provider-backed media workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["provider"]
    adapter: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    provider_id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    media_type: Literal["image", "video"]
    model: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    declared_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model", "display_name")
    @classmethod
    def normalize_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("direct media descriptor text must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_parameters(self):
        if len(self.declared_params) > 32:
            raise ValueError("direct media descriptors may declare at most 32 parameters")
        declared = set(self.declared_params)
        forbidden = {
            name
            for name in declared
            if is_sensitive_key(name)
        }
        if forbidden:
            raise ValueError(
                "direct media descriptors must not expose credential parameters: "
                + ", ".join(sorted(forbidden))
            )
        for name, contract in self.declared_params.items():
            if _PARAMETER_NAME_RE.fullmatch(name) is None:
                raise ValueError(
                    f"direct media parameter name is invalid: {name}"
                )
            unknown_contract_keys = set(contract) - _PARAMETER_CONTRACT_KEYS
            if unknown_contract_keys:
                raise ValueError(
                    f"direct media parameter {name} has unsupported contract fields: "
                    + ", ".join(sorted(unknown_contract_keys))
                )
            expected_type = contract.get("type")
            if expected_type not in _PARAMETER_TYPES:
                raise ValueError(
                    f"direct media parameter {name} has an unsupported type"
                )
            allowed_values = contract.get("enum")
            if allowed_values is not None:
                if not isinstance(allowed_values, list) or not allowed_values:
                    raise ValueError(
                        f"direct media parameter {name} enum must be a non-empty list"
                    )
                if len(allowed_values) > 64:
                    raise ValueError(
                        f"direct media parameter {name} enum may contain at most 64 values"
                    )
                for value in allowed_values:
                    _validate_parameter_value(name, value, contract)
                serialized_values = [
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    for value in allowed_values
                ]
                if len(serialized_values) != len(set(serialized_values)):
                    raise ValueError(
                        f"direct media parameter {name} enum values must be unique"
                    )
        unknown_defaults = set(self.defaults) - declared
        if unknown_defaults:
            raise ValueError(
                "direct media descriptor defaults must be declared parameters: "
                + ", ".join(sorted(unknown_defaults))
            )
        self.normalize_parameters({})
        return self

    @property
    def allowed_parameters(self) -> frozenset[str]:
        return frozenset(self.declared_params)

    def normalize_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(parameters) - self.allowed_parameters
        if unknown:
            raise ValueError(
                "unsupported direct media parameters for workflow "
                f"{self.provider_id}: {', '.join(sorted(unknown))}"
            )
        normalized = dict(self.defaults)
        normalized.update(parameters)
        for name, value in normalized.items():
            _validate_parameter_value(name, value, self.declared_params[name])
        return normalized


def _validate_parameter_value(
    name: str,
    value: Any,
    contract: Mapping[str, Any],
) -> None:
    expected_type = contract["type"]
    if expected_type == "string" and not isinstance(value, str):
        raise ValueError(f"direct media parameter {name} must be a string")
    if expected_type == "integer" and type(value) is not int:
        raise ValueError(f"direct media parameter {name} must be an integer")
    if expected_type == "number" and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"direct media parameter {name} must be finite")
    if expected_type == "boolean" and type(value) is not bool:
        raise ValueError(f"direct media parameter {name} must be a boolean")
    allowed_values = contract.get("enum")
    if isinstance(allowed_values, list) and value not in allowed_values:
        raise ValueError(
            f"direct media parameter {name} must be one of: "
            + ", ".join(str(item) for item in allowed_values)
        )


@dataclass(frozen=True)
class DirectMediaRequest:
    workflow_key: str
    prompt: str
    media_type: Literal["image", "video"]
    model: str
    output_dir: Path
    width: int | None = None
    height: int | None = None
    negative_prompt: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workflow_key.strip():
            raise ValueError("direct media workflow_key must not be blank")
        if not self.prompt.strip():
            raise ValueError("direct media prompt must not be blank")
        if self.media_type not in {"image", "video"}:
            raise ValueError("direct media media_type must be image or video")
        if not self.model.strip():
            raise ValueError("direct media model must not be blank")
        for name, value in (("width", self.width), ("height", self.height)):
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"direct media {name} must be a positive integer")
        if any(not isinstance(name, str) for name in self.parameters):
            raise ValueError("direct media parameter names must be strings")
        object.__setattr__(self, "output_dir", Path(self.output_dir).resolve())
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True)
class DirectMediaOutput:
    media_type: Literal["image", "video"]
    local_path: Path
    provider_id: str
    model: str
    request_id: str = ""
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        resolved_path = Path(self.local_path).resolve()
        if not resolved_path.is_file():
            raise ValueError("direct media output path must be an existing file")
        if self.media_type not in {"image", "video"}:
            raise ValueError("direct media output type must be image or video")
        if not self.provider_id.strip() or not self.model.strip():
            raise ValueError("direct media output provider and model must not be blank")
        object.__setattr__(self, "local_path", resolved_path)
        object.__setattr__(
            self,
            "provider_metadata",
            MappingProxyType(dict(self.provider_metadata)),
        )

    def to_trace_dict(self, *, task_root: str | Path | None = None) -> dict[str, Any]:
        trace_path = self.local_path.name
        if task_root is not None:
            try:
                trace_path = self.local_path.relative_to(Path(task_root).resolve()).as_posix()
            except (OSError, ValueError):
                trace_path = self.local_path.name
        return {
            "media_type": self.media_type,
            "task_relative_path": trace_path,
            "provider_id": self.provider_id,
            "model": self.model,
            "request_id": self.request_id,
            "provider_metadata": dict(self.provider_metadata),
        }


__all__ = [
    "DIRECT_MEDIA_SOURCE",
    "DirectMediaDescriptor",
    "DirectMediaOutput",
    "DirectMediaRequest",
]
