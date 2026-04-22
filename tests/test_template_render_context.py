from pixelle_video.models.render_package import CaptionCue, VisualClip
from pixelle_video.models.template_render_context import TemplateAudioRef, TemplateRenderContext


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
