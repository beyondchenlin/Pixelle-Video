import json
from pathlib import Path


def test_hyperframes_runtime_authority_is_pinned_npm_package() -> None:
    package_json = json.loads(
        Path("tools/hyperframes_bridge/package.json").read_text(encoding="utf-8")
    )

    dependencies = package_json["dependencies"]
    assert "@hyperframes/producer" in dependencies

    version = dependencies["@hyperframes/producer"]
    assert version
    assert not version.startswith(("^", "~", ">", "<", "*"))


def test_bridge_runtime_does_not_load_vendor_snapshots() -> None:
    for path in Path("tools/hyperframes_bridge/src").rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            assert "vendor/hyperframes" not in content, path
            assert "third_party/hyperframes" not in content, path


def test_hyperframes_text_style_manifest_contract_exposes_title_profile() -> None:
    manifest = json.loads(
        Path("tests/fixtures/text_rendering/render_manifest_with_text_styles.json").read_text(
            encoding="utf-8"
        )
    )

    assert [profile["id"] for profile in manifest["text_style_profiles"]] == [
        "caption-default",
        "title-default",
        "overlay-default",
    ]
