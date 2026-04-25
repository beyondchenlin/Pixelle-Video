from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import (
    SentenceUnit,
    TextCue,
    TextTrack,
    resolve_render_window,
)
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
)


@dataclass(frozen=True)
class TextCueCompiler:
    default_duration: float = 1.5

    def compile(
        self,
        *,
        package: CreationPackage,
        sentence_units: Sequence[SentenceUnit],
        frame_duration: float | None = None,
        frame_windows: Mapping[int, tuple[float, float]] | None = None,
    ) -> tuple[list[TextTrack], list[TextCue]]:
        plan = package.text_overlay_plan
        if plan is None:
            return [], []

        sentences_by_id = {sentence.id: sentence for sentence in sentence_units}
        tracks: OrderedDict[str, TextTrack] = OrderedDict()
        cues: list[TextCue] = []
        fallback_duration = float(frame_duration or self.default_duration)
        fallback_frame_windows = dict(frame_windows or {})

        for index, candidate in enumerate(plan.candidates, start=1):
            targets = tuple(candidate.renderer_targets or ("hyperframes",))
            primary_target = targets[0]
            track_kind = (
                "native_hint"
                if candidate.role == "model_native_hint"
                else candidate.role
            )
            style_profile = self._style_profile_for_role(candidate.role)
            track_id = f"track-{primary_target}-{track_kind}"
            if track_id not in tracks:
                tracks[track_id] = TextTrack(
                    id=track_id,
                    kind=track_kind,
                    name=track_kind,
                    renderer_targets=targets,
                    style_profile=style_profile,
                    layer=index,
                )
            else:
                track = tracks[track_id]
                if track.style_profile != style_profile:
                    raise ValueError(
                        f"Inconsistent style profile for text track {track_id}"
                    )
                merged_targets = self._merge_renderer_targets(
                    track.renderer_targets,
                    targets,
                )
                if merged_targets != track.renderer_targets:
                    tracks[track_id] = replace(
                        track,
                        renderer_targets=merged_targets,
                    )

            start, end = self._resolve_candidate_window(
                candidate_source=candidate.source,
                sentences_by_id=sentences_by_id,
                frame_windows=fallback_frame_windows,
                frame_duration=fallback_duration,
            )
            cues.append(
                TextCue(
                    id=f"text-cue-{index}",
                    track_id=track_id,
                    text=candidate.text,
                    start=start,
                    end=end,
                    role=candidate.role,
                    frame_indices=(int(candidate.source.get("frame_index", 0)),),
                    slot=candidate.suggested_slot,
                    style_profile=style_profile,
                    layer=index,
                    priority=index,
                    source={
                        "kind": "text_overlay_plan",
                        "candidate_id": candidate.id,
                    },
                )
            )

        return list(tracks.values()), cues

    def _style_profile_for_role(self, role: str) -> str | None:
        if role in {"model_native_hint", "native_hint"}:
            return None
        if role == "subtitle":
            return DEFAULT_CAPTION_STYLE_ID
        return DEFAULT_OVERLAY_STYLE_ID

    def _merge_renderer_targets(
        self,
        existing: tuple[str, ...],
        incoming: tuple[str, ...],
    ) -> tuple[str, ...]:
        merged = list(existing)
        for target in incoming:
            if target not in merged:
                merged.append(target)
        return tuple(merged)

    def _resolve_candidate_window(
        self,
        *,
        candidate_source,
        sentences_by_id: dict[str, SentenceUnit],
        frame_windows: Mapping[int, tuple[float, float]],
        frame_duration: float,
    ) -> tuple[float, float]:
        sentence_id = candidate_source.get("sentence_id")
        if sentence_id and str(sentence_id) in sentences_by_id:
            try:
                start, end = resolve_render_window(sentences_by_id[str(sentence_id)])
                return float(start), max(float(end), float(start) + 0.1)
            except ValueError:
                pass

        frame_index = int(candidate_source.get("frame_index", 0))
        if frame_index in frame_windows:
            start, end = frame_windows[frame_index]
            return float(start), max(float(end), float(start) + 0.1)

        start = frame_index * frame_duration
        return start, start + frame_duration
