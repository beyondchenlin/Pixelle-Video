from pathlib import Path

from pixelle_video.services.hyperframes_asset_materializer import (
    HyperFramesAssetMaterializer,
)


def test_asset_materializer_copies_inputs_into_project_local_assets(tmp_path: Path):
    source_audio = tmp_path / "master_audio.wav"
    source_image = tmp_path / "01_image.png"
    source_audio.write_bytes(b"wav")
    source_image.write_bytes(b"png")

    materializer = HyperFramesAssetMaterializer()
    project_dir = tmp_path / "task" / "hyperframes"
    result = materializer.materialize(
        project_dir=project_dir,
        audio_sources={"master_audio.wav": source_audio},
        image_sources={"01_image.png": source_image},
        video_sources={},
    )

    assert (project_dir / "assets" / "audio" / "master_audio.wav").exists()
    assert (project_dir / "assets" / "images" / "01_image.png").exists()
    assert result["audio"]["master_audio.wav"] == "assets/audio/master_audio.wav"
    assert result["images"]["01_image.png"] == "assets/images/01_image.png"
