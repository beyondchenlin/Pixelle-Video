from pathlib import Path


def test_landscape_template_gallery_preview_assets_exist():
    preview_assets = [
        Path("docs/images/1920x1080/image_landscape_full.png"),
        Path("docs/images/1920x1080/image_landscape_full_en.png"),
        Path("docs/images/1920x1080/image_landscape_minimal.png"),
        Path("docs/images/1920x1080/image_landscape_minimal_en.png"),
    ]

    for preview_asset in preview_assets:
        assert preview_asset.exists(), f"missing template gallery preview: {preview_asset}"
