import pytest

from pixelle_video.models.render_package import CaptionCue, RenderManifest, TextCue, TextTrack, VisualClip
from pixelle_video.models.template_render_context import (
    PHASE1_TEMPLATE_FIELD_INVENTORY,
    TemplateAudioRef,
    TemplateRenderContext,
)
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID, TextStyleProfile
from pixelle_video.services.hyperframes_project_service import build_template_render_context


def test_template_render_context_uses_render_timeline_values():
    cue = CaptionCue(
        id="c1",
        text="一句话",
        start=0.1,
        end=1.5,
        frame_indices=[0],
        style_profile="image_default",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=10.0,
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
                start=0.1,
                end=1.5,
                media_path="assets/images/01_image.png",
                media_type="image",
            )
        ],
        captions=[cue],
        audio=TemplateAudioRef(path="assets/audio/master_audio.wav", duration=10.0),
    )

    assert context.visuals[0].start == 0.1
    assert context.captions[0].end == 1.5


def test_template_render_context_exposes_text_layer_fields():
    track = TextTrack(
        id="track-overlay",
        kind="overlay",
        name="重点词轨",
        renderer_targets=("hyperframes",),
    )
    cue = TextCue(
        id="cue-1",
        track_id="track-overlay",
        text="重点词",
        start=0.2,
        end=1.4,
        role="keyword",
        slot="center",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        text_tracks=[track],
        text_cues=[cue],
    )

    assert context.text_tracks[0].kind == "overlay"
    assert context.text_cues[0].text == "重点词"


def test_template_render_context_exposes_phase1_shell_fields():
    field_names = TemplateRenderContext.__dataclass_fields__.keys()

    assert "title" in field_names
    assert "author" in field_names
    assert "footer" in field_names
    assert "style_profile" in field_names
    assert "template_params" in field_names
    assert "title_style_profile" in field_names
    assert "template_title_region" in field_names
    assert "template_caption_safe_area" in field_names


def test_template_render_context_defaults_template_text_regions_from_preset():
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_landscape_minimal",
    )

    assert context.template_title_region == {
        "x": 0.055,
        "y": 0.085,
        "width": 0.44,
        "height": 0.20,
    }
    assert context.template_caption_safe_area == {
        "x": 0.18,
        "y": 0.69,
        "width": 0.64,
        "height": 0.17,
    }


def test_template_render_context_preserves_explicit_text_regions_and_title_profile():
    title_style_profile = TextStyleProfile(
        id=DEFAULT_TITLE_STYLE_ID,
        name="Title Default",
    )
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        title_style_profile=title_style_profile,
        template_title_region={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        template_caption_safe_area={
            "x": 0.2,
            "y": 0.3,
            "width": 0.4,
            "height": 0.5,
        },
    )

    assert context.title_style_profile is title_style_profile
    assert context.template_title_region == {
        "x": 0.1,
        "y": 0.2,
        "width": 0.3,
        "height": 0.4,
    }
    assert context.template_caption_safe_area == {
        "x": 0.2,
        "y": 0.3,
        "width": 0.4,
        "height": 0.5,
    }


def test_build_template_render_context_resolves_default_title_style_profile():
    title_profile = TextStyleProfile(
        id=DEFAULT_TITLE_STYLE_ID,
        name="Title Default",
        primary_color="#112233",
    )
    manifest = RenderManifest(
        task_id="task-title-style",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-yellow",
                name="Caption Yellow",
                primary_color="#FFFF00",
            ),
            title_profile,
        ],
    )

    context = build_template_render_context(manifest, template_params={})

    assert context.title_style_profile is title_profile


def test_template_render_context_derives_canvas_media_layout_from_sync_flag():
    context = TemplateRenderContext(
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_landscape_minimal",
        sync_media_size_to_canvas=True,
    )

    assert context.media_layout_mode == "canvas"


def test_template_render_context_defaults_media_placement():
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
    )

    assert context.media_placement.to_dict()["scale_percent"] == 100


def test_template_render_context_accepts_media_placement_dict():
    context = TemplateRenderContext(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
        duration=2.0,
        fps=30,
        title="demo",
        author=None,
        footer=None,
        theme=None,
        style_profile="image_default",
        media_placement={"scale_percent": 100, "anchor": "top"},
    )

    assert context.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "anchor": "top",
    }


def test_template_render_context_rejects_invalid_media_layout_mode():
    with pytest.raises(ValueError, match="media_layout_mode"):
        TemplateRenderContext(
            template_id="image_landscape_minimal",
            canvas_width=1280,
            canvas_height=720,
            duration=2.0,
            fps=30,
            title="demo",
            author=None,
            footer=None,
            theme=None,
            style_profile="image_landscape_minimal",
            media_layout_mode="stretch",
        )


def test_phase1_field_inventory_covers_required_shell_regions():
    required_regions = {
        "title_region",
        "media_slot",
        "subtitle_safe_area",
        "author_footer_region",
        "decorative_background",
        "style_profile",
    }

    assert {"image_default", "image_life_insights_light"} <= set(
        PHASE1_TEMPLATE_FIELD_INVENTORY.keys()
    )
    for mapping in PHASE1_TEMPLATE_FIELD_INVENTORY.values():
        assert required_regions <= set(mapping.keys())
