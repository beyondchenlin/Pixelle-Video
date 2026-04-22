"""Helpers for auto-editor timeline export and sentence time remapping."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from pixelle_video.models.render_package import SentenceUnit

DEFAULT_AUTO_EDITOR_EXPORT = "timeline:api=1"
DEFAULT_AUTO_EDITOR_EXECUTABLE = "auto-editor"


def resolve_auto_editor_executable(
    *,
    repo_root: Path | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> str:
    resolved_from_path = which_fn(DEFAULT_AUTO_EDITOR_EXECUTABLE)
    if resolved_from_path:
        return resolved_from_path

    project_root = repo_root or Path(__file__).resolve().parents[2]
    candidate_paths = [
        project_root / ".venv" / "Scripts" / "auto-editor.exe",
        project_root / ".venv" / "bin" / "auto-editor",
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate)

    return DEFAULT_AUTO_EDITOR_EXECUTABLE


class AutoEditorRunner(Protocol):
    def export_timeline(self, audio_path: str, margin_ms: int | None = None) -> str:
        ...

    def export_trimmed_audio(
        self,
        audio_path: str,
        output_path: str,
        margin_ms: int | None = None,
    ) -> str:
        ...


@dataclass
class AutoEditorTimeline:
    chunks: list[list[float]] = field(default_factory=list)
    timebase: float = 1.0
    version: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if self.timebase is None:
            self.timebase = 1.0
        else:
            self.timebase = float(self.timebase)
        if self.timebase <= 0:
            raise ValueError("Auto-editor timeline timebase must be positive.")
        self.chunks = [self._coerce_chunk(chunk) for chunk in self.chunks]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AutoEditorTimeline":
        return cls(
            version=str(data.get("version")) if data.get("version") is not None else None,
            source=str(data.get("source")) if data.get("source") is not None else None,
            timebase=data.get("timebase", 1.0),
            chunks=[cls._coerce_chunk(chunk) for chunk in data.get("chunks", [])],
        )

    @classmethod
    def from_json(cls, payload: str) -> "AutoEditorTimeline":
        data = json.loads(payload)
        if not isinstance(data, Mapping):
            raise ValueError("Auto-editor timeline JSON must decode to an object.")
        return cls.from_mapping(data)

    @staticmethod
    def _coerce_chunk(chunk: Any) -> list[float]:
        if isinstance(chunk, Mapping):
            start = chunk.get("start")
            end = chunk.get("end")
            speed = chunk.get("speed", 1.0)
            return [float(start), float(end), float(speed)]

        if not isinstance(chunk, Sequence) or len(chunk) < 3:
            raise ValueError("Auto-editor chunks must contain start, end, and speed values.")

        start, end, speed = chunk[:3]
        return [float(start), float(end), float(speed)]

    def remap_time(self, source_time: float | None) -> float | None:
        if source_time is None:
            return None
        if not self.chunks:
            return float(source_time)
        if self.timebase <= 0:
            raise ValueError("Auto-editor timeline timebase must be positive.")

        source_units = float(source_time) * self.timebase
        remapped_units = 0.0
        last_end = 0.0
        last_speed = 1.0

        for start, end, speed in self.chunks:
            if source_units < start:
                if last_speed > 0:
                    remapped_units += max(0.0, source_units - last_end) / last_speed
                return remapped_units / self.timebase

            if source_units <= end:
                if speed <= 0:
                    return remapped_units / self.timebase
                remapped_units += (source_units - start) / speed
                return remapped_units / self.timebase

            if speed > 0:
                remapped_units += (end - start) / speed
            last_end = end
            last_speed = speed

        if last_speed > 0 and source_units > last_end:
            remapped_units += (source_units - last_end) / last_speed
        return remapped_units / self.timebase

    def remap_sentence(self, sentence: SentenceUnit) -> SentenceUnit:
        remapped_start = self.remap_time(getattr(sentence, "source_start", None))
        remapped_end = self.remap_time(getattr(sentence, "source_end", None))
        setattr(sentence, "remapped_start", remapped_start)
        setattr(sentence, "remapped_end", remapped_end)
        return sentence


@dataclass(frozen=True)
class AutoEditorTrimResult:
    trimmed_audio_path: str
    timeline: AutoEditorTimeline


class _SubprocessAutoEditorRunner:
    def __init__(
        self,
        executable: str | None = None,
        export_mode: str = DEFAULT_AUTO_EDITOR_EXPORT,
    ):
        self.executable = executable or resolve_auto_editor_executable()
        self.export_mode = export_mode

    def export_timeline(self, audio_path: str, margin_ms: int | None = None) -> str:
        output_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
                output_path = handle.name

            command = [
                self.executable,
                audio_path,
                *self._build_margin_args(margin_ms),
                "--export",
                self.export_mode,
                "-o",
                output_path,
            ]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "auto-editor timeline export failed: "
                    f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown error'}"
                )

            with open(output_path, "r", encoding="utf-8") as handle:
                return handle.read()
        finally:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass

    def export_trimmed_audio(
        self,
        audio_path: str,
        output_path: str,
        margin_ms: int | None = None,
    ) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                self.executable,
                audio_path,
                *self._build_margin_args(margin_ms),
                "-o",
                output_path,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "auto-editor audio export failed: "
                f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown error'}"
            )
        return output_path

    def _build_margin_args(self, margin_ms: int | None) -> list[str]:
        if margin_ms is None:
            return []

        seconds = max(0.0, float(margin_ms) / 1000.0)
        seconds_str = f"{seconds:.3f}".rstrip("0").rstrip(".")
        if not seconds_str:
            seconds_str = "0"
        return ["--margin", f"{seconds_str}sec"]


class AudioEditService:
    def __init__(self, runner: AutoEditorRunner | None = None):
        self.runner = runner or _SubprocessAutoEditorRunner()

    def export_timeline(self, audio_path: str, margin_ms: int | None = None) -> str:
        return self.runner.export_timeline(audio_path, margin_ms=margin_ms)

    def parse_timeline(self, payload: str | Mapping[str, Any]) -> AutoEditorTimeline:
        if isinstance(payload, str):
            return AutoEditorTimeline.from_json(payload)
        return AutoEditorTimeline.from_mapping(payload)

    def remap_sentence_units(
        self,
        sentence_units: Sequence[SentenceUnit],
        timeline: AutoEditorTimeline | Mapping[str, Any] | str,
    ) -> list[SentenceUnit]:
        auto_editor_timeline = self._ensure_timeline(timeline)
        return [auto_editor_timeline.remap_sentence(sentence) for sentence in sentence_units]

    def export_trimmed_audio_and_timeline(
        self,
        audio_path: str,
        output_path: str,
        margin_ms: int | None = None,
    ) -> AutoEditorTrimResult:
        trimmed_audio_path = self.runner.export_trimmed_audio(
            audio_path,
            output_path,
            margin_ms=margin_ms,
        )
        timeline = self.parse_timeline(self.export_timeline(audio_path, margin_ms=margin_ms))
        return AutoEditorTrimResult(
            trimmed_audio_path=trimmed_audio_path,
            timeline=timeline,
        )

    def remap_sentence_units_from_audio(
        self,
        audio_path: str,
        sentence_units: Sequence[SentenceUnit],
        margin_ms: int | None = None,
    ) -> list[SentenceUnit]:
        payload = self.export_timeline(audio_path, margin_ms=margin_ms)
        timeline = self.parse_timeline(payload)
        return self.remap_sentence_units(sentence_units, timeline)

    def _ensure_timeline(
        self,
        timeline: AutoEditorTimeline | Mapping[str, Any] | str,
    ) -> AutoEditorTimeline:
        if isinstance(timeline, AutoEditorTimeline):
            return timeline
        return self.parse_timeline(timeline)
