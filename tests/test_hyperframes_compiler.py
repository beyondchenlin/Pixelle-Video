from pathlib import Path

import pytest

from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack, VisualClip
from pixelle_video.models.template_render_context import (
    PHASE1_TEMPLATE_FIELD_INVENTORY,
    TemplateAudioRef,
    TemplateRenderContext,
)
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID, TextStyleProfile
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
    assert 'class="clip pixelle-media-clip"' in index_html
    assert 'href="./runtime/fonts/phase1_fonts.css"' in index_html
    assert 'class="clip caption-group"' in captions_html
    assert 'href="../runtime/fonts/phase1_fonts.css"' in captions_html
    assert 'data-duration="12.5"' in captions_html
    assert (project_dir / "runtime" / "fonts" / "phase1_fonts.css").exists()


def test_hyperframes_compiler_emits_media_placement_variables(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        media_placement={"scale_percent": 80, "anchor": "center"},
        duration=6.0,
        fps=30,
        title="Landscape",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_minimal",
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=6.0,
                media_path="assets/images/01.png",
                media_type="image",
            )
        ],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--pixelle-media-display-width: 1024px" in index_html
    assert "--pixelle-media-display-height: 576px" in index_html
    assert "--pixelle-media-left: 128px" in index_html
    assert "--pixelle-media-top: 72px" in index_html
    assert "pixelle-media-layer" in index_html
    assert "visual-clip__media" not in index_html


def test_hyperframes_compiler_defaults_media_placement_variables_to_full_contain_fit(
    tmp_path: Path,
):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        duration=6.0,
        fps=30,
        title="Landscape",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_minimal",
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=6.0,
                media_path="assets/images/01.png",
                media_type="image",
            )
        ],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--pixelle-media-display-width: 1280px" in index_html
    assert "--pixelle-media-display-height: 720px" in index_html
    assert "--pixelle-media-left: 0px" in index_html
    assert "--pixelle-media-top: 0px" in index_html


def test_compiler_exposes_clip_level_element_animation_manifest_attribute(
    tmp_path: Path,
):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        "__VISUALS__",
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "text_layer.template.html").write_text(
        "__TEXT_CUES__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        visuals=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1,
                media_path="assets/images/source.png",
                media_type="image",
                element_animation_manifest_path='data/element"clip.json',
            )
        ],
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert (
        'data-element-animation-manifest="data/element&quot;clip.json"'
        in index_html
    )
    assert 'data/element"clip.json' not in index_html


def test_compiler_emits_declarative_audio_tracks_for_hyperframes_mixer(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    (template_root / "image_default" / "compositions").mkdir(parents=True)
    (template_root / "image_default" / "index.template.html").write_text(
        '<div data-composition-id="main" data-duration="__DURATION__">__AUDIO__</div>',
        encoding="utf-8",
    )
    (template_root / "image_default" / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
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
        audio_tracks=[
            TemplateAudioRef(
                id="narration-audio",
                path="assets/audio/master_audio.wav",
                duration=12.5,
                volume=1.0,
                role="narration",
            ),
            TemplateAudioRef(
                id="background-audio",
                path="assets/audio/background_audio.wav",
                duration=12.5,
                volume=0.35,
                role="background",
            ),
        ],
    )

    project_dir = tmp_path / "project"
    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=project_dir,
        context=context,
    )

    index_html = (project_dir / "index.html").read_text(encoding="utf-8")

    assert 'id="narration-audio"' in index_html
    assert 'id="background-audio"' in index_html
    assert 'src="assets/audio/background_audio.wav"' in index_html
    assert 'data-start="0.0"' in index_html
    assert 'data-end="12.5"' in index_html
    assert 'data-duration="12.5"' in index_html
    assert 'data-volume="0.35"' in index_html
    assert 'data-role="background"' in index_html


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
                text="5 < 6 & text",
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

    assert "5 &lt; 6 &amp; text" in text_layer
    assert 'data-start="0.5"' in text_layer
    assert 'data-duration="1.0"' in text_layer
    assert 'data-slot="center"' in text_layer
    assert 'data-layer="4"' in text_layer
    assert "text_tracks.json" not in text_layer


def test_hyperframes_compiler_emits_text_style_variables(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<div data-duration="__DURATION__">__TEXT_CUES__</div>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "text_layer.template.html").write_text(
        '<div id="text-layer">__TEXT_CUES__</div><script>__TEXT_TIMELINE__</script>',
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-yellow",
                name="Caption Yellow",
                primary_color="#FFFF00",
                background_color="#000000",
                background_opacity=0.5,
                position="bottom_right",
                alignment="right",
                margin_x=44,
                margin_y=56,
                max_width_ratio=0.4,
            )
        ],
        text_tracks=[
            TextTrack(
                id="overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("hyperframes",),
                style_profile="caption-yellow",
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="overlay",
                text="Important <b>text</b> & keep",
                start=0,
                end=1,
                role="keyword",
                slot="center",
            )
        ],
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(
        encoding="utf-8"
    )
    assert 'data-style-profile="caption-yellow"' in html
    assert "--text-fill: #FFFF00" in html
    assert "Important text &amp; keep" in html
    assert "<b>" not in html


def test_hyperframes_compiler_prefers_cue_style_over_track_style(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        "__TEXT_CUES__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "text_layer.template.html").write_text(
        "__TEXT_CUES__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="track-style",
                name="Track Style",
                primary_color="#FFFFFF",
            ),
            TextStyleProfile(
                id="cue-style",
                name="Cue Style",
                primary_color="#FFFF00",
            ),
        ],
        text_tracks=[
            TextTrack(
                id="overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("hyperframes",),
                style_profile="track-style",
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="overlay",
                text="Cue style",
                start=0,
                end=1,
                role="keyword",
                style_profile="cue-style",
            )
        ],
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(
        encoding="utf-8"
    )
    assert 'data-style-profile="cue-style"' in html
    assert "--text-fill: #FFFF00" in html
    assert 'data-style-profile="track-style"' not in html


def test_hyperframes_compiler_sanitizes_css_profile_values(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        "__TEXT_CUES__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "text_layer.template.html").write_text(
        "__TEXT_CUES__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="hostile-font",
                name="Hostile Font",
                font_family='Noto Sans"; background:url(javascript:alert(1)); /*',
                primary_color="#FFFF00",
            )
        ],
        text_tracks=[
            TextTrack(
                id="overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("hyperframes",),
                style_profile="hostile-font",
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="overlay",
                text="Safe text",
                start=0,
                end=1,
                role="keyword",
            )
        ],
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(
        encoding="utf-8"
    )
    assert "--text-fill: #FFFF00" in html
    assert "--text-stroke-color:" in html
    assert "--text-font-family: sans-serif" in html
    assert "javascript:" not in html
    assert "backgroundurl" not in html
    assert "/*" not in html
    assert "*/" not in html


def test_hyperframes_compiler_emits_caption_style_variables(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<div data-duration="__DURATION__">__CAPTIONS__</div>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        '<div id="captions">__CAPTIONS__</div>',
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-yellow",
                name="Caption Yellow",
                primary_color="#FFFF00",
                background_color="#000000",
                background_opacity=0.5,
                position="bottom_right",
                alignment="right",
                margin_x=44,
                margin_y=56,
                max_width_ratio=0.4,
            )
        ],
        captions=[
            CaptionCue(
                id="caption-1",
                text="Caption <b>text</b> & keep",
                start=0,
                end=1,
                style_profile="caption-yellow",
            )
        ],
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "compositions" / "captions.html").read_text(
        encoding="utf-8"
    )
    assert 'data-style-profile="caption-yellow"' in html
    assert "--text-fill: #FFFF00" in html
    assert "--text-background: rgba(0, 0, 0, 0.5)" in html
    assert "--text-right: 44px" in html
    assert "--text-bottom: 56px" in html
    assert "--text-text-align: right" in html
    assert "--text-max-width: 432px" in html
    assert "Caption text &amp; keep" in html
    assert "<b>" not in html


def test_phase1_caption_templates_consume_caption_style_variables():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/compositions/captions.template.html"),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_full/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html"
        ),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "var(--text-left)" in content
        assert "var(--text-right)" in content
        assert "var(--text-top)" in content
        assert "var(--text-bottom)" in content
        assert "var(--text-transform)" in content
        assert "var(--text-max-width)" in content
        assert "var(--text-text-align)" in content
        assert "var(--text-align-items)" in content
        assert "var(--text-fill)" in content
        assert "var(--text-font-family)" in content
        assert "var(--text-font-size)" in content
        assert "var(--text-font-weight)" in content
        assert "var(--text-line-height)" in content
        assert "var(--text-stroke-width)" in content
        assert "var(--text-stroke-color)" in content
        assert "var(--text-background)" in content


def test_hyperframes_compiler_emits_title_style_variables(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<h1 class="video-title" style="__TITLE_STYLE_CSS__">__TITLE__</h1>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    title_style = TextStyleProfile(
        id=DEFAULT_TITLE_STYLE_ID,
        name="Title Default",
        font_size=88,
        font_weight=800,
        primary_color="#112233",
        background_color="#FFFFFF",
        background_opacity=0.75,
        stroke_width=3,
        max_width_ratio=0.5,
        max_chars_per_line=5,
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="ABCDEFGHIJ<script>alert(1)</script>",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        title_style_profile=title_style,
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--title-fill: #112233" in html
    assert "--title-stroke-width: 3px" in html
    assert "--title-background: rgba(255, 255, 255, 0.75)" in html
    assert "--title-font-size: 88px" in html
    assert "--title-max-width: 540px" in html
    assert "--title-text-align: center" in html
    assert "ABCDEFGHIJ" not in html
    assert "ABCDE<br/>FGHIJ" in html
    assert "<script>" not in html
    assert "--text-fill" not in html


def test_hyperframes_compiler_emits_title_layout_variables(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<h1 class="video-title" style="__TITLE_STYLE_CSS__">__TITLE__</h1>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    title_style = TextStyleProfile(
        id=DEFAULT_TITLE_STYLE_ID,
        name="Title Default",
        font_size=88,
        position="bottom_right",
        alignment="right",
        margin_x=44,
        margin_y=56,
        max_width_ratio=0.4,
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Layout title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        title_style_profile=title_style,
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--title-left: auto" in html
    assert "--title-right: 44px" in html
    assert "--title-top: auto" in html
    assert "--title-bottom: 56px" in html
    assert "--title-transform: none" in html
    assert "--title-text-align: right" in html
    assert "--title-max-width: 432px" in html


def test_hyperframes_compiler_explicit_title_position_uses_canvas_edge_margins(
    tmp_path: Path,
):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_landscape_minimal"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<h1 class="video-title" style="__TITLE_STYLE_CSS__">__TITLE__</h1>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    title_style = TextStyleProfile(
        id=DEFAULT_TITLE_STYLE_ID,
        name="Title Default",
        font_size=88,
        position="bottom_right",
        alignment="right",
        margin_x=10,
        margin_y=20,
        max_width_ratio=1.0,
    )
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1000,
        canvas_height=500,
        duration=1,
        fps=30,
        title="Layout title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_landscape_minimal",
        title_style_profile=title_style,
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--title-left: auto" in html
    assert "--title-right: 10px" in html
    assert "--title-top: auto" in html
    assert "--title-bottom: 20px" in html
    assert "--title-box-width: 980px" in html
    assert "--title-max-width: 980px" in html


def test_hyperframes_compiler_emits_fallback_title_style_variables(tmp_path: Path):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<h1 class="video-title" style="__TITLE_STYLE_CSS__">__TITLE__</h1>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Fallback title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "__TITLE_STYLE_CSS__" not in html
    assert "--title-fill: #2C3E50" in html
    assert "--title-background: rgba(255, 255, 255, 0)" in html


def test_hyperframes_compiler_uses_fallback_title_profile_for_wrapping(
    tmp_path: Path,
):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<h1 class="video-title" style="__TITLE_STYLE_CSS__">__TITLE__</h1>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="ABCDEFGHIJKL",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "ABCDEFGHIJ<br/>KL" in html


def test_hyperframes_compiler_copies_custom_font_file_and_emits_font_face(
    tmp_path: Path,
):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    font_file = tmp_path / "fonts" / "simhei.ttf"
    (template_dir / "compositions").mkdir(parents=True)
    font_file.parent.mkdir(parents=True)
    font_file.write_bytes(b"font bytes")
    (template_dir / "index.template.html").write_text(
        "<style></style>__CAPTIONS__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "<style></style>__CAPTIONS__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-local-font",
                name="Caption Local Font",
                font_family="SimHei",
                font_file=str(font_file),
            )
        ],
        captions=[
            CaptionCue(
                id="caption-1",
                text="本地字体",
                start=0,
                end=1,
                style_profile="caption-local-font",
            )
        ],
    )

    project_dir = tmp_path / "project"
    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=project_dir,
        context=context,
    )

    copied_fonts = list((project_dir / "runtime" / "custom_fonts").glob("*.ttf"))
    captions_html = (project_dir / "compositions" / "captions.html").read_text(
        encoding="utf-8"
    )

    assert len(copied_fonts) == 1
    assert copied_fonts[0].read_bytes() == b"font bytes"
    assert '@font-face { font-family: "SimHei";' in captions_html
    assert "../runtime/custom_fonts/" in captions_html
    assert "--text-font-family: SimHei" in captions_html


def test_hyperframes_compiler_escapes_element_animation_manifest_attribute(
    tmp_path: Path,
):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "image_default"
    (template_dir / "compositions").mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<script src="__ELEMENT_ANIMATION_MANIFEST__"></script>',
        encoding="utf-8",
    )
    (template_dir / "compositions" / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )
    (template_dir / "compositions" / "text_layer.template.html").write_text(
        "__TEXT_CUES__",
        encoding="utf-8",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        element_animation_manifest_path='data/manifest" onerror="alert(1).json',
    )

    HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root).compile(
        project_dir=tmp_path / "project",
        context=context,
    )

    html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert 'src="data/manifest&quot; onerror=&quot;alert(1).json"' in html
    assert ' onerror="' not in html


def test_phase1_templates_do_not_depend_on_remote_fonts_or_cdn_scripts():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/index.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"),
        Path(
            "resources/hyperframes/templates/image_default/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_full/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html"
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
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"),
        Path(
            "resources/hyperframes/templates/image_default/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_full/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html"
        ),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "phase1_fonts.css" in content


def test_phase1_templates_mount_static_text_layer_composition():
    template_ids = ["image_default", "image_life_insights_light", "image_landscape_full", "image_landscape_minimal"]

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


@pytest.mark.parametrize(
    "template_id",
    [
        "image_default",
        "image_life_insights_light",
        "image_landscape_full",
        "image_landscape_minimal",
    ],
)
def test_phase1_main_templates_compile_with_title_style_variables(
    tmp_path: Path,
    template_id: str,
):
    title = f"Title for {template_id}"
    title_style = TextStyleProfile(
        id=DEFAULT_TITLE_STYLE_ID,
        name="Title Default",
        font_size=88,
        primary_color="#112233",
        background_color="#445566",
        background_opacity=0.5,
        max_chars_per_line=40,
    )
    context = TemplateRenderContext(
        template_id=template_id,
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title=title,
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile=template_id,
        template_params={"author_desc": "LanRen"},
        title_style_profile=title_style,
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0,
                end=1,
                media_path="assets/images/01.png",
                media_type="image",
            )
        ],
    )

    HyperFramesCompiler().compile(project_dir=tmp_path / template_id, context=context)

    html = (tmp_path / template_id / "index.html").read_text(encoding="utf-8")
    assert "__TITLE_STYLE_CSS__" not in html
    assert "--title-fill: #112233" in html
    assert "--title-background: rgba(68, 85, 102, 0.5)" in html
    assert "var(--title-fill)" in html
    assert "var(--title-font-size)" in html
    assert "var(--title-background)" in html
    assert "var(--title-left)" in html
    assert "var(--title-text-align)" in html
    assert title in html


def test_phase1_main_templates_consume_title_layout_variables():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/index.template.html"),
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "var(--title-left)" in content
        assert "var(--title-right)" in content
        assert "var(--title-top)" in content
        assert "var(--title-bottom)" in content
        assert "var(--title-transform)" in content
        assert "var(--title-box-width)" in content
        assert "var(--title-text-align)" in content
        assert "var(--title-justify-content)" in content
        assert "var(--title-align-items)" in content


def test_phase1_main_title_flex_axes_map_style_alignment_and_position():
    column_template = Path(
        "resources/hyperframes/templates/image_default/index.template.html"
    ).read_text(encoding="utf-8")
    row_templates = [
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"),
    ]

    assert "flex-direction: column;" in column_template
    assert "align-items: var(--title-justify-content);" in column_template
    assert "justify-content: var(--title-align-items);" in column_template

    for path in row_templates:
        content = path.read_text(encoding="utf-8")
        assert "align-items: var(--title-align-items)" in content
        assert "justify-content: var(--title-justify-content)" in content


def test_phase1_text_layer_templates_consume_text_style_variables():
    template_paths = [
        Path("resources/hyperframes/templates/image_default/compositions/text_layer.template.html"),
        Path(
            "resources/hyperframes/templates/image_life_insights_light/compositions/text_layer.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_full/compositions/text_layer.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html"
        ),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "var(--text-left)" in content
        assert "var(--text-right)" in content
        assert "var(--text-top)" in content
        assert "var(--text-bottom)" in content
        assert "var(--text-transform)" in content
        assert "var(--text-max-width)" in content
        assert "var(--text-text-align)" in content
        assert "var(--text-justify-content)" in content
        assert "var(--text-align-items)" in content
        assert "var(--text-background)" in content
        assert "var(--text-fill)" in content
        assert "var(--text-font-family)" in content
        assert "var(--text-font-size)" in content
        assert "var(--text-font-weight)" in content
        assert "var(--text-line-height)" in content
        assert "var(--text-stroke-width)" in content
        assert "var(--text-stroke-color)" in content


def test_phase1_main_templates_apply_title_background_to_visible_box():
    wrapper_selectors = {
        Path("resources/hyperframes/templates/image_default/index.template.html"): ".video-title-wrapper",
        Path("resources/hyperframes/templates/image_life_insights_light/index.template.html"): ".header",
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"): ".title",
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"): ".header",
    }

    for path, selector in wrapper_selectors.items():
        content = path.read_text(encoding="utf-8")
        selector_index = content.index(selector)
        rule_start = content.index("{", selector_index)
        rule_end = content.index("}", rule_start)
        wrapper_rule = content[rule_start:rule_end]

        assert "background: var(--title-background)" in wrapper_rule
        assert "background-clip: text" not in wrapper_rule
        assert "-webkit-background-clip: text" not in wrapper_rule
        assert "-webkit-text-fill-color" not in wrapper_rule


@pytest.mark.parametrize(
    ("template_id", "layout_consumer_marker", "expected_right", "expected_bottom"),
    [
        ("image_default", 'class="video-title-wrapper"', "44px", "56px"),
        ("image_life_insights_light", 'class="header"', "44px", "56px"),
        ("image_landscape_full", 'class="title"', "44px", "56px"),
        ("image_landscape_minimal", 'class="header"', "44px", "56px"),
    ],
)
def test_phase1_main_templates_inject_title_variables_on_layout_consumer(
    tmp_path: Path,
    template_id: str,
    layout_consumer_marker: str,
    expected_right: str,
    expected_bottom: str,
):
    context = TemplateRenderContext(
        template_id=template_id,
        canvas_width=1080,
        canvas_height=1920,
        duration=1,
        fps=30,
        title="Scoped layout title",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile=template_id,
        template_params={"author_desc": "LanRen"},
        title_style_profile=TextStyleProfile(
            id=DEFAULT_TITLE_STYLE_ID,
            name="Title Default",
            position="bottom_right",
            alignment="right",
            margin_x=44,
            margin_y=56,
            max_width_ratio=0.4,
            max_chars_per_line=40,
        ),
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0,
                end=1,
                media_path="assets/images/01.png",
                media_type="image",
            )
        ],
    )

    HyperFramesCompiler().compile(project_dir=tmp_path / template_id, context=context)

    html = (tmp_path / template_id / "index.html").read_text(encoding="utf-8")
    marker_index = html.index(layout_consumer_marker)
    tag_start = html.rfind("<", 0, marker_index)
    tag_end = html.index(">", marker_index)
    opening_tag = html[tag_start : tag_end + 1]

    assert f"--title-right: {expected_right}" in opening_tag
    assert f"--title-bottom: {expected_bottom}" in opening_tag
    assert "--title-text-align: right" in opening_tag


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
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"): (
            "./runtime/vendor/gsap.min.js",
            'window.__timelines["main-comp"]',
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/index.template.html"
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
        Path(
            "resources/hyperframes/templates/image_landscape_full/compositions/captions.template.html"
        ): (
            "../runtime/vendor/gsap.min.js",
            'window.__timelines["captions"]',
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html"
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
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"),
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
        Path("resources/hyperframes/templates/image_landscape_full/index.template.html"),
        Path("resources/hyperframes/templates/image_landscape_minimal/index.template.html"),
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
        Path(
            "resources/hyperframes/templates/image_landscape_full/compositions/captions.template.html"
        ),
        Path(
            "resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html"
        ),
    ]

    for path in template_paths:
        content = path.read_text(encoding="utf-8")
        assert "fadeOutAt" not in content
        assert "tl.to(" not in content
        assert "tl.set(" in content


@pytest.mark.parametrize(
    "template_id",
    ["image_default", "image_life_insights_light", "image_landscape_full", "image_landscape_minimal"],
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


def test_landscape_template_assets_and_inventory_exist():
    assert Path("templates/1920x1080/image_landscape_full.html").exists()
    assert Path("templates/1920x1080/image_landscape_minimal.html").exists()
    assert "image_landscape_full" in PHASE1_TEMPLATE_FIELD_INVENTORY
    assert "image_landscape_minimal" in PHASE1_TEMPLATE_FIELD_INVENTORY
    assert Path("resources/hyperframes/templates/image_landscape_full/text_capabilities.json").exists()
    assert Path("resources/hyperframes/templates/image_landscape_minimal/text_capabilities.json").exists()


def test_landscape_entry_templates_use_repo_local_font_assets():
    full_template = Path("templates/1920x1080/image_landscape_full.html").read_text(
        encoding="utf-8"
    )
    minimal_template = Path("templates/1920x1080/image_landscape_minimal.html").read_text(
        encoding="utf-8"
    )

    assert "@font-face" in full_template
    assert "@font-face" in minimal_template
    assert (
        "../../resources/hyperframes/runtime/fonts/assets/MaShanZheng-Regular.ttf"
        in full_template
    )
    assert (
        "../../resources/hyperframes/runtime/fonts/assets/NotoSansSC-wght.ttf"
        in full_template
    )
    assert (
        "../../resources/hyperframes/runtime/fonts/assets/NotoSansSC-wght.ttf"
        in minimal_template
    )
    assert "fonts.googleapis.com" not in full_template
    assert "fonts.gstatic.com" not in full_template
    assert "Noto Serif SC" not in minimal_template
    assert ".content-stage" in minimal_template
    assert ".subtitle-shell" in minimal_template
    assert "width: fit-content;" in minimal_template
    assert "max-width: min(840px, calc(100% - 220px));" in minimal_template
    assert "max-width: 520px;" not in minimal_template
    assert "font-weight: 900;" in minimal_template
    assert "background: linear-gradient(135deg" in minimal_template
    assert "width: min(560px, 100%);" in minimal_template
    assert "height: min(560px, calc(100% - 180px));" in minimal_template
    assert "width: min(860px, 100%);" in minimal_template


def test_image_landscape_full_template_uses_local_assets_and_raised_text_without_backplates():
    index_content = Path(
        "resources/hyperframes/templates/image_landscape_full/index.template.html"
    ).read_text(encoding="utf-8")
    captions_content = Path(
        "resources/hyperframes/templates/image_landscape_full/compositions/captions.template.html"
    ).read_text(encoding="utf-8")
    text_layer_content = Path(
        "resources/hyperframes/templates/image_landscape_full/compositions/text_layer.template.html"
    ).read_text(encoding="utf-8")

    assert "./runtime/fonts/phase1_fonts.css" in index_content
    assert "../runtime/fonts/phase1_fonts.css" in captions_content
    assert "./runtime/vendor/gsap.min.js" in index_content
    assert "../runtime/vendor/gsap.min.js" in captions_content
    assert "https://fonts.googleapis.com" not in index_content
    assert "https://cdnjs.cloudflare.com" not in captions_content
    assert 'window.__timelines["main-comp"]' in index_content
    assert "padTimelineToDuration(tl, duration);" in index_content
    assert "font-family: var(--title-font-family);" in index_content
    assert ".info-cluster" in index_content
    assert "left: 72px;" in index_content
    assert "bottom: 44px;" in index_content
    assert "__FOOTER__" in index_content
    assert "__AUTHOR__" in index_content
    assert "__AUTHOR_DESC__" in index_content
    assert "bottom: 260px" not in captions_content
    assert "bottom: 190px" not in captions_content
    assert "bottom: var(--text-bottom)" in captions_content
    assert "transform: var(--text-transform)" in captions_content
    assert "justify-content: var(--text-justify-content)" in captions_content
    assert "align-items: var(--text-align-items)" in captions_content
    assert "text-align: var(--text-text-align)" in captions_content
    assert "background: var(--text-background)" in captions_content
    assert "font-size: var(--text-font-size)" in captions_content
    assert "color: var(--text-fill)" in captions_content
    assert "font-family: var(--text-font-family)" in captions_content
    assert "left: var(--text-left)" in text_layer_content
    assert "top: var(--text-top)" in text_layer_content
    assert "font-size: var(--text-font-size)" in text_layer_content
    assert "color: var(--text-fill)" in text_layer_content
    assert "background: rgba(26, 37, 47, 0.78)" not in text_layer_content
    assert "top: 74%" not in text_layer_content


def test_image_landscape_minimal_template_uses_local_assets_and_raised_text_without_backplates():
    index_content = Path(
        "resources/hyperframes/templates/image_landscape_minimal/index.template.html"
    ).read_text(encoding="utf-8")
    captions_content = Path(
        "resources/hyperframes/templates/image_landscape_minimal/compositions/captions.template.html"
    ).read_text(encoding="utf-8")
    text_layer_content = Path(
        "resources/hyperframes/templates/image_landscape_minimal/compositions/text_layer.template.html"
    ).read_text(encoding="utf-8")

    assert "./runtime/fonts/phase1_fonts.css" in index_content
    assert "../runtime/fonts/phase1_fonts.css" in captions_content
    assert "./runtime/vendor/gsap.min.js" in index_content
    assert "../runtime/vendor/gsap.min.js" in captions_content
    assert "https://fonts.googleapis.com" not in index_content
    assert "https://cdnjs.cloudflare.com" not in captions_content
    assert 'window.__timelines["main-comp"]' in index_content
    assert "padTimelineToDuration(tl, duration);" in index_content
    assert ".minimal-line" in index_content
    assert ".circle" in index_content
    assert 'class="minimal-line line-1"' in index_content
    assert 'class="circle circle-2"' in index_content
    assert ".content-stage" in index_content
    assert "width: min(var(--title-box-width)" in index_content
    assert "max-width: var(--title-max-width);" in index_content
    assert "font-weight: var(--title-font-weight);" in index_content
    assert "background: var(--title-background);" in index_content
    assert "background: linear-gradient(135deg" not in index_content
    assert "width: min(560px, 100%);" in index_content
    assert "height: min(560px, calc(100% - 180px));" in index_content
    assert ".signature" in index_content
    assert "right: 72px;" in index_content
    assert "bottom: 48px;" in index_content
    assert "__FOOTER__" in index_content
    assert "__AUTHOR__" in index_content
    assert "__AUTHOR_DESC__" in index_content
    assert "left: 520px;" not in captions_content
    assert "right: 280px;" not in captions_content
    assert "inset: 154px 180px 116px 180px;" not in captions_content
    assert "left: var(--text-left)" in captions_content
    assert "right: var(--text-right)" in captions_content
    assert "top: var(--text-top)" in captions_content
    assert "bottom: var(--text-bottom)" in captions_content
    assert "width: min(var(--text-max-width)" in captions_content
    assert "justify-content: var(--text-justify-content)" in captions_content
    assert "align-items: var(--text-align-items)" in captions_content
    assert "text-align: var(--text-text-align)" in captions_content
    assert "background: var(--text-background)" in captions_content
    assert "font-size: var(--text-font-size)" in captions_content
    assert "color: var(--text-fill)" in captions_content
    assert "font-family: var(--text-font-family)" in captions_content
    assert "left: var(--text-left)" in text_layer_content
    assert "top: var(--text-top)" in text_layer_content
    assert "font-size: var(--text-font-size)" in text_layer_content
    assert "color: var(--text-fill)" in text_layer_content
    assert "background: rgba(26, 37, 47, 0.78)" not in text_layer_content
    assert "top: 74%" not in text_layer_content


def test_legacy_image_landscape_minimal_template_uses_standard_media_layer():
    legacy_content = Path("templates/1920x1080/image_landscape_minimal.html").read_text(
        encoding="utf-8"
    )

    assert "{{pixelle_media_layer}}" in legacy_content
    assert "{{image}}" not in legacy_content


def test_image_landscape_full_template_compiles_with_1920x1080_canvas(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_full",
        canvas_width=1920,
        canvas_height=1080,
        duration=6.0,
        fps=30,
        title="横屏示例",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_full",
        template_params={"author_desc": "Landscape"},
        visuals=[VisualClip(id="v1", frame_index=0, start=0.0, end=6.0, media_path="assets/images/01.png", media_type="image")],
        captions=[CaptionCue(id="c1", text="横屏字幕", start=0.0, end=2.0, frame_indices=[0], style_profile="image_landscape_full")],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    captions_html = (tmp_path / "project" / "compositions" / "captions.html").read_text(encoding="utf-8")
    text_layer_html = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(encoding="utf-8")
    assert 'data-width="1920"' in captions_html
    assert 'data-height="1080"' in captions_html
    assert "width: 1920px;" in text_layer_html
    assert "height: 1080px;" in text_layer_html


def test_image_landscape_minimal_template_compiles_with_1920x1080_canvas(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
        duration=6.0,
        fps=30,
        title="横屏示例",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_minimal",
        template_params={"author_desc": "Landscape"},
        visuals=[VisualClip(id="v1", frame_index=0, start=0.0, end=6.0, media_path="assets/images/01.png", media_type="image")],
        captions=[CaptionCue(id="c1", text="横屏字幕", start=0.0, end=2.0, frame_indices=[0], style_profile="image_landscape_minimal")],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    captions_html = (tmp_path / "project" / "compositions" / "captions.html").read_text(encoding="utf-8")
    text_layer_html = (tmp_path / "project" / "compositions" / "text_layer.html").read_text(encoding="utf-8")
    assert 'data-width="1920"' in captions_html
    assert 'data-height="1080"' in captions_html
    assert "width: 1920px;" in text_layer_html
    assert "height: 1080px;" in text_layer_html


def test_image_landscape_minimal_template_expands_visual_when_media_syncs_to_canvas(tmp_path: Path):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        sync_media_size_to_canvas=True,
        media_layout_mode="canvas",
        duration=6.0,
        fps=30,
        title="Landscape",
        author="LanRen.AI",
        footer="LanRen",
        theme=None,
        style_profile="image_landscape_minimal",
        template_params={"author_desc": "Landscape"},
        visuals=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=6.0,
                media_path="assets/images/01.png",
                media_type="image",
            )
        ],
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert "--pixelle-media-display-width: 1280px" in index_html
    assert "--pixelle-media-display-height: 720px" in index_html
    assert "--pixelle-media-left: 0px" in index_html
    assert "--pixelle-media-top: 0px" in index_html
    assert 'class="clip pixelle-media-clip"' in index_html


def _layered_template_spec_payload(**overrides):
    payload = {
        "version": "layered_template.v1",
        "template_id": "user:portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 48, "y": 48, "width": 624, "height": 1184, "unit": "px"},
        "layers": [
            {
                "id": "background",
                "type": "background",
                "name": "Background",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 0,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {"kind": "color", "ref": "#FAF4E8", "metadata": {}},
                "style": {},
                "role": None,
            },
            {
                "id": "media",
                "type": "generated_media",
                "name": "Generated media",
                "rect": {"x": 60, "y": 220, "width": 600, "height": 760, "unit": "px"},
                "z_index": 10,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://primary",
                    "metadata": {},
                },
                "style": {"object_fit": "contain"},
                "role": None,
            },
            {
                "id": "title",
                "type": "text",
                "name": "Title",
                "rect": {"x": 60, "y": 72, "width": 600, "height": 120, "unit": "px"},
                "z_index": 20,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": None,
                "style": {"font_size": 42, "primary_color": "#1F2937", "alignment": "center"},
                "role": "title",
            },
            {
                "id": "caption",
                "type": "text",
                "name": "Caption",
                "rect": {"x": 84, "y": 1020, "width": 552, "height": 120, "unit": "px"},
                "z_index": 30,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": None,
                "style": {"font_size": 28, "primary_color": "#111827", "alignment": "center"},
                "role": "caption",
            },
        ],
        "metadata": {"orientation": "portrait"},
    }
    payload.update(overrides)
    return payload


def test_hyperframes_compiler_ignores_empty_layered_template_spec(
    tmp_path: Path,
):
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    (template_root / "image_landscape_minimal" / "compositions").mkdir(parents=True)
    (runtime_root / "fonts").mkdir(parents=True)
    (template_root / "image_landscape_minimal" / "index.template.html").write_text(
        (
            '<main data-width="__CANVAS_WIDTH__" data-height="__CANVAS_HEIGHT__">'
            "<h1>__TITLE__</h1>"
            '<section class="visuals">__VISUALS__</section>'
            '<section class="captions">__CAPTIONS__</section>'
            "</main>"
        ),
        encoding="utf-8",
    )
    (
        template_root
        / "image_landscape_minimal"
        / "compositions"
        / "captions.template.html"
    ).write_text(
        '<div class="caption-root">__CAPTIONS__</div>',
        encoding="utf-8",
    )
    (runtime_root / "fonts" / "phase1_fonts.css").write_text(
        ":root { --hf-font-sans: sans-serif; }",
        encoding="utf-8",
    )
    empty_spec = _layered_template_spec_payload(
        template_id="system:1920x1080/image_landscape_minimal.html",
        template_name="image_landscape_minimal.html",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        safe_area={"x": 0, "y": 0, "width": 1280, "height": 720, "unit": "px"},
        layers=[],
        metadata={},
    )
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        duration=3.0,
        fps=30,
        title="Moon title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_landscape_minimal",
        layered_template_spec=empty_spec,
        visuals=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0.0,
                end=3.0,
                media_path="assets/images/01_image.png",
                media_type="image",
            )
        ],
        captions=[
            CaptionCue(
                id="caption-1",
                text="Moon caption",
                start=0.0,
                end=3.0,
                frame_indices=[0],
                style_profile="caption-default",
            )
        ],
    )

    compiler = HyperFramesCompiler(template_root=template_root, runtime_root=runtime_root)
    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    captions_html = (tmp_path / "project" / "compositions" / "captions.html").read_text(
        encoding="utf-8"
    )

    assert "pixelle-generated-media-slot" not in index_html
    assert "Moon title" in index_html
    assert 'src="assets/images/01_image.png"' in index_html
    assert 'class="clip pixelle-media-clip"' in index_html
    assert "Moon caption" in captions_html


def test_hyperframes_compiler_uses_layered_template_adapter_when_spec_present(
    tmp_path: Path,
):
    compiler = HyperFramesCompiler()
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=720,
        canvas_height=1280,
        duration=3.0,
        fps=30,
        title="Layered title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        layered_template_spec=_layered_template_spec_payload(),
        visuals=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0.0,
                end=3.0,
                media_path="assets/images/layered-source.png",
                media_type="image",
            )
        ],
        captions=[
            CaptionCue(
                id="caption-1",
                text="Layered caption",
                start=0.0,
                end=3.0,
                frame_indices=[0],
                style_profile="image_default",
            )
        ],
        audio=TemplateAudioRef(path="assets/audio/master_audio.wav", duration=3.0),
    )

    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    captions_html = (tmp_path / "project" / "compositions" / "captions.html").read_text(
        encoding="utf-8"
    )

    assert "pixelle-generated-media-slot" in index_html
    assert "Layered title" in index_html
    assert 'src="assets/images/layered-source.png"' in index_html
    assert 'data-composition-src="compositions/captions.html"' in index_html
    assert 'data-composition-src="compositions/text_layer.html"' in index_html
    assert 'window.__timelines["main-comp"]' in index_html
    assert "Layered caption" in captions_html


def test_hyperframes_compiler_rejects_unsupported_generated_media_ref_for_layered_spec(
    tmp_path: Path,
):
    compiler = HyperFramesCompiler()
    spec = _layered_template_spec_payload()
    spec["layers"][1]["source"]["ref"] = "generated://secondary"
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=720,
        canvas_height=1280,
        duration=3.0,
        fps=30,
        title="Layered title",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        layered_template_spec=spec,
        visuals=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0.0,
                end=3.0,
                media_path="assets/images/layered-source.png",
                media_type="image",
            )
        ],
    )

    with pytest.raises(ValueError, match="unsupported generated-media ref"):
        compiler.compile(project_dir=tmp_path / "project", context=context)
