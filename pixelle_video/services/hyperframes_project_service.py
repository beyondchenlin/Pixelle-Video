"""
HyperFrames project data export helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from pixelle_video.models.render_package import AudioBlock, CaptionCue, RenderManifest, SentenceUnit, VisualClip
from pixelle_video.utils.os_util import get_output_path


@dataclass(frozen=True)
class HyperFramesProjectPaths:
    task_dir: Path
    project_dir: Path
    data_dir: Path
    manifest_path: Path
    captions_path: Path


class HyperFramesProjectService:
    """Write task-local HyperFrames project data files."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir) if output_dir is not None else Path(get_output_path())

    def get_task_dir(self, task_id: str) -> Path:
        return self.output_dir / task_id

    def get_project_dir(self, task_id: str) -> Path:
        return self.get_task_dir(task_id) / "hyperframes"

    def get_data_dir(self, task_id: str) -> Path:
        return self.get_project_dir(task_id) / "data"

    def write_project_data(
        self,
        manifest: RenderManifest,
        master_audio_duration: float | None = None,
    ) -> HyperFramesProjectPaths:
        normalized_manifest = self._normalize_manifest_timeline(manifest, master_audio_duration)
        data_dir = self.get_data_dir(normalized_manifest.task_id)
        data_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = data_dir / "render_manifest.json"
        captions_path = data_dir / "captions.json"
        effective_caption_cues = self._resolve_caption_cues(normalized_manifest)

        self._write_json(
            manifest_path,
            self._build_manifest_payload(normalized_manifest, effective_caption_cues),
        )
        self._write_json(
            captions_path,
            self._build_captions_payload(normalized_manifest, effective_caption_cues),
        )

        return HyperFramesProjectPaths(
            task_dir=self.get_task_dir(normalized_manifest.task_id),
            project_dir=self.get_project_dir(normalized_manifest.task_id),
            data_dir=data_dir,
            manifest_path=manifest_path,
            captions_path=captions_path,
        )

    def _build_manifest_payload(
        self,
        manifest: RenderManifest,
        caption_cues: list[CaptionCue],
    ) -> dict:
        payload = manifest.to_dict()
        payload["caption_cues"] = [cue.to_dict() for cue in caption_cues]
        return payload

    def _build_captions_payload(
        self,
        manifest: RenderManifest,
        caption_cues: list[CaptionCue],
    ) -> dict:
        return {
            "task_id": manifest.task_id,
            "template_id": manifest.template_id,
            "captions": [cue.to_dict() for cue in caption_cues],
        }

    def _resolve_caption_cues(self, manifest: RenderManifest) -> list[CaptionCue]:
        return list(manifest.caption_cues or self._build_caption_cues_from_sentences(manifest))

    def _normalize_manifest_timeline(
        self,
        manifest: RenderManifest,
        master_audio_duration: float | None,
    ) -> RenderManifest:
        duration = self._resolve_master_audio_duration(manifest, master_audio_duration)
        return replace(
            manifest,
            audio_blocks=self._normalize_audio_blocks(manifest.audio_blocks, duration),
            sentence_units=self._normalize_sentence_units(manifest.sentence_units, duration),
            visual_clips=self._normalize_visual_clips(manifest.visual_clips, duration),
            caption_cues=self._normalize_caption_cues(manifest.caption_cues, duration),
        )

    def _resolve_master_audio_duration(
        self,
        manifest: RenderManifest,
        master_audio_duration: float | None,
    ) -> float:
        if master_audio_duration is not None:
            return max(0.0, float(master_audio_duration))

        candidates = [0.0]
        for block in manifest.audio_blocks:
            candidates.append(float(block.end or 0.0))
        for sentence in manifest.sentence_units:
            for value in (sentence.source_end, sentence.remapped_end):
                if value is not None:
                    candidates.append(float(value))
        for cue in manifest.caption_cues:
            candidates.append(float(cue.end))
        for clip in manifest.visual_clips:
            candidates.append(float(clip.end))
        return max(candidates)

    def _normalize_audio_blocks(self, blocks: list[AudioBlock], duration: float) -> list[AudioBlock]:
        normalized_blocks: list[AudioBlock] = []
        for block in blocks:
            span = self._normalize_time_span(block.start, block.end, duration)
            if span is None:
                continue
            normalized_blocks.append(
                replace(block, start=span[0], end=span[1])
            )
        return normalized_blocks

    def _normalize_sentence_units(
        self,
        sentence_units: list[SentenceUnit],
        duration: float,
    ) -> list[SentenceUnit]:
        normalized_sentences: list[SentenceUnit] = []
        for sentence in sentence_units:
            source_span = self._normalize_time_span(sentence.source_start, sentence.source_end, duration)
            remapped_span = self._normalize_time_span(sentence.remapped_start, sentence.remapped_end, duration)
            if source_span is None and remapped_span is None:
                continue

            normalized_sentences.append(
                replace(
                    sentence,
                    source_start=source_span[0] if source_span else None,
                    source_end=source_span[1] if source_span else None,
                    remapped_start=remapped_span[0] if remapped_span else None,
                    remapped_end=remapped_span[1] if remapped_span else None,
                )
            )
        return normalized_sentences

    def _normalize_caption_cues(self, caption_cues: list[CaptionCue], duration: float) -> list[CaptionCue]:
        normalized_cues: list[CaptionCue] = []
        for cue in caption_cues:
            span = self._normalize_time_span(cue.start, cue.end, duration)
            if span is None:
                continue
            normalized_cues.append(replace(cue, start=span[0], end=span[1]))
        return normalized_cues

    def _normalize_visual_clips(self, visual_clips: list[VisualClip], duration: float) -> list[VisualClip]:
        normalized_clips: list[VisualClip] = []
        for clip in visual_clips:
            if not clip.media_path:
                continue
            span = self._normalize_time_span(clip.start, clip.end, duration)
            if span is None:
                continue
            normalized_clips.append(replace(clip, start=span[0], end=span[1]))
        return normalized_clips

    def _normalize_time_span(
        self,
        start: float | None,
        end: float | None,
        duration: float,
    ) -> tuple[float, float] | None:
        if start is None or end is None:
            return None

        clamped_start = self._clamp_time(start, duration)
        clamped_end = self._clamp_time(end, duration)
        if clamped_end <= clamped_start:
            return None
        return clamped_start, clamped_end

    @staticmethod
    def _clamp_time(value: float, duration: float) -> float:
        return max(0.0, min(float(value), max(0.0, float(duration))))

    def _build_caption_cues_from_sentences(self, manifest: RenderManifest) -> list[CaptionCue]:
        captions: list[CaptionCue] = []
        for sentence in manifest.sentence_units:
            start = (
                sentence.remapped_start
                if sentence.remapped_start is not None
                else sentence.source_start
            )
            end = (
                sentence.remapped_end
                if sentence.remapped_end is not None
                else sentence.source_end
            )
            if start is None or end is None:
                continue

            captions.append(
                CaptionCue(
                    id=sentence.id,
                    text=sentence.text,
                    start=float(start),
                    end=float(end),
                    frame_indices=list(sentence.frame_indices),
                    style_profile=manifest.template_id,
                )
            )
        return captions

    def _write_json(self, path: Path, payload: dict) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
