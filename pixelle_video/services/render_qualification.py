from __future__ import annotations

import json
import os
import statistics
import threading
import time
import wave
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Iterator

import psutil
from PIL import Image, ImageDraw

from pixelle_video.models.media_placement import (
    MediaPlacement,
    calculate_media_box,
)
from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import (
    RenderAudioTrack,
    RenderManifest,
    TextCue,
    TextTrack,
    VisualClip,
)
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.ass_text_adapter import AssTextAdapter
from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService
from pixelle_video.services.hyperframes_renderer import HyperFramesRenderer
from pixelle_video.services.media_geometry_resolver import MediaGeometryResolver
from pixelle_video.services.render_artifact_analyzer import (
    PixelBox,
    RenderArtifactAnalyzer,
)
from pixelle_video.services.render_output_probe import RenderOutputProbe
from pixelle_video.services.render_snapshot import RenderSnapshotService
from pixelle_video.services.video_encoder_executor import reset_runtime_encoder_failures
from pixelle_video.utils.ffmpeg_encoder import (
    available_h264_backends,
    clear_ffmpeg_encoder_probe_cache,
    get_h264_backend,
)
from pixelle_video.utils.path_safety import (
    resolve_path_within,
    resolve_task_dir,
    validate_task_id,
)

GOLDEN_TEMPLATE_ID = "render_contract_golden"
GOLDEN_TEXT = "BASELINEBASELINE"
GOLDEN_SAMPLE_TIME = 0.6
GOLDEN_DURATION = 1.2
GOLDEN_SOURCE_WIDTH = 200
GOLDEN_SOURCE_HEIGHT = 300


@dataclass(frozen=True)
class QualificationCase:
    name: str
    width: int
    height: int
    fit: str
    duration: float = GOLDEN_DURATION


@dataclass(frozen=True)
class RenderMeasurement:
    elapsed_seconds: float
    peak_rss_bytes: int
    output_path: str


class _PeakMemorySampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._peak = 0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _PeakMemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._sample()

    @property
    def peak_rss_bytes(self) -> int:
        return self._peak

    def _run(self) -> None:
        while not self._stop.wait(0.02):
            self._sample()

    def _sample(self) -> None:
        process = psutil.Process()
        rss = 0
        for candidate in (process, *process.children(recursive=True)):
            try:
                rss += candidate.memory_info().rss
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        self._peak = max(self._peak, rss)


class RenderQualificationSuite:
    """Run reproducible final-artifact qualification against both renderers."""

    ORIENTATIONS = {
        "landscape": (320, 180),
        "portrait": (180, 320),
        "square": (240, 240),
    }
    FIT_MODES = ("contain", "cover", "stretch", "original_size")

    def __init__(self, *, output_root: str | Path) -> None:
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.font_path = (
            self.repo_root
            / "resources"
            / "hyperframes"
            / "runtime"
            / "fonts"
            / "assets"
            / "NotoSansSC-wght.ttf"
        ).resolve()
        self.analyzer = RenderArtifactAnalyzer()
        self.probe = RenderOutputProbe()

    def golden_cases(self) -> tuple[QualificationCase, ...]:
        return tuple(
            QualificationCase(
                name=f"{orientation}-{fit}",
                width=dimensions[0],
                height=dimensions[1],
                fit=fit,
            )
            for orientation, dimensions in self.ORIENTATIONS.items()
            for fit in self.FIT_MODES
        )

    def run_golden_matrix(
        self,
        *,
        expectations_path: str | Path,
        use_gpu: bool = False,
    ) -> dict:
        expectations = self._read_expectations(expectations_path)
        cases: list[dict] = []
        failures: list[str] = []
        for case in self.golden_cases():
            case_root = self.output_root / "golden" / case.name
            manifest = self.build_fixed_manifest(case=case, case_root=case_root)
            outputs = self.render_both(
                manifest=manifest,
                case_root=case_root,
                use_gpu=use_gpu,
            )
            ffmpeg_frame = self.analyzer.extract_frame(
                video_path=outputs["ffmpeg"].output_path,
                timestamp=GOLDEN_SAMPLE_TIME,
                output_path=case_root / "ffmpeg.png",
            )
            hyperframes_frame = self.analyzer.extract_frame(
                video_path=outputs["hyperframes"].output_path,
                timestamp=GOLDEN_SAMPLE_TIME,
                output_path=case_root / "hyperframes.png",
            )
            ffmpeg_metrics = self.analyzer.analyze_frame(ffmpeg_frame)
            hyperframes_metrics = self.analyzer.analyze_frame(hyperframes_frame)
            difference = self.analyzer.compare(
                left_frame=ffmpeg_frame,
                right_frame=hyperframes_frame,
                left_metrics=ffmpeg_metrics,
                right_metrics=hyperframes_metrics,
            )
            expected = expectations.get(case.name)
            if not isinstance(expected, dict):
                raise ValueError(f"missing golden expectation for {case.name}")
            expected_media = PixelBox(**expected["media_box"])
            expected_landmark = PixelBox(**expected["landmark_box"])
            expected_text_line_count = int(expected["text_line_count"])
            expected_text_baseline_proxy_rows = tuple(
                int(value) for value in expected["text_baseline_proxy_rows"]
            )
            errors: list[str] = []
            try:
                self.analyzer.assert_pixel_contract(
                    expected_media_box=expected_media,
                    expected_landmark_box=expected_landmark,
                    expected_text_line_count=expected_text_line_count,
                    expected_text_baseline_proxy_rows=expected_text_baseline_proxy_rows,
                    left=ffmpeg_metrics,
                    right=hyperframes_metrics,
                    difference=difference,
                )
            except AssertionError as exc:
                errors.append(str(exc))
                failures.append(f"{case.name}: {exc}")
            case_payload = {
                "case": asdict(case),
                "expected": expected,
                "outputs": {
                    name: asdict(measurement) for name, measurement in outputs.items()
                },
                "ffmpeg_frame": ffmpeg_metrics.to_dict(),
                "hyperframes_frame": hyperframes_metrics.to_dict(),
                "difference": difference.to_dict(),
                "errors": errors,
                "ok": not errors,
            }
            self.analyzer.write_report(case_root / "difference_report.json", case_payload)
            cases.append(case_payload)
        payload = {
            "version": "render_qualification.v1",
            "kind": "golden_matrix",
            "case_count": len(cases),
            "cases": cases,
            "errors": failures,
            "ok": not failures,
        }
        self.analyzer.write_report(self.output_root / "golden_matrix_report.json", payload)
        return payload

    def run_long_duration_matrix(
        self,
        *,
        durations: tuple[float, ...] = (121.0, 271.910113),
        use_gpu: bool = False,
    ) -> dict:
        results = []
        for duration in durations:
            case = QualificationCase(
                name=f"long-{str(duration).replace('.', '_')}",
                width=320,
                height=180,
                fit="contain",
                duration=duration,
            )
            case_root = self.output_root / "long" / case.name
            manifest = self.build_fixed_manifest(case=case, case_root=case_root)
            outputs = self.render_both(
                manifest=manifest,
                case_root=case_root,
                use_gpu=use_gpu,
            )
            results.append(
                {
                    "duration": duration,
                    "outputs": {
                        name: asdict(measurement)
                        for name, measurement in outputs.items()
                    },
                    "ok": True,
                }
            )
        payload = {
            "version": "render_qualification.v1",
            "kind": "long_duration_matrix",
            "results": results,
            "ok": True,
        }
        self.analyzer.write_report(self.output_root / "long_duration_report.json", payload)
        return payload

    def run_performance_gate(self, *, repeats: int = 5) -> dict:
        if repeats != 5:
            raise ValueError("the release performance gate requires exactly five runs")
        case = QualificationCase(
            name="performance-landscape-contain",
            width=320,
            height=180,
            fit="contain",
            duration=GOLDEN_DURATION,
        )
        measurements: dict[str, list[RenderMeasurement]] = {
            "hyperframes": [],
            "ffmpeg": [],
        }
        for index in range(repeats):
            case_root = self.output_root / "performance" / f"run-{index + 1}"
            manifest = self.build_fixed_manifest(case=case, case_root=case_root)
            # Alternate order to reduce systematic warm-cache and thermal bias.
            order = ("hyperframes", "ffmpeg") if index % 2 == 0 else ("ffmpeg", "hyperframes")
            for backend in order:
                measurement = (
                    self.render_hyperframes(
                        manifest=manifest,
                        case_root=case_root,
                        use_gpu=False,
                        output_name=f"hyperframes-{index + 1}.mp4",
                    )
                    if backend == "hyperframes"
                    else self.render_ffmpeg(
                        manifest=manifest,
                        case_root=case_root,
                        encoder="libx264",
                        output_name=f"ffmpeg-{index + 1}.mp4",
                    )
                )
                measurements[backend].append(measurement)
        medians = {
            backend: {
                "elapsed_seconds": statistics.median(
                    item.elapsed_seconds for item in values
                ),
                "peak_rss_bytes": statistics.median(
                    item.peak_rss_bytes for item in values
                ),
            }
            for backend, values in measurements.items()
        }
        elapsed_ratio = (
            medians["ffmpeg"]["elapsed_seconds"]
            / medians["hyperframes"]["elapsed_seconds"]
        )
        memory_ratio = (
            medians["ffmpeg"]["peak_rss_bytes"]
            / medians["hyperframes"]["peak_rss_bytes"]
        )
        failures = []
        if elapsed_ratio > 0.8:
            failures.append(f"median elapsed ratio exceeds 0.8: {elapsed_ratio:.6f}")
        if memory_ratio > 1.1:
            failures.append(f"peak memory ratio exceeds 1.1: {memory_ratio:.6f}")
        payload = {
            "version": "render_qualification.v1",
            "kind": "performance_gate",
            "repeats": repeats,
            "runs": {
                backend: [asdict(item) for item in values]
                for backend, values in measurements.items()
            },
            "medians": medians,
            "ffmpeg_elapsed_ratio": elapsed_ratio,
            "ffmpeg_peak_memory_ratio": memory_ratio,
            "errors": failures,
            "ok": not failures,
        }
        self.analyzer.write_report(self.output_root / "performance_report.json", payload)
        if failures:
            raise AssertionError("; ".join(failures))
        return payload

    def run_hardware_matrix(self) -> dict:
        case = QualificationCase(
            name="hardware-landscape-contain",
            width=320,
            height=180,
            fit="contain",
        )
        case_root = self.output_root / "hardware"
        manifest = self.build_fixed_manifest(case=case, case_root=case_root)
        results = []
        for codec in ("h264_nvenc", "h264_qsv", "h264_vaapi"):
            backend = get_h264_backend(codec)
            with _encoder_override(codec):
                runnable = any(item.codec == codec for item in available_h264_backends())
                if not runnable:
                    results.append(
                        {
                            "codec": codec,
                            "hardware": backend.hardware,
                            "status": "device_unavailable",
                            "available_on_host": False,
                            "ok": None,
                        }
                    )
                    continue
                measurement = self.render_ffmpeg(
                    manifest=manifest,
                    case_root=case_root,
                    encoder=codec,
                    output_name=f"{codec}.mp4",
                )
                report = json.loads(
                    Path(measurement.output_path)
                    .with_name(f"{Path(measurement.output_path).stem}.render_probe.json")
                    .read_text(encoding="utf-8")
                )
                used_codec = report.get("encoder_backend")
                results.append(
                    {
                        "codec": codec,
                        "hardware": True,
                        "available_on_host": True,
                        "status": "passed" if used_codec == codec else "unexpected_fallback",
                        "measurement": asdict(measurement),
                        "encoder_backend": used_codec,
                        "ok": used_codec == codec,
                    }
                )
        available_results = [
            item for item in results if item["available_on_host"]
        ]
        payload = {
            "version": "render_qualification.v1",
            "kind": "hardware_matrix",
            "results": results,
            "available_codecs": [item["codec"] for item in available_results],
            "unavailable_codecs": [
                item["codec"] for item in results if not item["available_on_host"]
            ],
            "ok": bool(available_results)
            and all(item["ok"] is True for item in available_results),
        }
        self.analyzer.write_report(self.output_root / "hardware_report.json", payload)
        return payload

    def run_historical_task(self, *, task_dir: str | Path, use_gpu: bool = False) -> dict:
        source_task = Path(task_dir).resolve()
        source_manifest = source_task / "hyperframes" / "data" / "render_manifest.json"
        if not source_manifest.is_file():
            raise ValueError(f"historical render manifest does not exist: {source_manifest}")
        manifest = RenderManifest.from_dict(
            json.loads(source_manifest.read_text(encoding="utf-8"))
        )
        source_task_id = validate_task_id(str(manifest.task_id))
        project_dir = source_task / "hyperframes"
        resolved_clips = []
        geometry = MediaGeometryResolver()
        for clip in manifest.visual_clips:
            media_path = self._resolve_historical_asset(
                clip.media_path,
                source_task=source_task,
                project_dir=project_dir,
                field_name=f"visual clip {clip.id!r}",
            )
            box = geometry.resolve_box(
                media_path=str(media_path),
                media_type=clip.media_type,
                canvas_width=manifest.canvas_width,
                canvas_height=manifest.canvas_height,
                fallback_width=manifest.media_width,
                fallback_height=manifest.media_height,
                placement=manifest.media_placement,
            )
            resolved_clips.append(
                replace(clip, media_path=str(media_path.resolve()), resolved_media_box=box)
            )
        master_audio = self._resolve_historical_asset(
            manifest.master_audio_path or "",
            source_task=source_task,
            project_dir=project_dir,
            field_name="master audio",
        )
        resolved_audio_tracks = []
        for track in manifest.audio_tracks:
            audio_path = self._resolve_historical_asset(
                track.path,
                source_task=source_task,
                project_dir=project_dir,
                field_name=f"audio track {track.id!r}",
            )
            resolved_audio_tracks.append(
                replace(track, path=str(audio_path.resolve()))
            )
        text_tracks = list(manifest.text_tracks)
        text_cues = list(manifest.text_cues)
        if not text_cues and manifest.caption_cues:
            text_tracks = [
                TextTrack(
                    id="historical-captions",
                    kind="caption",
                    name="Historical Captions",
                    renderer_targets=("ass",),
                    style_profile="caption-default",
                )
            ]
            text_cues = [
                TextCue(
                    id=cue.id,
                    track_id="historical-captions",
                    text=cue.text,
                    start=cue.start,
                    end=cue.end,
                    role="subtitle",
                    slot="lower_third",
                    style_profile=cue.style_profile or "caption-default",
                    frame_indices=tuple(cue.frame_indices),
                )
                for cue in manifest.caption_cues
            ]
        resolved_profiles = [
            self._resolve_historical_font_profile(
                profile=profile,
                source_task=source_task,
                project_dir=project_dir,
            )
            for profile in manifest.text_style_profiles
        ]
        replay = replace(
            manifest,
            task_id=f"history-{source_task_id}"[-120:],
            master_audio_path=str(master_audio.resolve()),
            audio_tracks=resolved_audio_tracks,
            visual_clips=resolved_clips,
            text_style_profiles=resolved_profiles,
            text_tracks=text_tracks,
            text_cues=text_cues,
            caption_cues=list(manifest.caption_cues),
        )
        case_root = resolve_task_dir(self.output_root / "history", source_task_id)
        outputs = self.render_both(
            manifest=replay,
            case_root=case_root,
            use_gpu=use_gpu,
        )
        payload = {
            "version": "render_qualification.v1",
            "kind": "historical_task",
            "source_task": str(source_task),
            "source_manifest_version": manifest.version,
            "replay_manifest_version": replay.version,
            "outputs": {
                name: asdict(measurement) for name, measurement in outputs.items()
            },
            "ok": True,
        }
        self.analyzer.write_report(case_root / "historical_report.json", payload)
        return payload

    def _resolve_historical_font_profile(
        self,
        *,
        profile: TextStyleProfile,
        source_task: Path,
        project_dir: Path,
    ) -> TextStyleProfile:
        if not profile.font_file:
            return profile
        source_repository = self._source_repository(source_task)
        resolved = self._resolve_historical_asset(
            profile.font_file,
            source_task=source_task,
            project_dir=project_dir,
            field_name=f"font profile {profile.id!r}",
            additional_relative_roots=(source_task, source_repository),
            additional_trusted_roots=self._repository_asset_roots(source_repository),
        )
        return replace(profile, font_file=str(resolved))

    def _resolve_historical_asset(
        self,
        raw_path: str,
        *,
        source_task: Path,
        project_dir: Path,
        field_name: str,
        additional_relative_roots: tuple[Path | None, ...] = (),
        additional_trusted_roots: tuple[Path, ...] = (),
    ) -> Path:
        path_text = str(raw_path).strip()
        if not path_text:
            raise ValueError(f"historical {field_name} path cannot be empty")
        supplied = Path(path_text)
        trusted_roots = tuple(
            root.resolve()
            for root in (
                source_task,
                self.repo_root / "resources",
                *additional_trusted_roots,
            )
            if root is not None
        )
        if supplied.is_absolute():
            candidates = (supplied.resolve(),)
        else:
            relative_roots = (
                project_dir,
                *additional_relative_roots,
            )
            candidates = tuple(
                resolve_path_within(root, supplied)
                for root in relative_roots
                if root is not None
            )
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if any(
                candidate == trusted_root or candidate.is_relative_to(trusted_root)
                for trusted_root in trusted_roots
            ):
                return candidate
            raise ValueError(
                f"historical {field_name} resolves outside trusted roots: {candidate}"
            )
        raise ValueError(
            f"historical {field_name} asset cannot be resolved without substitution: "
            f"{raw_path!r}"
        )

    @staticmethod
    def _source_repository(source_task: Path) -> Path | None:
        candidate = source_task.parent.parent.resolve()
        git_marker = candidate / ".git"
        if source_task.parent.name == "output" and git_marker.exists():
            return candidate
        return None

    @staticmethod
    def _repository_asset_roots(repository: Path | None) -> tuple[Path, ...]:
        if repository is None:
            return ()
        return (repository / "fonts", repository / "resources")

    def build_fixed_manifest(
        self,
        *,
        case: QualificationCase,
        case_root: Path,
    ) -> RenderManifest:
        assets = case_root / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        image_path = assets / "fixed_asset.png"
        audio_path = assets / "master_audio.wav"
        self._write_fixed_image(image_path)
        self._write_silence(audio_path, case.duration)
        placement = MediaPlacement(fit=case.fit)
        media_box = calculate_media_box(
            canvas_width=case.width,
            canvas_height=case.height,
            media_source_width=GOLDEN_SOURCE_WIDTH,
            media_source_height=GOLDEN_SOURCE_HEIGHT,
            placement=placement,
        )
        profile = TextStyleProfile(
            id="golden",
            name="Golden",
            font_family="Noto Sans SC",
            font_file=str(self.font_path),
            font_size=36,
            font_weight=500,
            primary_color="#FFFFFF",
            stroke_color="#000000",
            stroke_width=1,
            position="bottom",
            alignment="center",
            margin_x=10,
            margin_y=12,
            max_width_ratio=0.9,
            line_height=1.0,
            max_chars_per_line=8,
            punctuation_mode="preserve",
        )
        cue_end = max(0.2, case.duration - 0.1)
        return RenderManifest(
            version="render_manifest.v2",
            task_id=case.name.replace(".", "_"),
            title="",
            width=case.width,
            height=case.height,
            fps=30,
            template_id=GOLDEN_TEMPLATE_ID,
            master_audio_path=str(audio_path),
            master_audio_duration=case.duration,
            media_placement=placement,
            text_style_profiles=[profile],
            text_tracks=[
                TextTrack(
                    id="golden-text",
                    kind="caption",
                    name="Golden Text",
                    renderer_targets=("hyperframes", "ass"),
                    style_profile=profile.id,
                )
            ],
            text_cues=[
                TextCue(
                    id="golden-cue",
                    track_id="golden-text",
                    text=GOLDEN_TEXT,
                    start=0.1,
                    end=cue_end,
                    role="subtitle",
                    slot="lower_third",
                    style_profile=profile.id,
                )
            ],
            visual_clips=[
                VisualClip(
                    id="golden-visual",
                    frame_index=0,
                    start=0,
                    end=case.duration,
                    media_path=str(image_path),
                    media_type="image",
                    resolved_media_box=media_box,
                )
            ],
        )

    def render_both(
        self,
        *,
        manifest: RenderManifest,
        case_root: Path,
        use_gpu: bool,
    ) -> dict[str, RenderMeasurement]:
        RenderSnapshotService().write(
            output_dir=case_root / "snapshot",
            manifest=manifest,
            execution_plan=RenderExecutionPlan(
                requested_backend="hyperframes_compiled",
                effective_backend="hyperframes_compiled",
            ),
        )
        return {
            "ffmpeg": self.render_ffmpeg(
                manifest=manifest,
                case_root=case_root,
                encoder="libx264",
            ),
            "hyperframes": self.render_hyperframes(
                manifest=manifest,
                case_root=case_root,
                use_gpu=use_gpu,
            ),
        }

    def render_ffmpeg(
        self,
        *,
        manifest: RenderManifest,
        case_root: Path,
        encoder: str,
        output_name: str = "ffmpeg.mp4",
    ) -> RenderMeasurement:
        output = case_root / output_name
        ass = AssTextAdapter().export(
            manifest=manifest,
            output_dir=case_root / f"ass-{output.stem}",
        ).master
        background_track = self._ffmpeg_background_track(manifest)
        with _encoder_override(encoder):
            return self._measure(
                lambda: FfmpegManifestRenderer().render(
                    manifest=manifest,
                    execution_plan=RenderExecutionPlan(
                        requested_backend="ffmpeg_manifest",
                        effective_backend="ffmpeg_manifest",
                    ),
                    output_path=str(output),
                    ass_path=str(ass),
                    bgm_path=(background_track.path if background_track else None),
                    bgm_volume=(background_track.volume if background_track else 0.2),
                    bgm_mode="once",
                )
            )

    @staticmethod
    def _ffmpeg_background_track(
        manifest: RenderManifest,
    ) -> RenderAudioTrack | None:
        background_tracks = [
            track
            for track in manifest.audio_tracks
            if track.role.strip().lower() in {"background", "bgm", "music"}
        ]
        if len(background_tracks) > 1:
            raise ValueError(
                "ffmpeg qualification supports exactly one historical background track"
            )
        if not background_tracks:
            return None
        track = background_tracks[0]
        if abs(track.start) > 0.001 or abs(track.media_start) > 0.001:
            raise ValueError(
                "historical background track timing cannot be projected without loss: "
                f"track={track.id!r}, start={track.start}, media_start={track.media_start}"
            )
        return track

    def render_hyperframes(
        self,
        *,
        manifest: RenderManifest,
        case_root: Path,
        use_gpu: bool,
        output_name: str = "hyperframes.mp4",
    ) -> RenderMeasurement:
        project = HyperFramesProjectService(
            output_dir=str(case_root / "hyperframes-tasks")
        ).write_project(manifest)
        output = case_root / output_name

        def render() -> str:
            result = HyperFramesRenderer(use_gpu=use_gpu).render(
                str(project.project_dir),
                str(output),
                width=manifest.canvas_width,
                height=manifest.canvas_height,
                fps=manifest.fps,
                expected_duration=manifest.master_audio_duration,
                expect_audio=True,
            )
            self.probe.validate(
                output_path=result,
                width=manifest.canvas_width,
                height=manifest.canvas_height,
                fps=manifest.fps,
                duration=float(manifest.master_audio_duration or 0),
                subtitle_end=max(
                    (cue.end for cue in manifest.text_cues),
                    default=None,
                ),
                report_path=output.with_name(f"{output.stem}.render_probe.json"),
                encoder_backend="hyperframes_compiled",
                lossy_encode_count=1,
            )
            return result

        return self._measure(render)

    @staticmethod
    def _measure(operation: Callable[[], str]) -> RenderMeasurement:
        started = time.perf_counter()
        with _PeakMemorySampler() as sampler:
            output = operation()
        return RenderMeasurement(
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_bytes=sampler.peak_rss_bytes,
            output_path=str(Path(output).resolve()),
        )

    @staticmethod
    def _write_fixed_image(path: Path) -> None:
        image = Image.new(
            "RGB",
            (GOLDEN_SOURCE_WIDTH, GOLDEN_SOURCE_HEIGHT),
            (24, 24, 24),
        )
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (0, 0, GOLDEN_SOURCE_WIDTH - 1, GOLDEN_SOURCE_HEIGHT - 1),
            outline=(0, 255, 0),
            width=8,
        )
        draw.line(
            (0, GOLDEN_SOURCE_HEIGHT // 2, GOLDEN_SOURCE_WIDTH - 1, GOLDEN_SOURCE_HEIGHT // 2),
            fill=(255, 0, 255),
            width=5,
        )
        draw.rectangle((44, 60, 156, 240), outline=(0, 180, 255), width=4)
        image.save(path)

    @staticmethod
    def _write_silence(path: Path, duration: float) -> None:
        frame_count = int(round(float(duration) * 48000))
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(48000)
            chunk = b"\0\0\0\0" * 48000
            remaining = frame_count
            while remaining:
                current = min(remaining, 48000)
                audio.writeframesraw(chunk[: current * 4])
                remaining -= current

    @staticmethod
    def _read_expectations(path: str | Path) -> dict[str, dict]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("version") != "render_golden_expectations.v1":
            raise ValueError("unsupported golden expectation version")
        cases = payload.get("cases")
        if not isinstance(cases, dict):
            raise ValueError("golden expectations must contain a case mapping")
        return cases


@contextmanager
def _encoder_override(codec: str) -> Iterator[None]:
    previous = os.environ.get("PIXELLE_FFMPEG_H264_ENCODER")
    os.environ["PIXELLE_FFMPEG_H264_ENCODER"] = codec
    clear_ffmpeg_encoder_probe_cache()
    reset_runtime_encoder_failures()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PIXELLE_FFMPEG_H264_ENCODER", None)
        else:
            os.environ["PIXELLE_FFMPEG_H264_ENCODER"] = previous
        clear_ffmpeg_encoder_probe_cache()
        reset_runtime_encoder_failures()


__all__ = [
    "QualificationCase",
    "RenderMeasurement",
    "RenderQualificationSuite",
]
