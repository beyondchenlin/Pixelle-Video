from pixelle_video.models.render_package import CaptionCue, TextCue, TextTrack, VisualClip
from pixelle_video.models.template_render_context import (
    PHASE1_TEMPLATE_FIELD_INVENTORY,
    TemplateAudioRef,
    TemplateRenderContext,
)


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
