from pathlib import Path


def test_phase1_runtime_assets_are_local_only():
    fonts_css = Path("resources/hyperframes/runtime/fonts/phase1_fonts.css")
    vendor_readme = Path("resources/hyperframes/runtime/vendor/README.md")

    assert fonts_css.exists()
    assert vendor_readme.exists()
    assert "https://" not in fonts_css.read_text(encoding="utf-8")
