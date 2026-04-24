from pathlib import Path

import pytest

from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack, VisualClip
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler


def test_phase1_runtime_assets_are_local_only():
    fonts_css = Path("resources/hyperframes/runtime/fonts/phase1_fonts.css")
    noto_font = Path("resources/hyperframes/runtime/fonts/assets/NotoSansSC-wght.ttf")
    brush_font = Path("resources/hyperframes/runtime/fonts/assets/MaShanZheng-Regular.ttf")
    vendor_readme = Path("resources/hyperframes/runtime/vendor/README.md")
    vendor_gsap = Path("resources/hyperframes/runtime/vendor/gsap.min.js")

    assert fonts_css.exists()
    assert noto_font.exists()
    assert brush_font.exists()
    assert vendor_readme.exists()
    assert vendor_gsap.exists()
    assert "https://" not in fonts_css.read_text(encoding="utf-8")
    assert 'url("./assets/NotoSansSC-wght.ttf")' in fonts_css.read_text(encoding="utf-8")
    assert 'url("./assets/MaShanZheng-Regular.ttf")' in fonts_css.read_text(encoding="utf-8")


def test_compiler_emits_static_index_without_manifest_fetch_or_remote_urls(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (runtime_root / "fonts").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        (
            '<div id="root" data-width="__CANVAS_WIDTH__" '
            'data-height="__CANVAS_HEIGHT__" data-duration="__DURATION__">'
            '<link rel="stylesheet" href="./runtime/fonts/phase1_fonts.css" />'
            "__VISUALS____AUDIO__</div>"
        ),
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        (
            '<link rel="stylesheet" href="../runtime/fonts/phase1_fonts.css" />'
            '<div id="captions-root" data-duration="__DURATION__">__CAPTIONS__</div>'
        ),
        encoding="utf-8",
    )
    (runtime_root / "fonts" / "phase1_fonts.css").write_text(
        ":root { --hf-font-sans: sans-serif; }",
        encoding="utf-8",
    )
    compiler = HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root)
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
    assert 'class="clip visual-clip"' in index_html
    assert 'href="./runtime/fonts/phase1_fonts.css"' in index_html
    assert 'class="clip caption-group"' in captions_html
    assert 'href="../runtime/fonts/phase1_fonts.css"' in captions_html
    assert 'data-duration="12.5"' in captions_html
    assert (project_dir / "runtime" / "fonts" / "phase1_fonts.css").exists()


def test_compiler_emits_static_text_layer_without_manifest_fetch(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (runtime_root / "vendor").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        (
            '<div id="main" data-duration="__DURATION__">'
            '<div data-composition-src="compositions/text_layer.html"></div>'
            "__VISUALS____AUDIO__</div>"
        ),
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        '<div id="captions">__CAPTIONS__</div>',
        encoding="utf-8",
    )
    (
        template_root / "image_default" / "compositions" / "text_layer.template.html"
    ).write_text(
        '<div id="text-layer">__TEXT_CUES__</div><script>__TEXT_TIMELINE__</script>',
        encoding="utf-8",
    )
    (runtime_root / "vendor" / "gsap.min.js").write_text("", encoding="utf-8")
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=3.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_tracks=[
            TextTrack(
                id="track-1",
                kind="keyword",
                name="keyword",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-1",
                text="<Pixelle & 字>",
                start=0.5,
                end=1.5,
                role="keyword",
                slot="center",
                layer=4,
            )
        ],
    )

    project_dir = tmp_path / "project"
    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=project_dir,
        context=context,
    )

    text_layer = (project_dir / "compositions" / "text_layer.html").read_text(
        encoding="utf-8"
    )

    assert "&lt;Pixelle &amp; 字&gt;" in text_layer
    assert 'data-start="0.5"' in text_layer
    assert 'data-duration="1.0"' in text_layer
    assert 'data-slot="center"' in text_layer
    assert 'data-layer="4"' in text_layer
    assert "text_tracks.json" not in text_layer


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


def test_phase1_templates_reference_local_font_entrypoint():
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
        assert "phase1_fonts.css" in content


def test_phase1_templates_mount_static_text_layer_composition():
    template_ids = ["image_default", "image_life_insights_light"]

    for template_id in template_ids:
        template_dir = Path("resources/hyperframes/templates") / template_id
        index_content = (template_dir / "index.template.html").read_text(
            encoding="utf-8"
        )
        text_layer_template = template_dir / "compositions" / "text_layer.template.html"

        assert 'data-composition-id="text-layer"' in index_content
        assert 'data-composition-src="compositions/text_layer.html"' in index_content
        assert text_layer_template.exists()
        assert "__TEXT_CUES__" in text_layer_template.read_text(encoding="utf-8")


def test_life_insights_caption_template_does_not_embed_hardcoded_english_label():
    content = Path(
        "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
    ).read_text(encoding="utf-8")

    assert "Key takeaway" not in content


def test_phase1_templates_reference_local_gsap_vendor_and_register_timelines():
    template_expectations = {
        Path("resources/hyperframes/templates/image_default/index.template.html"): (
            "./runtime/vendor/gsap.min.js",
            'window.__timelines["main-comp"]',
        ),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/index.template.html"
        ): (
            "./runtime/vendor/gsap.min.js",
            'window.__timelines["main-comp"]',
        ),
        Path(
            "resources/hyperframes/templates/image_default/compositions/captions.template.html"
        ): (
            "../runtime/vendor/gsap.min.js",
            'window.__timelines["captions"]',
        ),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
        ): (
            "../runtime/vendor/gsap.min.js",
            'window.__timelines["captions"]',
        ),
    }

    for path, (script_path, timeline_registration) in template_expectations.items():
        content = path.read_text(encoding="utf-8")
        assert script_path in content
        assert timeline_registration in content


def test_phase1_main_templates_keep_visual_materials_as_hard_cuts():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/index.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "visualClips.forEach" not in content
        assert 'tl.fromTo(\n            clip,' not in content
        assert 'tl.to(\n            clip,' not in content


def test_phase1_main_templates_show_shell_immediately_without_fade_motion():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/index.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert 'tl.fromTo(\n          ".video-title-wrapper"' not in content
        assert 'tl.fromTo(\n          ".footer"' not in content
        assert 'tl.fromTo(\n          ".header"' not in content
        assert 'tl.fromTo(\n          ".bottom-section"' not in content
        assert 'tl.fromTo(\n          ".author"' not in content


def test_phase1_caption_templates_use_hard_visibility_switches_without_fades():
    template_paths = [
        Path(
            "resources/hyperframes/templates/image_default/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
        ),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "fadeOutAt" not in content
        assert "tl.to(" not in content
        assert "tl.set(" in content


@pytest.mark.parametrize(
    "template_id",
    ["image_default", "image_life_insights_light"],
)
def test_phase1_caption_templates_compile_with_context_canvas_dimensions(
    tmp_path: Path,
    template_id: str,
):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id=template_id,
        canvas_width=720,
        canvas_height=1280,
        duration=6.0,
        fps=30,
        title="示例标题",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile=template_id,
        template_params={"author_desc": "LanRen"},
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=6.0,
                media_path="assets/images/01_image.png",
                media_type="image",
            )
        ],
        captions=[
            CaptionCue(
                id="c1",
                text="第一句字幕",
                start=0.0,
                end=2.0,
                frame_indices=[0],
                style_profile=template_id,
            )
        ],
        audio=TemplateAudioRef(path="assets/audio/master_audio.wav", duration=6.0),
    )

    project_dir = tmp_path / "task" / "hyperframes"
    compiler.compile(project_dir=project_dir, context=context)

    captions_html = (project_dir / "compositions" / "captions.html").read_text(
        encoding="utf-8"
    )

    assert 'data-width="720"' in captions_html
    assert 'data-height="1280"' in captions_html
    assert "width: 720px;" in captions_html
    assert "height: 1280px;" in captions_html


def test_phase1_templates_preserve_source_shell_regions():
    content = Path(
        "resources/hyperframes/templates/image_life_insights_light/index.template.html"
    ).read_text(encoding="utf-8")

    assert "bg-pattern" in content
    assert "header" in content
    assert "content" in content
    assert "bottom-section" in content
    assert "author" in content
