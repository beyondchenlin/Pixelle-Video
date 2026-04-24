"""
HyperFrames project data export helpers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from shutil import copy2

from pixelle_video.models.render_package import (
    AudioBlock,
    CaptionCue,
    RenderManifest,
    SentenceUnit,
    TextCue,
    VisualClip,
    resolve_render_window,
)
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext
from pixelle_video.models.template_text_capabilities import TemplateTextCapabilities
from pixelle_video.services.hyperframes_asset_materializer import HyperFramesAssetMaterializer
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler
from pixelle_video.utils.os_util import get_output_path
from pixelle_video.utils.text_splitting import format_caption_text, split_text_into_subtitle_phrases


@dataclass(frozen=True)
class HyperFramesProjectPaths:
    task_dir: Path
    project_dir: Path
    data_dir: Path
    manifest_path: Path
    captions_path: Path
    text_tracks_path: Path


def _build_caption_cues_from_sentences(manifest: RenderManifest) -> list[CaptionCue]:
    captions: list[CaptionCue] = []
    for sentence in manifest.sentence_units:
        try:
            start, end = resolve_render_window(sentence)
        except ValueError:
            continue

        captions.extend(
            _build_sentence_caption_cues(
                sentence=sentence,
                start=float(start),
                end=float(end),
                style_profile=manifest.template_id,
                punctuation_mode=manifest.caption_punctuation_mode,
            )
        )
    return captions


def _build_sentence_caption_cues(
    *,
    sentence: SentenceUnit,
    start: float,
    end: float,
    style_profile: str,
    punctuation_mode: str,
) -> list[CaptionCue]:
    phrases = split_text_into_subtitle_phrases(sentence.text)
    if not phrases:
        return []

    if len(phrases) == 1 or end <= start:
        return [
            CaptionCue(
                id=sentence.id,
                text=format_caption_text(sentence.text, punctuation_mode=punctuation_mode),
                start=float(start),
                end=float(end),
                frame_indices=list(sentence.frame_indices),
                style_profile=style_profile,
            )
        ]

    weights = [_estimate_caption_phrase_weight(phrase) for phrase in phrases]
    total_weight = sum(weights) or len(phrases)
    span = float(end) - float(start)
    elapsed_weight = 0.0
    captions: list[CaptionCue] = []

    for index, (phrase, weight) in enumerate(zip(phrases, weights), start=1):
        cue_start = float(start) if index == 1 else captions[-1].end
        if index == len(phrases):
            cue_end = float(end)
        else:
            elapsed_weight += weight
            cue_end = float(start) + span * (elapsed_weight / total_weight)

        if cue_end <= cue_start:
            continue

        captions.append(
            CaptionCue(
                id=f"{sentence.id}-cue-{index}",
                text=format_caption_text(phrase, punctuation_mode=punctuation_mode),
                start=cue_start,
                end=cue_end,
                frame_indices=list(sentence.frame_indices),
                style_profile=style_profile,
            )
        )

    if not captions:
        return []

    captions[-1] = replace(captions[-1], end=float(end))
    return captions


def _estimate_caption_phrase_weight(text: str) -> int:
    visible_chars = [char for char in text if not char.isspace()]
    return max(1, len(visible_chars))


def build_template_render_context(
    manifest: RenderManifest,
    *,
    template_params: dict | None,
) -> TemplateRenderContext:
    params = dict(template_params or {})
    caption_cues = list(manifest.caption_cues or _build_caption_cues_from_sentences(manifest))

    duration_candidates = [float(manifest.master_audio_duration or 0.0)]
    duration_candidates.extend(float(cue.end) for cue in caption_cues)
    duration_candidates.extend(float(cue.end) for cue in manifest.text_cues)
    duration_candidates.extend(float(clip.end) for clip in manifest.visual_clips)
    duration = max(duration_candidates, default=0.0)

    audio = None
    if manifest.master_audio_path:
        audio = TemplateAudioRef(
            path=manifest.master_audio_path,
            duration=duration,
        )

    return TemplateRenderContext(
        template_id=manifest.template_id,
        canvas_width=manifest.canvas_width,
        canvas_height=manifest.canvas_height,
        duration=duration,
        fps=manifest.fps,
        title=manifest.title,
        author=params.get("author"),
        footer=params.get("footer"),
        theme=params.get("theme"),
        style_profile=params.get("style_profile", manifest.template_id),
        template_params=params,
        visuals=list(manifest.visual_clips),
        captions=caption_cues,
        text_tracks=list(manifest.text_tracks),
        text_cues=list(manifest.text_cues),
        element_animation_manifest_path=manifest.element_animation_manifest_path,
        audio=audio,
    )


class HyperFramesProjectService:
    """Write task-local HyperFrames project data files."""

    def __init__(
        self,
        output_dir: str | None = None,
        *,
        asset_materializer: HyperFramesAssetMaterializer | None = None,
        compiler: HyperFramesCompiler | None = None,
    ):
        self.output_dir = Path(output_dir) if output_dir is not None else Path(get_output_path())
        self.asset_materializer = asset_materializer or HyperFramesAssetMaterializer()
        self.compiler = compiler or HyperFramesCompiler()

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
        normalized_manifest, effective_caption_cues = self._prepare_manifest_for_export(
            manifest,
            master_audio_duration,
        )
        project_paths = self._build_project_paths(normalized_manifest.task_id)
        self._write_diagnostic_payloads(
            project_paths,
            normalized_manifest,
            effective_caption_cues,
        )
        return project_paths

    def write_project(
        self,
        manifest: RenderManifest,
        *,
        template_params: dict | None = None,
        master_audio_duration: float | None = None,
    ) -> HyperFramesProjectPaths:
        normalized_manifest, _ = self._prepare_manifest_for_export(
            manifest,
            master_audio_duration,
        )
        project_paths = self._build_project_paths(normalized_manifest.task_id)
        localized_manifest = self._materialize_project_assets(
            normalized_manifest,
            project_paths.project_dir,
        )
        localized_cues = self._resolve_caption_cues(localized_manifest)
        localized_manifest = replace(localized_manifest, caption_cues=localized_cues)
        context = build_template_render_context(
            localized_manifest,
            template_params=template_params,
        )

        self.compiler.compile(project_dir=project_paths.project_dir, context=context)
        self._write_diagnostic_payloads(
            project_paths,
            localized_manifest,
            localized_cues,
        )
        return project_paths

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

    def _build_text_tracks_payload(self, manifest: RenderManifest) -> dict:
        return {
            "task_id": manifest.task_id,
            "text_tracks": [track.to_dict() for track in manifest.text_tracks],
            "text_cues": [cue.to_dict() for cue in manifest.text_cues],
        }

    def _resolve_caption_cues(self, manifest: RenderManifest) -> list[CaptionCue]:
        return list(manifest.caption_cues or _build_caption_cues_from_sentences(manifest))

    def _prepare_manifest_for_export(
        self,
        manifest: RenderManifest,
        master_audio_duration: float | None,
    ) -> tuple[RenderManifest, list[CaptionCue]]:
        normalized_manifest = self._normalize_manifest_timeline(manifest, master_audio_duration)
        self._validate_text_capabilities(normalized_manifest)
        effective_caption_cues = self._resolve_caption_cues(normalized_manifest)
        normalized_manifest = replace(
            normalized_manifest,
            caption_cues=effective_caption_cues,
        )
        return normalized_manifest, effective_caption_cues

    def _build_project_paths(self, task_id: str) -> HyperFramesProjectPaths:
        data_dir = self.get_data_dir(task_id)
        data_dir.mkdir(parents=True, exist_ok=True)
        return HyperFramesProjectPaths(
            task_dir=self.get_task_dir(task_id),
            project_dir=self.get_project_dir(task_id),
            data_dir=data_dir,
            manifest_path=data_dir / "render_manifest.json",
            captions_path=data_dir / "captions.json",
            text_tracks_path=data_dir / "text_tracks.json",
        )

    def _write_diagnostic_payloads(
        self,
        project_paths: HyperFramesProjectPaths,
        manifest: RenderManifest,
        caption_cues: list[CaptionCue],
    ) -> None:
        self._write_json(
            project_paths.manifest_path,
            self._build_manifest_payload(manifest, caption_cues),
        )
        self._write_json(
            project_paths.captions_path,
            self._build_captions_payload(manifest, caption_cues),
        )
        self._write_json(
            project_paths.text_tracks_path,
            self._build_text_tracks_payload(manifest),
        )

    def _materialize_project_assets(
        self,
        manifest: RenderManifest,
        project_dir: Path,
    ) -> RenderManifest:
        audio_sources: dict[str, Path] = {}
        if manifest.master_audio_path:
            audio_sources[Path(manifest.master_audio_path).name] = Path(manifest.master_audio_path)

        image_sources: dict[str, Path] = {}
        video_sources: dict[str, Path] = {}
        for clip in manifest.visual_clips:
            source_path = Path(clip.media_path)
            if clip.media_type == "video":
                video_sources[source_path.name] = source_path
            else:
                image_sources[source_path.name] = source_path

        materialized = self.asset_materializer.materialize(
            project_dir=project_dir,
            audio_sources=audio_sources,
            image_sources=image_sources,
            video_sources=video_sources,
        )

        localized_visuals: list[VisualClip] = []
        for clip in manifest.visual_clips:
            source_name = Path(clip.media_path).name
            target_group = "video" if clip.media_type == "video" else "images"
            localized_visuals.append(
                replace(
                    clip,
                    media_path=materialized[target_group][source_name],
                )
            )

        localized_master_audio_path = manifest.master_audio_path
        if manifest.master_audio_path:
            localized_master_audio_path = materialized["audio"][
                Path(manifest.master_audio_path).name
            ]

        localized_element_animation_manifest_path = self._materialize_element_animation_manifest(
            manifest.element_animation_manifest_path,
            project_dir,
        )

        return replace(
            manifest,
            master_audio_path=localized_master_audio_path,
            visual_clips=localized_visuals,
            element_animation_manifest_path=localized_element_animation_manifest_path,
        )

    def _materialize_element_animation_manifest(
        self,
        manifest_path: str | None,
        project_dir: Path,
    ) -> str | None:
        if not manifest_path:
            return None

        source_manifest_path = Path(manifest_path)
        if not source_manifest_path.exists():
            return None

        payload = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        asset_dir = project_dir / "assets" / "element_animation"
        data_dir = project_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        localized_assets: dict[str, str] = {}
        localized_filenames: dict[str, str] = {}

        self._localize_element_animation_asset(
            payload,
            "source_image_path",
            source_manifest_path=source_manifest_path,
            asset_dir=asset_dir,
            localized_assets=localized_assets,
            localized_filenames=localized_filenames,
        )

        background = payload.get("background")
        if isinstance(background, dict):
            self._localize_element_animation_asset(
                background,
                "image_path",
                source_manifest_path=source_manifest_path,
                asset_dir=asset_dir,
                localized_assets=localized_assets,
                localized_filenames=localized_filenames,
            )

        elements = payload.get("elements")
        if isinstance(elements, list):
            for element in elements:
                if not isinstance(element, dict):
                    continue
                for key in ("image_path", "mask_path"):
                    self._localize_element_animation_asset(
                        element,
                        key,
                        source_manifest_path=source_manifest_path,
                        asset_dir=asset_dir,
                        localized_assets=localized_assets,
                        localized_filenames=localized_filenames,
                    )

        target_manifest_path = data_dir / "element_animation_manifest.json"
        self._write_json(target_manifest_path, payload)
        return "data/element_animation_manifest.json"

    def _localize_element_animation_asset(
        self,
        payload: dict,
        key: str,
        *,
        source_manifest_path: Path,
        asset_dir: Path,
        localized_assets: dict[str, str],
        localized_filenames: dict[str, str],
    ) -> None:
        value = payload.get(key)
        if not value:
            return

        source_path = Path(str(value))
        if not source_path.is_absolute():
            source_path = source_manifest_path.parent / source_path
        if not source_path.exists():
            return

        source_key = str(source_path.resolve())
        localized_path = localized_assets.get(source_key)
        if localized_path is not None:
            payload[key] = localized_path
            return

        asset_dir.mkdir(parents=True, exist_ok=True)
        target_filename = self._resolve_element_animation_asset_filename(
            source_path,
            source_key=source_key,
            localized_filenames=localized_filenames,
        )
        target_path = asset_dir / target_filename
        copy2(source_path, target_path)
        localized_path = f"assets/element_animation/{target_filename}"
        localized_assets[source_key] = localized_path
        payload[key] = localized_path

    def _resolve_element_animation_asset_filename(
        self,
        source_path: Path,
        *,
        source_key: str,
        localized_filenames: dict[str, str],
    ) -> str:
        source_name = source_path.name
        source_name_key = source_name.casefold()
        existing_source_key = localized_filenames.get(source_name_key)
        if existing_source_key is None or existing_source_key == source_key:
            localized_filenames[source_name_key] = source_key
            return source_name

        path_hash = hashlib.sha256(source_key.encode("utf-8")).hexdigest()
        for length in (10, 16, 32, 64):
            candidate = f"{source_path.stem}_{path_hash[:length]}{source_path.suffix}"
            candidate_key = candidate.casefold()
            existing_source_key = localized_filenames.get(candidate_key)
            if existing_source_key is None or existing_source_key == source_key:
                localized_filenames[candidate_key] = source_key
                return candidate

        raise ValueError(f"could not create unique filename for {source_path}")

    def _normalize_manifest_timeline(
        self,
        manifest: RenderManifest,
        master_audio_duration: float | None,
    ) -> RenderManifest:
        duration = self._resolve_master_audio_duration(manifest, master_audio_duration)
        normalized_audio_blocks = self._normalize_audio_blocks(manifest.audio_blocks, duration)
        valid_block_ids = {block.id for block in normalized_audio_blocks}
        return replace(
            manifest,
            audio_blocks=normalized_audio_blocks,
            sentence_units=self._normalize_sentence_units(
                manifest.sentence_units,
                duration,
                valid_block_ids=valid_block_ids,
            ),
            visual_clips=self._normalize_visual_clips(manifest.visual_clips, duration),
            caption_cues=self._normalize_caption_cues(manifest.caption_cues, duration),
            text_cues=self._normalize_text_cues(manifest.text_cues, duration),
        )

    def _resolve_master_audio_duration(
        self,
        manifest: RenderManifest,
        master_audio_duration: float | None,
    ) -> float:
        if master_audio_duration is not None:
            return max(0.0, float(master_audio_duration))
        if manifest.master_audio_duration is not None:
            return max(0.0, float(manifest.master_audio_duration))

        candidates = [0.0]
        for block in manifest.audio_blocks:
            candidates.append(float(block.end or 0.0))
        for sentence in manifest.sentence_units:
            for value in (sentence.source_end, sentence.remapped_end):
                if value is not None:
                    candidates.append(float(value))
        for cue in manifest.caption_cues:
            candidates.append(float(cue.end))
        for cue in manifest.text_cues:
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
        *,
        valid_block_ids: set[str] | None = None,
    ) -> list[SentenceUnit]:
        normalized_sentences: list[SentenceUnit] = []
        for sentence in sentence_units:
            source_span = self._normalize_time_span(sentence.source_start, sentence.source_end, duration)
            remapped_span = self._normalize_time_span(sentence.remapped_start, sentence.remapped_end, duration)
            has_remapped_span = sentence.remapped_start is not None or sentence.remapped_end is not None
            if source_span is None and remapped_span is None and not has_remapped_span:
                continue

            if has_remapped_span and remapped_span is None:
                source_span = None

            normalized_sentences.append(
                replace(
                    sentence,
                    source_start=source_span[0] if source_span else None,
                    source_end=source_span[1] if source_span else None,
                    remapped_start=remapped_span[0] if remapped_span else None,
                    remapped_end=remapped_span[1] if remapped_span else None,
                    block_id=(
                        sentence.block_id
                        if valid_block_ids is None or sentence.block_id in valid_block_ids
                        else None
                    ),
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

    def _normalize_text_cues(self, text_cues: list[TextCue], duration: float) -> list[TextCue]:
        normalized_cues: list[TextCue] = []
        for cue in text_cues:
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

    def _load_text_capabilities(
        self,
        template_id: str,
    ) -> TemplateTextCapabilities | None:
        path = self.compiler.template_root / template_id / "text_capabilities.json"
        if not path.exists():
            return None
        return TemplateTextCapabilities.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def _validate_text_capabilities(self, manifest: RenderManifest) -> None:
        tracks = {track.id: track for track in manifest.text_tracks if track.enabled}
        hyperframes_cues = [
            cue
            for cue in manifest.text_cues
            if tracks.get(cue.track_id) is not None
            and "hyperframes" in tracks[cue.track_id].renderer_targets
        ]
        if not hyperframes_cues:
            return

        capabilities = self._load_text_capabilities(manifest.template_id)
        if capabilities is None:
            raise ValueError(
                f"template {manifest.template_id} has no text capabilities"
            )

        for cue in hyperframes_cues:
            track = tracks[cue.track_id]
            capabilities.validate(
                slot=cue.slot,
                role=cue.role,
                style_profile=cue.style_profile or track.style_profile,
                layer=cue.layer,
            )

    def _write_json(self, path: Path, payload: dict) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
