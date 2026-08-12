import json
from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.models.render_package import RenderAudioTrack, RenderManifest
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.render_qualification import (
    GOLDEN_TEXT,
    QualificationCase,
    RenderQualificationSuite,
)


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
