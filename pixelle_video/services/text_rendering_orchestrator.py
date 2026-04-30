from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pixelle_video.models.text_layout import TextLayoutPlan
from pixelle_video.models.text_overlay import (
    ImageTextPromptPolicy,
    TextOverlayPlan,
    TextRenderingPolicy,
    TextRenderingSettings,
    build_text_rendering_policy,
    build_text_rendering_settings,
)
from pixelle_video.models.text_render_package import (
    CaptionRenderingSettings,
    TextRenderPackage,
)
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
)
from pixelle_video.services.text_overlay_planner import TextOverlayPlanner

_PROGRAMMATIC_TARGETS = {"hyperframes", "html", "ass", "python"}
_PREVIEW_TASK_ID = "text-rendering-preview"


@dataclass(frozen=True)
class TextRenderingBuildResult:
    settings: TextRenderingSettings
    text_render_package: TextRenderPackage
    caption_settings: CaptionRenderingSettings
    overlay_policy: TextRenderingPolicy
    overlay_plan: TextOverlayPlan
    text_style_profiles: tuple[TextStyleProfile, ...]
    caption_style: TextStyleProfile
    overlay_style: TextStyleProfile
    image_text_policy: ImageTextPromptPolicy
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def package(self) -> TextRenderPackage:
        return self.text_render_package


class TextRenderingOrchestrator:
    def __init__(self, overlay_planner: TextOverlayPlanner | None = None) -> None:
        self.overlay_planner = overlay_planner or TextOverlayPlanner()

    def build(
        self,
        *,
        text_rendering: Mapping[str, Any] | None,
        narrations: Sequence[str] = (),
        render_backend: str | None = None,
        frame_count: int | None = None,
        task_id: str | None = None,
        config: Any | None = None,
        canvas_width: int | None = None,
        canvas_height: int | None = None,
    ) -> TextRenderingBuildResult:
        request = dict(text_rendering or {})
        settings = build_text_rendering_settings(request)
        overlay_policy = build_text_rendering_policy(settings.overlay)

        caption_style = _profile_from_request(
            style_id=DEFAULT_CAPTION_STYLE_ID,
            data=_mapping_or_none(request.get("caption_style")),
            config=config,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        overlay_style = _profile_from_request(
            style_id=DEFAULT_OVERLAY_STYLE_ID,
            data=_mapping_or_none(request.get("overlay_style")),
            config=config,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        caption_settings = _caption_settings_from_request(
            request.get("caption"), caption_style_id=caption_style.id
        )
        overlay_plan = self._build_overlay_plan(
            narrations=narrations,
            settings=settings,
            policy=overlay_policy,
        )
        effective_task_id = str(task_id or "").strip() or _PREVIEW_TASK_ID
        text_style_profiles = (caption_style, overlay_style)
        diagnostics = _diagnostics(
            task_id=effective_task_id,
            render_backend=render_backend,
            frame_count=frame_count,
            overlay_plan=overlay_plan,
            settings=settings,
            policy=overlay_policy,
        )

        package = TextRenderPackage(
            task_id=effective_task_id,
            caption_settings=caption_settings,
            text_style_profiles=text_style_profiles,
            layout_plan=TextLayoutPlan(),
            diagnostics=diagnostics,
        )

        return TextRenderingBuildResult(
            settings=settings,
            text_render_package=package,
            caption_settings=caption_settings,
            overlay_policy=overlay_policy,
            overlay_plan=overlay_plan,
            text_style_profiles=text_style_profiles,
            caption_style=caption_style,
            overlay_style=overlay_style,
            image_text_policy=settings.image_text,
            diagnostics=package.diagnostics,
        )

    def _build_overlay_plan(
        self,
        *,
        narrations: Sequence[str],
        settings: TextRenderingSettings,
        policy: TextRenderingPolicy,
    ) -> TextOverlayPlan:
        if not settings.overlay.enabled:
            return TextOverlayPlan()
        if not _has_programmatic_target(policy):
            return TextOverlayPlan()
        return self.overlay_planner.plan(narrations=narrations, policy=policy)


def _profile_from_request(
    *,
    style_id: str,
    data: Mapping[str, Any] | None,
    config: Any | None = None,
    canvas_width: int | None = None,
    canvas_height: int | None = None,
) -> TextStyleProfile:
    defaults = {
        profile.id: profile.to_dict()
        for profile in build_default_text_style_profiles(
            config=config,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
    }
    payload = dict(defaults[style_id])
    if data:
        payload.update(dict(data))
    payload["id"] = style_id
    return TextStyleProfile.from_dict(payload)


def _caption_settings_from_request(
    value: Any, *, caption_style_id: str
) -> CaptionRenderingSettings:
    payload = dict(value or {}) if isinstance(value, Mapping) else {}
    payload["style_profile"] = caption_style_id
    return CaptionRenderingSettings.from_dict(payload)


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _has_programmatic_target(policy: TextRenderingPolicy) -> bool:
    return any(target in _PROGRAMMATIC_TARGETS for target in policy.enabled_targets)


def _diagnostics(
    *,
    task_id: str,
    render_backend: str | None,
    frame_count: int | None,
    overlay_plan: TextOverlayPlan,
    settings: TextRenderingSettings,
    policy: TextRenderingPolicy,
) -> dict[str, Any]:
    disabled_reasons: list[str] = []
    if not settings.overlay.enabled:
        disabled_reasons.append("overlay_disabled")
    elif not _has_programmatic_target(policy):
        disabled_reasons.append("overlay_has_no_programmatic_target")

    return {
        "task_id": task_id,
        "render_backend": render_backend,
        "frame_count": frame_count,
        "disabled_reasons": disabled_reasons,
        "overlay_plan": {
            "candidate_count": len(overlay_plan.candidates),
            "planned": bool(overlay_plan.candidates),
        },
    }
