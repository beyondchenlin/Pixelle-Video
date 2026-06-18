from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

REFERENCE_IMAGE_INJECTION_SUMMARY_VERSION = "reference_image_injection_summary/v1"

ReferenceImageWorkflowInjectionStatus = Literal[
    "off",
    "prompt_only",
    "workflow_injected",
    "required_failed",
    "unknown",
]


class ReferenceImageInjectionSummary(BaseModel):
    """User-facing summary of reference-image analysis and workflow injection."""

    version: str = REFERENCE_IMAGE_INJECTION_SUMMARY_VERSION
    analysis_status: str = "unknown"
    workflow_injection_status: ReferenceImageWorkflowInjectionStatus = "unknown"
    workflow_key: str = ""
    workflow_source: str = ""
    injection_mode: Literal["off", "auto", "required", ""] = ""
    param_name: str | None = None
    reason: str = ""
    artifact_relative_path: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
