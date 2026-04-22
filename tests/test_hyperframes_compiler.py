from pathlib import Path

from pixelle_video.models.render_package import CaptionCue, VisualClip
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler


def test_phase1_runtime_assets_are_local_only():
    fonts_css = Path("resources/hyperframes/runtime/fonts/phase1_fonts.css")
    vendor_readme = Path("resources/hyperframes/runtime/vendor/README.md")

    assert fonts_css.exists()
    assert vendor_readme.exists()
    assert "https://" not in fonts_css.read_text(encoding="utf-8")


def test_compiler_emits_static_index_without_manifest_fetch_or_remote_urls(tmp_path: Path):
    template_root = tmp_path / "templates"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        (
            '<div id="root" data-width="__CANVAS_WIDTH__" '
            'data-height="__CANVAS_HEIGHT__" data-duration="__DURATION__">'
            "__VISUALS____AUDIO__</div>"
        ),
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        '<div id="captions-root" data-duration="__DURATION__">__CAPTIONS__</div>',
        encoding="utf-8",
    )
    compiler = HyperFramesCompiler(template_root=template_root)
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=12.5,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        template_params={},
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=3.0,
                media_path="assets/images/01_image.png",
                media_type="image",
            )
        ],
        captions=[
            CaptionCue(
                id="c1",
                text="第一句",
                start=0.0,
                end=3.0,
                frame_indices=[0],
                style_profile="image_default",
            )
        ],
        audio=TemplateAudioRef(path="assets/audio/master_audio.wav", duration=12.5),
    )

    project_dir = tmp_path / "task" / "hyperframes"
    compiler.compile(project_dir=project_dir, context=context)

    index_html = (project_dir / "index.html").read_text(encoding="utf-8")
    captions_html = (project_dir / "compositions" / "captions.html").read_text(
        encoding="utf-8"
    )

    assert "render_manifest.json" not in index_html
    assert "https://" not in index_html
    assert 'src="assets/audio/master_audio.wav"' in index_html
    assert 'src="assets/images/01_image.png"' in index_html
    assert 'data-duration="12.5"' in captions_html


def test_phase1_templates_do_not_depend_on_remote_fonts_or_cdn_scripts():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/index.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
        Path(
            "resources/hyperframes/templates/image_default/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
        ),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "https://fonts.googleapis.com" not in content
        assert "https://cdnjs.cloudflare.com" not in content


def test_phase1_templates_preserve_source_shell_regions():
    content = Path(
        "resources/hyperframes/templates/image_life_insights_light/index.template.html"
    ).read_text(encoding="utf-8")

    assert "bg-pattern" in content
    assert "header" in content
    assert "content" in content
    assert "bottom-section" in content
    assert "author" in content
