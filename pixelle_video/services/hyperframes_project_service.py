"""
HyperFrames project data export helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pixelle_video.models.render_package import CaptionCue, RenderManifest
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

    def write_project_data(self, manifest: RenderManifest) -> HyperFramesProjectPaths:
        data_dir = self.get_data_dir(manifest.task_id)
        data_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = data_dir / "render_manifest.json"
        captions_path = data_dir / "captions.json"
        effective_caption_cues = self._resolve_caption_cues(manifest)

        self._write_json(
            manifest_path,
            self._build_manifest_payload(manifest, effective_caption_cues),
        )
        self._write_json(
            captions_path,
            self._build_captions_payload(manifest, effective_caption_cues),
        )

        return HyperFramesProjectPaths(
            task_dir=self.get_task_dir(manifest.task_id),
            project_dir=self.get_project_dir(manifest.task_id),
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
