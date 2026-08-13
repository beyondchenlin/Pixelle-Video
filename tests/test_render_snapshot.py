import json
import os
from pathlib import Path

import pytest

from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest, VisualClip
from pixelle_video.services.render_snapshot import RenderSnapshotService
from pixelle_video.utils.filesystem import extended_length_path


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length path contract")
def test_write_json_atomic_supports_windows_paths_beyond_max_path(tmp_path: Path):
    target = (
        tmp_path
        / ("a" * 80)
        / ("b" * 80)
        / ("c" * 80)
        / "render_manifest.json"
    )
    assert len(str(target.resolve(strict=False))) > 260

    RenderSnapshotService._write_json_atomic(target, {"ok": True})

    assert json.loads(extended_length_path(target).read_text(encoding="utf-8")) == {
        "ok": True
    }


def _snapshot_manifest(tmp_path: Path) -> RenderManifest:
    audio = tmp_path / "master.wav"
    image = tmp_path / "frame.png"
    audio.write_bytes(b"audio")
    image.write_bytes(b"image")
    return RenderManifest(
        task_id="snapshot-task",
        title="Snapshot",
        width=320,
        height=180,
        fps=30,
        template_id="image_default",
        master_audio_path=str(audio),
        master_audio_duration=1.0,
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0.0,
                end=1.0,
                media_path=str(image),
                media_type="image",
            )
        ],
    )


def test_render_snapshot_persists_and_loads_resolved_contract(tmp_path):
    service = RenderSnapshotService()
    manifest = _snapshot_manifest(tmp_path)
    plan = RenderExecutionPlan(
        requested_backend="hyperframes_compiled",
        effective_backend="ffmpeg_manifest",
        fallback_reason="test fallback",
    )

    paths = service.write(
        output_dir=tmp_path / "snapshot",
        manifest=manifest,
        execution_plan=plan,
    )
    restored = service.load(paths.manifest)

    assert restored.to_dict() == manifest.to_dict()
    assert json.loads(paths.execution_plan.read_text(encoding="utf-8")) == plan.to_dict()
    inventory = json.loads(paths.asset_inventory.read_text(encoding="utf-8"))
    assert inventory["version"] == "render_asset_inventory.v1"
    assert {item["role"] for item in inventory["assets"]} == {
        "master_audio",
        "visual_clip:clip-1",
    }
    assert list((tmp_path / "snapshot").glob("*.tmp")) == []


def test_render_snapshot_rerender_uses_fixed_assets_without_generation(tmp_path):
    service = RenderSnapshotService()
    manifest = _snapshot_manifest(tmp_path)
    paths = service.write(
        output_dir=tmp_path / "snapshot",
        manifest=manifest,
        execution_plan=RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
        ),
    )
    calls = {}

    class FakeRenderer:
        def render(self, **kwargs):
            calls.update(kwargs)
            Path(kwargs["output_path"]).write_bytes(b"video")
            return kwargs["output_path"]

    output = tmp_path / "rerender.mp4"
    result = service.rerender_ffmpeg(
        manifest_path=paths.manifest,
        output_path=output,
        renderer=FakeRenderer(),
    )

    assert result == str(output.resolve())
    assert calls["manifest"].to_dict() == manifest.to_dict()
    assert calls["execution_plan"].diagnostics["source"] == "fixed_asset_rerender"


def test_render_snapshot_blocks_rerender_after_fixed_asset_changes(tmp_path):
    service = RenderSnapshotService()
    manifest = _snapshot_manifest(tmp_path)
    paths = service.write(
        output_dir=tmp_path / "snapshot",
        manifest=manifest,
        execution_plan=RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
        ),
    )
    Path(manifest.visual_clips[0].media_path).write_bytes(b"changed image")

    try:
        service.rerender_ffmpeg(
            manifest_path=paths.manifest,
            output_path=tmp_path / "rerender.mp4",
        )
    except ValueError as exc:
        assert "asset size changed" in str(exc) or "asset content changed" in str(exc)
    else:
        raise AssertionError("changed fixed asset must block rerender")


def test_render_snapshot_blocks_rerender_after_fixed_asset_is_deleted(tmp_path):
    service = RenderSnapshotService()
    manifest = _snapshot_manifest(tmp_path)
    paths = service.write(
        output_dir=tmp_path / "snapshot",
        manifest=manifest,
        execution_plan=RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
        ),
    )
    Path(manifest.visual_clips[0].media_path).unlink()

    with pytest.raises(ValueError, match="render snapshot asset is missing"):
        service.rerender_ffmpeg(
            manifest_path=paths.manifest,
            output_path=tmp_path / "rerender.mp4",
        )


def test_render_snapshot_reuses_saved_subtitle_bgm_and_mix_options(tmp_path):
    service = RenderSnapshotService()
    manifest = _snapshot_manifest(tmp_path)
    ass = tmp_path / "captions.ass"
    bgm = tmp_path / "music.wav"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    bgm.write_bytes(b"music")
    paths = service.write(
        output_dir=tmp_path / "snapshot",
        manifest=manifest,
        execution_plan=RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
        ),
        supplemental_assets={"ass": ass, "bgm": bgm},
        render_options={"bgm_volume": 0.35, "bgm_mode": "once"},
    )
    calls = {}

    class FakeRenderer:
        def render(self, **kwargs):
            calls.update(kwargs)
            return kwargs["output_path"]

    service.rerender_ffmpeg(
        manifest_path=paths.manifest,
        output_path=tmp_path / "rerender.mp4",
        renderer=FakeRenderer(),
    )

    assert calls["ass_path"] == str(ass.resolve())
    assert calls["bgm_path"] == str(bgm.resolve())
    assert calls["bgm_volume"] == 0.35
    assert calls["bgm_mode"] == "once"
