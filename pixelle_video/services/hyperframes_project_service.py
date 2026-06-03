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
    RenderAudioTrack,
    RenderManifest,
    SentenceUnit,
    TextCue,
    VisualClip,
)
from pixelle_video.models.template_display import (
    TemplateDisplaySettings,
    resolve_template_params_and_display,
)
from pixelle_video.models.template_parameters import validate_template_params
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext
from pixelle_video.models.template_text_capabilities import TemplateTextCapabilities
from pixelle_video.models.text_style import DEFAULT_CAPTION_STYLE_ID, DEFAULT_TITLE_STYLE_ID
from pixelle_video.services.caption_cue_builder import build_caption_cues_from_sentences
from pixelle_video.services.hyperframes_asset_materializer import HyperFramesAssetMaterializer
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler
from pixelle_video.utils.os_util import get_output_path


@dataclass(frozen=True)
class HyperFramesProjectPaths:
    task_dir: Path
    project_dir: Path
    data_dir: Path
    manifest_path: Path
    captions_path: Path
    text_tracks_path: Path


def _build_caption_cues_from_sentences(manifest: RenderManifest) -> list[CaptionCue]:
    return build_caption_cues_from_sentences(
        manifest.sentence_units,
        style_profile=DEFAULT_CAPTION_STYLE_ID,
        punctuation_mode=manifest.caption_punctuation_mode,
    )


def _resolve_caption_cues_for_manifest(manifest: RenderManifest) -> list[CaptionCue]:
    if (
        not manifest.caption_rendering_enabled
        or "hyperframes" not in manifest.caption_renderer_targets
    ):
        return []
    return list(manifest.caption_cues or _build_caption_cues_from_sentences(manifest))


def build_template_render_context(
    manifest: RenderManifest,
    *,
    template_params: dict | None,
    template_display: TemplateDisplaySettings | dict | None = None,
) -> TemplateRenderContext:
    raw_params, display_settings = resolve_template_params_and_display(
        template_params,
        template_display,
        default_display=manifest.template_display,
    )
    validated_params = validate_template_params(raw_params)
    params = display_settings.render_template_params(validated_params)
    caption_cues = _resolve_caption_cues_for_manifest(manifest)
    title_style_profile = next(
        (
            profile
            for profile in manifest.text_style_profiles
            if profile.id == DEFAULT_TITLE_STYLE_ID
        ),
        None,
    )

    duration_candidates = [float(manifest.master_audio_duration or 0.0)]
    duration_candidates.extend(float(track.end) for track in manifest.audio_tracks)
    duration_candidates.extend(float(cue.end) for cue in caption_cues)
    duration_candidates.extend(float(cue.end) for cue in manifest.text_cues)
    duration_candidates.extend(float(clip.end) for clip in manifest.visual_clips)
    duration = max(duration_candidates, default=0.0)

    audio = None
    audio_tracks: list[TemplateAudioRef] = []
    if manifest.audio_tracks:
        audio_tracks = [
            TemplateAudioRef(
                id=track.id,
                path=track.path,
                start=track.start,
                duration=max(float(track.end) - float(track.start), 0.0),
                media_start=track.media_start,
                volume=track.volume,
                track_index=track.track_index,
                role=track.role,
            )
            for track in manifest.audio_tracks
        ]
        audio = next(
            (track for track in audio_tracks if track.role == "narration"),
            audio_tracks[0],
        )
    if manifest.master_audio_path:
        audio = TemplateAudioRef(
            path=manifest.master_audio_path,
            duration=duration,
        )

    return TemplateRenderContext(
        template_id=manifest.template_id,
        canvas_width=manifest.canvas_width,
        canvas_height=manifest.canvas_height,
        media_width=manifest.media_width,
        media_height=manifest.media_height,
        sync_media_size_to_canvas=manifest.sync_media_size_to_canvas,
        media_layout_mode=manifest.media_layout_mode,
        media_placement=manifest.media_placement,
        layered_template_spec=manifest.layered_template_spec,
        duration=duration,
        fps=manifest.fps,
        title=display_settings.render_title(manifest.title),
        author=params.get("author"),
        footer=params.get("footer"),
        theme=params.get("theme"),
        style_profile=params.get("style_profile", manifest.template_id),
        template_params=params,
        visuals=list(manifest.visual_clips),
        captions=caption_cues,
        text_style_profiles=list(manifest.text_style_profiles),
        title_style_profile=title_style_profile,
        text_tracks=list(manifest.text_tracks),
        text_cues=list(manifest.text_cues),
        audio_tracks=audio_tracks,
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
        template_display: TemplateDisplaySettings | dict | None = None,
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
            template_display=template_display,
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
            "text_style_profiles": [
                profile.to_dict() for profile in manifest.text_style_profiles
            ],
            "text_tracks": [track.to_dict() for track in manifest.text_tracks],
            "text_cues": [cue.to_dict() for cue in manifest.text_cues],
        }

    def _resolve_caption_cues(self, manifest: RenderManifest) -> list[CaptionCue]:
        return _resolve_caption_cues_for_manifest(manifest)

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
        for track in manifest.audio_tracks:
            audio_sources[Path(track.path).name] = Path(track.path)

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
            element_manifest_name = self._clip_element_animation_manifest_name(clip)
            localized_element_animation_manifest_path = (
                self._materialize_element_animation_manifest(
                    clip.element_animation_manifest_path,
                    project_dir,
                    manifest_name=element_manifest_name,
                    asset_namespace=Path(element_manifest_name).stem,
                )
            )
            localized_visuals.append(
                replace(
                    clip,
                    media_path=materialized[target_group][source_name],
                    element_animation_manifest_path=localized_element_animation_manifest_path,
                )
            )

        localized_master_audio_path = manifest.master_audio_path
        if manifest.master_audio_path:
            localized_master_audio_path = materialized["audio"][
                Path(manifest.master_audio_path).name
            ]

        localized_audio_tracks: list[RenderAudioTrack] = []
        for track in manifest.audio_tracks:
            source_name = Path(track.path).name
            localized_audio_tracks.append(
                replace(
                    track,
                    path=materialized["audio"][source_name],
                )
            )

        localized_element_animation_manifest_path = self._materialize_element_animation_manifest(
            manifest.element_animation_manifest_path,
            project_dir,
        )

        return replace(
            manifest,
            master_audio_path=localized_master_audio_path,
            audio_tracks=localized_audio_tracks,
            visual_clips=localized_visuals,
            element_animation_manifest_path=localized_element_animation_manifest_path,
        )

    def _materialize_element_animation_manifest(
        self,
        manifest_path: str | None,
        project_dir: Path,
        *,
        manifest_name: str = "element_animation_manifest.json",
        asset_namespace: str | None = None,
    ) -> str | None:
        if not manifest_path:
            return None

        source_manifest_path = Path(manifest_path)
        if not source_manifest_path.exists():
            return None

        payload = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        asset_path_prefix = "assets/element_animation"
        asset_dir = project_dir / asset_path_prefix
        if asset_namespace:
            asset_dir = asset_dir / asset_namespace
            asset_path_prefix = f"{asset_path_prefix}/{asset_namespace}"
        data_dir = project_dir / "data"
        localized_assets: dict[str, str] = {}
        localized_filenames: dict[str, str] = {}

        self._localize_element_animation_asset(
            payload,
            "source_image_path",
            source_manifest_path=source_manifest_path,
            asset_dir=asset_dir,
            asset_path_prefix=asset_path_prefix,
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
                asset_path_prefix=asset_path_prefix,
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
                        asset_path_prefix=asset_path_prefix,
                        localized_assets=localized_assets,
                        localized_filenames=localized_filenames,
                    )

        if manifest_name == "element_animation_manifest.json":
            target_manifest_path = data_dir / manifest_name
            localized_manifest_path = f"data/{manifest_name}"
        else:
            target_manifest_path = data_dir / "element_animation" / manifest_name
            localized_manifest_path = f"data/element_animation/{manifest_name}"
        target_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(target_manifest_path, payload)
        return localized_manifest_path

    def _localize_element_animation_asset(
        self,
        payload: dict,
        key: str,
        *,
        source_manifest_path: Path,
        asset_dir: Path,
        asset_path_prefix: str,
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
        localized_path = f"{asset_path_prefix}/{target_filename}"
        localized_assets[source_key] = localized_path
        payload[key] = localized_path

    def _clip_element_animation_manifest_name(self, clip: VisualClip) -> str:
        clip_id = str(clip.id)
        safe_id = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in clip_id
        ).strip("._")
        if not safe_id:
            safe_id = hashlib.sha256(clip_id.encode("utf-8")).hexdigest()[:10]
        return f"element_animation_{safe_id}.json"

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
        normalized_audio_tracks = self._normalize_audio_tracks(manifest.audio_tracks, duration)
        normalized_audio_blocks = self._normalize_audio_blocks(manifest.audio_blocks, duration)
        valid_block_ids = {block.id for block in normalized_audio_blocks}
        return replace(
            manifest,
            audio_tracks=normalized_audio_tracks,
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
        for track in manifest.audio_tracks:
            candidates.append(float(track.end))
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

    def _normalize_audio_tracks(
        self,
        tracks: list[RenderAudioTrack],
        duration: float,
    ) -> list[RenderAudioTrack]:
        normalized_tracks: list[RenderAudioTrack] = []
        for track in tracks:
            span = self._normalize_time_span(track.start, track.end, duration)
            if span is None:
                continue
            normalized_tracks.append(
                replace(track, start=span[0], end=span[1])
            )
        return normalized_tracks

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
