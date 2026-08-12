import json
import os
from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.models.render_package import RenderAudioTrack, RenderManifest
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services import render_qualification as qualification_module
from pixelle_video.services.render_qualification import (
    GOLDEN_TEXT,
    QualificationCase,
    RenderMeasurement,
    RenderQualificationSuite,
)
from pixelle_video.utils.ffmpeg_encoder import get_h264_backend


def test_golden_cases_cover_three_orientations_and_four_fit_modes(tmp_path):
    suite = RenderQualificationSuite(output_root=tmp_path)

    cases = suite.golden_cases()

    assert len(cases) == 12
    assert {case.name for case in cases} == {
        f"{orientation}-{fit}"
        for orientation in ("landscape", "portrait", "square")
        for fit in ("contain", "cover", "stretch", "original_size")
    }


def test_fixed_manifest_is_versioned_and_uses_identical_baseline_lines(tmp_path):
    suite = RenderQualificationSuite(output_root=tmp_path / "reports")
    case = QualificationCase(
        name="landscape-contain",
        width=320,
        height=180,
        fit="contain",
    )

    manifest = suite.build_fixed_manifest(case=case, case_root=tmp_path / "case")

    assert manifest.version == "render_manifest.v2"
    assert manifest.media_placement.fit == "contain"
    assert manifest.text_cues[0].text == GOLDEN_TEXT == "BASELINEBASELINE"
    assert manifest.text_style_profiles[0].max_chars_per_line == 8
    assert manifest.text_tracks[0].renderer_targets == ("hyperframes", "ass")
    assert manifest.visual_clips[0].resolved_media_box is not None
    assert Path(manifest.master_audio_path).is_file()
    with Image.open(manifest.visual_clips[0].media_path) as fixed_asset:
        assert fixed_asset.size == (200, 300)


def test_performance_gate_requires_exactly_five_runs(tmp_path):
    suite = RenderQualificationSuite(output_root=tmp_path)

    with pytest.raises(ValueError, match="exactly five runs"):
        suite.run_performance_gate(repeats=4)


def test_exact_hardware_gate_fails_closed_when_required_device_is_unavailable(
    tmp_path,
    monkeypatch,
):
    suite = RenderQualificationSuite(output_root=tmp_path / "evidence")
    monkeypatch.setattr(suite, "build_fixed_manifest", lambda **_kwargs: object())
    monkeypatch.setattr(
        qualification_module,
        "available_h264_backends",
        lambda: (get_h264_backend("libx264"),),
    )
    monkeypatch.setattr(
        qualification_module,
        "collect_hardware_provenance",
        lambda **_kwargs: _clean_hardware_provenance(),
    )

    report = suite.run_hardware_matrix(required_codec="h264_qsv")

    assert report["required_codec"] == "h264_qsv"
    assert report["results"] == [
        {
            "codec": "h264_qsv",
            "hardware": True,
            "status": "device_unavailable",
            "available_on_host": False,
            "ok": False,
        }
    ]
    assert report["ok"] is False
    assert report["complete_on_host"] is False
    assert report["errors"] == [
        "required hardware codec is unavailable on this host: h264_qsv"
    ]


def test_exact_hardware_gate_records_portable_hashed_final_artifacts(
    tmp_path,
    monkeypatch,
):
    suite = RenderQualificationSuite(output_root=tmp_path / "evidence")
    monkeypatch.setattr(suite, "build_fixed_manifest", lambda **_kwargs: object())
    monkeypatch.setattr(
        qualification_module,
        "available_h264_backends",
        lambda: (
            get_h264_backend(os.environ["PIXELLE_FFMPEG_H264_ENCODER"]),
            get_h264_backend("libx264"),
        ),
    )
    monkeypatch.setattr(
        qualification_module,
        "collect_hardware_provenance",
        lambda **_kwargs: _clean_hardware_provenance(),
    )

    def fake_render_ffmpeg(*, case_root, encoder, output_name, **_kwargs):
        case_root.mkdir(parents=True, exist_ok=True)
        output = case_root / output_name
        output.write_bytes(b"real-device-final-video")
        output.with_name(f"{output.stem}.render_probe.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "encoder_backend": encoder,
                    "lossy_encode_count": 1,
                }
            ),
            encoding="utf-8",
        )
        return RenderMeasurement(
            elapsed_seconds=1.25,
            peak_rss_bytes=1024,
            output_path=str(output),
        )

    monkeypatch.setattr(suite, "render_ffmpeg", fake_render_ffmpeg)

    report = suite.run_hardware_matrix(required_codec="h264_nvenc")

    result = report["results"][0]
    assert report["ok"] is True
    assert report["host_ok"] is True
    assert report["complete_on_host"] is False
    assert result["status"] == "passed"
    assert result["measurement"] == {
        "elapsed_seconds": 1.25,
        "peak_rss_bytes": 1024,
    }
    assert result["artifact"]["relative_path"] == "hardware/h264_nvenc.mp4"
    assert len(result["artifact"]["sha256"]) == 64
    assert "output_path" not in result["measurement"]
    portable_probe = json.loads(
        (
            tmp_path
            / "evidence"
            / result["probe_artifact"]["relative_path"]
        ).read_text(encoding="utf-8")
    )
    assert portable_probe["path"] == "hardware/h264_nvenc.mp4"
    assert portable_probe["path_kind"] == "relative_to_report_root"


def test_historical_font_resolution_uses_original_repository_asset(tmp_path):
    repository = tmp_path / "repository"
    source_task = repository / "output" / "task-1"
    project_dir = source_task / "hyperframes"
    font = repository / "fonts" / "historical.ttf"
    project_dir.mkdir(parents=True)
    (repository / ".git").mkdir()
    font.parent.mkdir(parents=True)
    font.write_bytes(b"historical font fixture")
    suite = RenderQualificationSuite(output_root=tmp_path / "reports")
    profile = TextStyleProfile(
        id="historical",
        name="Historical",
        font_file="fonts/historical.ttf",
    )

    resolved = suite._resolve_historical_font_profile(
        profile=profile,
        source_task=source_task,
        project_dir=project_dir,
    )

    assert resolved.font_file == str(font.resolve())


def test_historical_font_resolution_rejects_silent_substitution(tmp_path):
    source_task = tmp_path / "repository" / "output" / "task-1"
    project_dir = source_task / "hyperframes"
    project_dir.mkdir(parents=True)
    suite = RenderQualificationSuite(output_root=tmp_path / "reports")
    profile = TextStyleProfile(
        id="missing",
        name="Missing",
        font_file="fonts/missing.ttf",
    )

    with pytest.raises(ValueError, match="without substitution"):
        suite._resolve_historical_font_profile(
            profile=profile,
            source_task=source_task,
            project_dir=project_dir,
        )


def test_historical_asset_resolution_rejects_existing_file_outside_trusted_roots(
    tmp_path,
):
    repository = tmp_path / "repository"
    source_task = repository / "output" / "task-1"
    project_dir = source_task / "hyperframes"
    project_dir.mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    suite = RenderQualificationSuite(output_root=tmp_path / "reports")

    with pytest.raises(ValueError, match="outside trusted roots"):
        suite._resolve_historical_asset(
            str(outside),
            source_task=source_task,
            project_dir=project_dir,
            field_name="test asset",
        )


def test_historical_task_rejects_manifest_task_id_path_escape(tmp_path):
    source_task = tmp_path / "source-task"
    manifest_dir = source_task / "hyperframes" / "data"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "version": "render_manifest.v1",
                "task_id": "../escape",
                "title": "unsafe",
                "width": 320,
                "height": 180,
                "fps": 30,
                "template_id": "image_default",
            }
        ),
        encoding="utf-8",
    )
    suite = RenderQualificationSuite(output_root=tmp_path / "reports")

    with pytest.raises(ValueError, match="unsafe path characters"):
        suite.run_historical_task(task_dir=source_task)


def test_ffmpeg_background_track_preserves_single_zero_offset_track():
    background = RenderAudioTrack(
        id="background",
        path="background.wav",
        start=0,
        end=10,
        volume=0.25,
        role="background",
    )
    manifest = RenderManifest(
        task_id="audio",
        title="",
        width=320,
        height=180,
        fps=30,
        template_id="legacy",
        audio_tracks=[background],
    )

    assert RenderQualificationSuite._ffmpeg_background_track(manifest) is background


def test_ffmpeg_background_track_rejects_unrepresentable_timing():
    manifest = RenderManifest(
        task_id="audio-offset",
        title="",
        width=320,
        height=180,
        fps=30,
        template_id="legacy",
        audio_tracks=[
            RenderAudioTrack(
                id="background",
                path="background.wav",
                start=1,
                end=10,
                role="background",
            )
        ],
    )

    with pytest.raises(ValueError, match="cannot be projected without loss"):
        RenderQualificationSuite._ffmpeg_background_track(manifest)


def _clean_hardware_provenance() -> dict:
    return {
        "source_revision": "a" * 40,
        "source_tree_clean": True,
        "host": {
            "operating_system": "TestOS",
            "operating_system_release": "1",
            "architecture": "x86_64",
            "ffmpeg_version": "ffmpeg test",
            "hardware_devices": ["test device"],
        },
        "ci": {
            "provider": "local",
            "run_id": None,
            "run_attempt": None,
            "job": None,
        },
    }
