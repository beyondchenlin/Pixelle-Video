from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from pixelle_video.models.render_package import TextCue, TextTrack
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
)

_CAPTION_ROLES = {"caption", "subtitle"}
_OVERLAY_ROLES = {"overlay", "keyword"}


@dataclass
class TextStyleResolver:
    profiles: Iterable[TextStyleProfile] = ()
    strict: bool = False
    diagnostics: dict = field(default_factory=lambda: {"fallbacks": []})

    def __post_init__(self) -> None:
        merged = {profile.id: profile for profile in build_default_text_style_profiles()}
        merged.update({profile.id: profile for profile in self.profiles})
        self.profiles_by_id = merged

    def resolve_for_cue(
        self, *, cue: TextCue, track: TextTrack | None = None
    ) -> TextStyleProfile:
        requested_style_ids = (
            self._clean_style_id(cue.style_profile),
            self._clean_style_id(track.style_profile if track is not None else None),
        )
        missing_style_ids: list[str] = []

        for style_id in requested_style_ids:
            if style_id is None:
                continue
            profile = self.profiles_by_id.get(style_id)
            if profile is not None:
                if missing_style_ids:
                    self._record_fallback(
                        cue_id=cue.id,
                        missing_style_ids=missing_style_ids,
                        resolved_style_id=profile.id,
                    )
                return profile
            missing_style_ids.append(style_id)

        default_style_id = self._default_style_id(cue=cue, track=track)
        profile = self.profiles_by_id.get(default_style_id)
        if profile is not None:
            if missing_style_ids:
                self._record_fallback(
                    cue_id=cue.id,
                    missing_style_ids=missing_style_ids,
                    resolved_style_id=profile.id,
                )
            return profile

        if self.strict:
            raise ValueError(
                f"No usable text style profile resolved for cue {cue.id}: "
                f"missing default {default_style_id}"
            )

        fallback = next(iter(self.profiles_by_id.values()), None)
        if fallback is None:
            raise ValueError(f"No usable text style profile resolved for cue {cue.id}")
        self._record_fallback(
            cue_id=cue.id,
            missing_style_ids=missing_style_ids or [default_style_id],
            resolved_style_id=fallback.id,
        )
        return fallback

    def _default_style_id(self, *, cue: TextCue, track: TextTrack | None) -> str:
        role = str(cue.role or "").strip().lower()
        track_kind = str(track.kind if track is not None else "").strip().lower()
        if role in _CAPTION_ROLES or track_kind in _CAPTION_ROLES:
            return DEFAULT_CAPTION_STYLE_ID
        if role in _OVERLAY_ROLES or track_kind == "overlay":
            return DEFAULT_OVERLAY_STYLE_ID
        return DEFAULT_CAPTION_STYLE_ID

    def _record_fallback(
        self, *, cue_id: str, missing_style_ids: list[str], resolved_style_id: str
    ) -> None:
        fallback = {
            "cue_id": cue_id,
            "missing_style_id": missing_style_ids[0],
            "resolved_style_id": resolved_style_id,
        }
        if len(missing_style_ids) > 1:
            fallback["missing_style_ids"] = list(missing_style_ids)
        self.diagnostics.setdefault("fallbacks", []).append(fallback)

    def _clean_style_id(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None
