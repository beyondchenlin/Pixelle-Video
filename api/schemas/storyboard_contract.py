from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.storyboard_planning import FrameOverrideSource
from pixelle_video.prompt_language import PromptLanguage

StoryboardPromptLanguage = PromptLanguage

StoryboardOverrideField = Literal[
    "source_text",
    "visual_goal",
    "prompt_intent",
    "shot_type",
    "shot_purpose",
    "primary_subject",
    "secondary_subjects",
    "world_elements",
    "continuity_anchors",
    "focus_detail",
    "mandatory_anchor_area_ratio",
    "mandatory_anchor_horizontal_position",
    "mandatory_anchor_depth_position",
    "mandatory_anchor_visible_extent",
    "mandatory_anchor_action_verb",
    "mandatory_anchor_interaction_target",
]


class StoryboardFrameOverride(BaseModel):
    """Structured per-frame storyboard override payload bound to StoryboardPlan identity."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(..., min_length=1, description="Storyboard plan id")
    plan_revision: int = Field(..., ge=1, description="Storyboard plan revision")
    frame_id: str = Field(..., min_length=1, description="Storyboard plan frame id")
    source_digest: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 digest of the plan source text",
    )
    locked_fields: List[StoryboardOverrideField] = Field(
        ...,
        min_length=1,
        description="Editable frame fields that should stay locked on replay",
    )
    override_source: Optional[FrameOverrideSource] = Field(
        None,
        description="Origin of the override payload",
    )
    source_text: Optional[str] = Field(None, description="Locked source text override")
    visual_goal: Optional[str] = Field(None, description="Locked visual goal override")
    prompt_intent: Optional[str] = Field(None, description="Locked prompt intent override")
    shot_type: Optional[str] = Field(None, description="Locked shot type override")
    shot_purpose: Optional[str] = Field(None, description="Locked shot purpose override")
    primary_subject: Optional[str] = Field(None, description="Locked primary subject override")
    secondary_subjects: Optional[List[str]] = Field(None, description="Locked secondary subject overrides")
    world_elements: Optional[List[str]] = Field(None, description="Locked world element overrides")
    continuity_anchors: Optional[List[str]] = Field(None, description="Locked continuity anchor overrides")
    focus_detail: Optional[str] = Field(None, description="Locked focus detail override")
    mandatory_anchor_area_ratio: Optional[float] = Field(
        None,
        gt=0,
        le=1,
        description="Locked mandatory visual-anchor frame-area ratio",
    )
    mandatory_anchor_horizontal_position: Optional[
        Literal["left", "center", "right", "cross_frame"]
    ] = Field(None, description="Locked mandatory visual-anchor horizontal position")
    mandatory_anchor_depth_position: Optional[
        Literal["foreground", "midground", "background", "full_frame"]
    ] = Field(None, description="Locked mandatory visual-anchor depth position")
    mandatory_anchor_visible_extent: Optional[
        Literal[
            "full_body",
            "half_body",
            "partial",
            "distant_silhouette",
            "headshot",
            "recognizable_detail",
        ]
    ] = Field(None, description="Locked mandatory visual-anchor visible extent")
    mandatory_anchor_action_verb: Optional[str] = Field(
        None,
        min_length=1,
        description="Locked mandatory visual-anchor action verb",
    )
    mandatory_anchor_interaction_target: Optional[str] = Field(
        None,
        min_length=1,
        description="Locked mandatory visual-anchor interaction target",
    )

    @model_validator(mode="after")
    def validate_locked_field_values(self) -> "StoryboardFrameOverride":
        provided_fields = [
            field_name
            for field_name in StoryboardOverrideField.__args__
            if getattr(self, field_name) is not None
        ]
        for field_name in provided_fields:
            if field_name not in self.locked_fields:
                raise ValueError(f"{field_name} must be listed in locked_fields")
        return self


class StoryboardPlanPayload(BaseModel):
    """Replayable storyboard plan payload matching StoryboardPlan.to_dict()."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(..., min_length=1, description="Stable storyboard plan id")
    revision: int = Field(..., ge=1, description="Storyboard plan revision")
    mode: str = Field(..., description="Storyboard generation mode")
    count_mode: str = Field(..., description="Storyboard count mode")
    requested_scene_count: Optional[int] = Field(
        None,
        ge=1,
        description="Requested scene count when manual mode is used",
    )
    resolved_scene_count: int = Field(..., ge=1, description="Resolved storyboard frame count")
    source_text: str = Field(..., min_length=1, description="Normalized storyboard source text")
    source_digest: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 digest of the normalized source text",
    )
    frames: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="StoryboardPlan frame payloads",
    )
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Replayable storyboard diagnostics payload",
    )

    @model_validator(mode="after")
    def validate_storyboard_plan_payload(self) -> "StoryboardPlanPayload":
        self._validate_frames()
        self.to_storyboard_plan()
        return self

    def _validate_frames(self) -> None:
        """Validate frame structure before converting to StoryboardPlan to avoid KeyError."""
        required_fields = ["index", "source_text", "visual_goal", "prompt_intent"]
        for i, frame in enumerate(self.frames):
            if not isinstance(frame, dict):
                raise ValueError(f"Frame at index {i} must be a dictionary")
            for field in required_fields:
                if field not in frame:
                    raise ValueError(f"Frame at index {i} is missing required field: {field}")

    def to_storyboard_plan(self) -> StoryboardPlan:
        return StoryboardPlan.from_dict(self.model_dump())

    def source_texts(self) -> list[str]:
        return [str(frame.get("source_text", "")) for frame in self.frames]


__all__ = [
    "StoryboardFrameOverride",
    "StoryboardOverrideField",
    "StoryboardPlanPayload",
    "StoryboardPromptLanguage",
]
