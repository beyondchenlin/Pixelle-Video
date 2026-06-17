import json
from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.services.reference_image_asset_service import (
    ReferenceImageAssetService,
    resolve_reference_image_input,
)


def _enabled_config(**overrides):
    config = {
        "enabled": True,
        "allowed_extensions": [".jpg", ".jpeg", ".png", ".webp"],
        "max_upload_size_mb": 20,
        "max_vision_edge_px": 64,
        "max_workflow_edge_px": 128,
        "strip_exif": True,
        "convert_to_png_for_workflow": False,
    }
    config.update(overrides)
    return config


def test_prepare_reference_image_writes_task_asset_without_source_path(tmp_path):
    source_path = tmp_path / "local_reference.png"
    Image.new("RGB", (48, 32), (255, 255, 255)).save(source_path)

    task_dir = tmp_path / "task"
    asset = ReferenceImageAssetService(_enabled_config()).prepare(
        str(source_path),
        task_dir=task_dir,
    )

    assert Path(asset.task_asset_path).is_file()
    assert Path(asset.vision_asset_path).is_file()
    assert Path(asset.workflow_asset_path).is_file()
    assert asset.task_asset_relative_path.startswith("reference_image/")
    assert asset.workflow_asset_relative_path.startswith("reference_image/")

    asset_json_path = task_dir / "reference_image" / "asset.json"
    persisted = json.loads(asset_json_path.read_text(encoding="utf-8"))
    serialized = json.dumps(persisted, ensure_ascii=False)

    assert str(source_path) not in serialized
    assert asset.sha256 in serialized


def test_prepare_reference_image_rejects_unsupported_extension(tmp_path):
    source_path = tmp_path / "reference.txt"
    source_path.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported reference image extension"):
        ReferenceImageAssetService(_enabled_config()).prepare(
            str(source_path),
            task_dir=tmp_path / "task",
        )


def test_resolve_reference_image_rejects_structured_server_path():
    with pytest.raises(ValueError, match="must not contain server-local paths"):
        resolve_reference_image_input(
            {"reference_image": {"source_path": "/etc/passwd"}}
        )


def test_upload_id_requires_api_resolution_before_assetization(tmp_path):
    with pytest.raises(ValueError, match="upload_id/artifact_id resolution is not implemented"):
        ReferenceImageAssetService(_enabled_config()).prepare(
            {"upload_id": "abc123"},
            task_dir=tmp_path / "task",
        )
