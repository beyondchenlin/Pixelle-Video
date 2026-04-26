import json

import pytest

from pixelle_video.models.render_package import (
    AudioBlock,
    CaptionCue,
    RenderAudioTrack,
    RenderManifest,
    SentenceUnit,
    TextCue,
    TextTrack,
    VisualClip,
)
from pixelle_video.models.text_style import DEFAULT_CAPTION_STYLE_ID, TextStyleProfile
from pixelle_video.services.hyperframes_project_service import (
    HyperFramesProjectService,
    build_template_render_context,
)


def test_write_project_data_writes_manifest_and_captions_files(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        master_audio_path="output/task-1/master_audio.wav",
        audio_blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1. Sentence 2.",
                audio_path="output/task-1/block-1.wav",
                start=0.0,
                end=3.5,
                source_frame_indices=[0, 1],
            )
        ],
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.0,
                source_end=1.7,
                remapped_start=0.0,
                remapped_end=1.5,
            )
        ],
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0.0,
                end=1.5,
                media_path="output/task-1/frames/01_composed.png",
                media_type="image",
            )
        ],
        caption_cues=[
            CaptionCue(
                id="caption-1",
                text="Sentence 1",
                start=0.0,
                end=1.5,
                frame_indices=[0],
                style_profile="image_life_insights_light",
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))

    project_paths = service.write_project_data(manifest)
    manifest_path = project_paths.data_dir / "render_manifest.json"
    captions_path = project_paths.data_dir / "captions.json"

    assert manifest_path.exists()
    assert captions_path.exists()
    assert project_paths.manifest_path == manifest_path

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    captions_data = json.loads(captions_path.read_text(encoding="utf-8"))

    assert manifest_data["task_id"] == "task-1"
    assert captions_data["task_id"] == "task-1"
    assert captions_data["captions"][0]["text"] == "Sentence 1"
    assert not (project_paths.data_dir / "render-manifest.json").exists()


def test_write_project_data_writes_text_tracks_diagnostic_payload(tmp_path):
    manifest = RenderManifest(
        task_id="task-text",
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
            )
        ],
        text_tracks=[
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="重点词轨",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="重点词",
                start=0.2,
                end=1.4,
                role="keyword",
                slot="center",
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project_data(manifest)

    text_tracks_path = project_paths.data_dir / "text_tracks.json"
    text_tracks_data = json.loads(text_tracks_path.read_text(encoding="utf-8"))
    manifest_data = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))

    assert text_tracks_path.exists()
    assert text_tracks_data["task_id"] == "task-text"
    assert text_tracks_data["text_style_profiles"][0]["id"] == "caption-yellow"
    assert text_tracks_data["text_style_profiles"][0]["primary_color"] == "#FFFF00"
    assert text_tracks_data["text_tracks"][0]["kind"] == "overlay"
    assert text_tracks_data["text_cues"][0]["role"] == "keyword"
    assert manifest_data["text_tracks"][0]["id"] == "track-overlay"


def test_write_project_data_clamps_text_cues_to_manifest_duration(tmp_path):
    manifest = RenderManifest(
        task_id="task-text-clamp",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_duration=2.0,
        text_tracks=[
            TextTrack(
                id="track-keyword",
                kind="keyword",
                name="keyword",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-keyword",
                text="重点",
                start=1.0,
                end=4.0,
                role="keyword",
                slot="center",
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project_data(manifest, master_audio_duration=2.0)
    text_tracks_data = json.loads(
        project_paths.text_tracks_path.read_text(encoding="utf-8")
    )

    assert text_tracks_data["text_cues"][0]["start"] == 1.0
    assert text_tracks_data["text_cues"][0]["end"] == 2.0


def test_write_project_data_rejects_unknown_text_slot(tmp_path):
    manifest = RenderManifest(
        task_id="task-text-slot",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_duration=2.0,
        text_tracks=[
            TextTrack(
                id="track-keyword",
                kind="keyword",
                name="keyword",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-keyword",
                text="重点",
                start=0.0,
                end=1.0,
                role="keyword",
                slot="unknown",
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))

    with pytest.raises(ValueError, match="unsupported text slot"):
        service.write_project_data(manifest, master_audio_duration=2.0)


def test_build_template_render_context_prefers_remapped_timing_when_present():
    sentences = [
        SentenceUnit(
            id="s1",
            text="第一句",
            frame_indices=[0],
            block_id="block-1",
            source_start=0.3,
            source_end=2.8,
            remapped_start=0.1,
            remapped_end=2.2,
        )
    ]
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_default",
        master_audio_path="assets/audio/master_audio.wav",
        master_audio_duration=3.0,
        sentence_units=sentences,
        visual_clips=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.1,
                end=2.2,
                media_path="assets/images/01_image.png",
                media_type="image",
            )
        ],
    )

    context = build_template_render_context(
        manifest,
        template_params={"author": "demo", "footer": "LanRen"},
    )

    assert context.duration == 3.0
    assert context.audio.path == "assets/audio/master_audio.wav"
    assert context.captions[0].start == 0.1
    assert context.captions[0].end == 2.2


def test_build_template_render_context_carries_declarative_audio_tracks():
    manifest = RenderManifest(
        task_id="task-audio-context",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        master_audio_duration=4.0,
        audio_tracks=[
            RenderAudioTrack(
                id="narration-audio",
                path="assets/audio/master_audio.wav",
                start=0.0,
                end=4.0,
                volume=1.0,
                role="narration",
            ),
            RenderAudioTrack(
                id="background-audio",
                path="assets/audio/background_audio.wav",
                start=0.0,
                end=4.0,
                volume=0.25,
                role="background",
            ),
        ],
    )

    context = build_template_render_context(manifest, template_params={})

    assert [track.id for track in context.audio_tracks] == [
        "narration-audio",
        "background-audio",
    ]
    assert context.audio_tracks[1].path == "assets/audio/background_audio.wav"
    assert context.audio_tracks[1].volume == pytest.approx(0.25)
    assert context.audio_tracks[1].role == "background"


def test_build_template_render_context_derives_duration_from_audio_tracks():
    manifest = RenderManifest(
        task_id="task-audio-duration",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        audio_tracks=[
            RenderAudioTrack(
                id="background-audio",
                path="assets/audio/background_audio.wav",
                start=1.0,
                end=4.5,
                volume=0.25,
                role="background",
            ),
        ],
    )

    context = build_template_render_context(manifest, template_params={})

    assert context.duration == pytest.approx(4.5)
    assert context.audio_tracks[0].duration == pytest.approx(3.5)


def test_build_template_render_context_carries_text_layer_from_manifest():
    manifest = RenderManifest(
        task_id="task-context",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_tracks=[
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="重点词轨",
                renderer_targets=("hyperframes",),
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="重点词",
                start=0.2,
                end=1.4,
                role="keyword",
                slot="center",
            )
        ],
    )

    context = build_template_render_context(manifest, template_params={})

    assert context.text_tracks[0].id == "track-overlay"
    assert context.text_cues[0].slot == "center"
    assert context.duration == 1.4


def test_build_template_render_context_carries_text_style_profiles():
    manifest = RenderManifest(
        task_id="task-context-styles",
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
            )
        ],
    )

    context = build_template_render_context(manifest, template_params={})

    assert context.text_style_profiles[0].id == "caption-yellow"
    assert context.text_style_profiles[0].primary_color == "#FFFF00"


def test_write_project_data_keeps_audio_tracks_when_duration_comes_from_tracks(tmp_path):
    manifest = RenderManifest(
        task_id="task-audio-track-only",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        audio_tracks=[
            RenderAudioTrack(
                id="background-audio",
                path="assets/audio/background_audio.wav",
                start=0.0,
                end=4.0,
                volume=0.25,
                role="background",
            ),
        ],
    )

    project_paths = HyperFramesProjectService(output_dir=str(tmp_path)).write_project_data(
        manifest,
    )
    manifest_data = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))

    assert manifest_data["audio_tracks"][0]["id"] == "background-audio"
    assert manifest_data["audio_tracks"][0]["end"] == pytest.approx(4.0)


def test_write_project_materializes_local_assets_and_compiles_static_html(tmp_path):
    source_audio = tmp_path / "master_audio.wav"
    source_image = tmp_path / "01_image.png"
    source_audio.write_bytes(b"wav")
    source_image.write_bytes(b"png")

    manifest = RenderManifest(
        task_id="task-compiled",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_default",
        master_audio_path=str(source_audio),
        master_audio_duration=3.0,
        sentence_units=[
            SentenceUnit(
                id="s1",
                text="第一句",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.0,
                source_end=1.2,
                remapped_start=0.1,
                remapped_end=1.0,
            )
        ],
        visual_clips=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.1,
                end=1.0,
                media_path=str(source_image),
                media_type="image",
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project(
        manifest,
        template_params={"author": "demo", "footer": "LanRen"},
    )

    index_html = (project_paths.project_dir / "index.html").read_text(encoding="utf-8")
    manifest_data = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))

    assert (project_paths.project_dir / "assets" / "audio" / "master_audio.wav").exists()
    assert (project_paths.project_dir / "assets" / "images" / "01_image.png").exists()
    assert 'src="assets/audio/master_audio.wav"' in index_html
    assert 'src="assets/images/01_image.png"' in index_html
    assert manifest_data["master_audio_path"] == "assets/audio/master_audio.wav"
    assert manifest_data["visual_clips"][0]["media_path"] == "assets/images/01_image.png"


def test_write_project_materializes_declarative_audio_tracks(tmp_path):
    source_master_audio = tmp_path / "master_audio.wav"
    source_bgm_audio = tmp_path / "background_audio.wav"
    source_master_audio.write_bytes(b"master")
    source_bgm_audio.write_bytes(b"bgm")

    manifest = RenderManifest(
        task_id="task-audio-tracks",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="image_default",
        master_audio_duration=3.0,
        audio_tracks=[
            RenderAudioTrack(
                id="narration-audio",
                path=str(source_master_audio),
                start=0.0,
                end=3.0,
                volume=1.0,
                role="narration",
            ),
            RenderAudioTrack(
                id="background-audio",
                path=str(source_bgm_audio),
                start=0.0,
                end=3.0,
                volume=0.35,
                role="background",
            ),
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project(manifest, template_params={})
    manifest_data = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))
    index_html = (project_paths.project_dir / "index.html").read_text(encoding="utf-8")

    assert (project_paths.project_dir / "assets" / "audio" / "master_audio.wav").exists()
    assert (project_paths.project_dir / "assets" / "audio" / "background_audio.wav").exists()
    assert manifest_data["audio_tracks"][0]["path"] == "assets/audio/master_audio.wav"
    assert manifest_data["audio_tracks"][1]["path"] == "assets/audio/background_audio.wav"
    assert 'src="assets/audio/background_audio.wav"' in index_html
    assert 'data-volume="0.35"' in index_html


def test_write_project_materializes_element_animation_manifest_and_assets(tmp_path):
    source_image = tmp_path / "source.png"
    background_image = tmp_path / "background.png"
    element_image = tmp_path / "element.png"
    mask_image = tmp_path / "mask.png"
    for path in (source_image, background_image, element_image, mask_image):
        path.write_bytes(b"png")

    element_manifest_path = tmp_path / "element_manifest.json"
    element_manifest_path.write_text(
        json.dumps(
            {
                "source_image_path": str(source_image),
                "background": {"image_path": str(background_image)},
                "audio_path": "remote/audio/not-localized.wav",
                "elements": [
                    {
                        "id": "element-1",
                        "image_path": str(element_image),
                        "mask_path": str(mask_image),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = RenderManifest(
        task_id="task-element-animation",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="image_default",
        element_animation_manifest_path=str(element_manifest_path),
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project(manifest, template_params={})

    localized_manifest_path = project_paths.data_dir / "element_animation_manifest.json"
    localized_asset_dir = project_paths.project_dir / "assets" / "element_animation"
    localized_element_manifest = json.loads(
        localized_manifest_path.read_text(encoding="utf-8")
    )
    render_manifest = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))

    assert localized_manifest_path.exists()
    assert (localized_asset_dir / "source.png").exists()
    assert (localized_asset_dir / "background.png").exists()
    assert (localized_asset_dir / "element.png").exists()
    assert (localized_asset_dir / "mask.png").exists()
    assert (
        localized_element_manifest["source_image_path"]
        == "assets/element_animation/source.png"
    )
    assert (
        localized_element_manifest["background"]["image_path"]
        == "assets/element_animation/background.png"
    )
    assert (
        localized_element_manifest["elements"][0]["image_path"]
        == "assets/element_animation/element.png"
    )
    assert (
        localized_element_manifest["elements"][0]["mask_path"]
        == "assets/element_animation/mask.png"
    )
    assert localized_element_manifest["audio_path"] == "remote/audio/not-localized.wav"
    assert (
        render_manifest["element_animation_manifest_path"]
        == "data/element_animation_manifest.json"
    )


def test_write_project_materializes_clip_level_element_animation_manifest(tmp_path):
    source_image = tmp_path / "source.png"
    source_image.write_bytes(b"png")
    element_manifest_path = tmp_path / "element_manifest.json"
    element_manifest_path.write_text(
        json.dumps(
            {
                "source_image_path": str(source_image),
                "canvas": {"width": 1080, "height": 1920},
                "timeline": {"duration": 1.0, "fps": 30},
                "background": {
                    "mode": "source_image_low_motion",
                    "image_path": str(source_image),
                },
                "segmentation": {
                    "provider": "test",
                    "workflow": "test.json",
                    "prompt": None,
                    "candidate_limit": 1,
                    "selected_count": 1,
                },
                "elements": [],
                "render": {"backend": "hyperframes_canvas"},
                "audio_path": None,
            }
        ),
        encoding="utf-8",
    )

    manifest = RenderManifest(
        task_id="task-clip-element",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="image_default",
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=0,
                end=1,
                media_path=str(source_image),
                media_type="image",
                element_animation_manifest_path=str(element_manifest_path),
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project(manifest, template_params={})
    render_manifest = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))
    localized_manifest_path = (
        project_paths.data_dir
        / "element_animation"
        / "element_animation_clip-1.json"
    )
    localized_element_manifest = json.loads(
        localized_manifest_path.read_text(encoding="utf-8")
    )

    assert (
        render_manifest["visual_clips"][0]["element_animation_manifest_path"]
        == "data/element_animation/element_animation_clip-1.json"
    )
    assert localized_manifest_path.exists()
    assert localized_element_manifest["source_image_path"].startswith(
        "assets/element_animation/element_animation_clip-1/"
    )


def test_write_project_uses_unique_element_animation_asset_names_for_basename_collisions(tmp_path):
    source_image = tmp_path / "source.png"
    background_image = tmp_path / "background.png"
    element_image = tmp_path / "element.png"
    first_mask_dir = tmp_path / "first"
    second_mask_dir = tmp_path / "second"
    first_mask_dir.mkdir()
    second_mask_dir.mkdir()
    first_mask = first_mask_dir / "mask.png"
    second_mask = second_mask_dir / "mask.png"
    for path in (source_image, background_image, element_image, first_mask, second_mask):
        path.write_bytes(path.parent.name.encode("utf-8"))

    element_manifest_path = tmp_path / "element_manifest.json"
    element_manifest_path.write_text(
        json.dumps(
            {
                "source_image_path": str(source_image),
                "background": {"image_path": str(background_image)},
                "elements": [
                    {
                        "id": "element-1",
                        "image_path": str(element_image),
                        "mask_path": str(first_mask),
                    },
                    {
                        "id": "element-2",
                        "image_path": str(element_image),
                        "mask_path": str(second_mask),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = RenderManifest(
        task_id="task-element-animation-collision",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="image_default",
        element_animation_manifest_path=str(element_manifest_path),
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project(manifest, template_params={})
    localized_element_manifest = json.loads(
        (project_paths.data_dir / "element_animation_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    first_localized_mask = localized_element_manifest["elements"][0]["mask_path"]
    second_localized_mask = localized_element_manifest["elements"][1]["mask_path"]
    repeated_element_image = localized_element_manifest["elements"][1]["image_path"]

    assert first_localized_mask == "assets/element_animation/mask.png"
    assert second_localized_mask.startswith("assets/element_animation/mask_")
    assert second_localized_mask.endswith(".png")
    assert first_localized_mask != second_localized_mask
    assert (
        repeated_element_image
        == localized_element_manifest["elements"][0]["image_path"]
    )
    assert (project_paths.project_dir / first_localized_mask).exists()
    assert (project_paths.project_dir / second_localized_mask).exists()


def test_write_project_uses_unique_element_animation_asset_names_for_case_collisions(tmp_path):
    source_image = tmp_path / "source.png"
    background_image = tmp_path / "background.png"
    element_image = tmp_path / "element.png"
    first_mask_dir = tmp_path / "first"
    second_mask_dir = tmp_path / "second"
    first_mask_dir.mkdir()
    second_mask_dir.mkdir()
    first_mask = first_mask_dir / "Mask.png"
    second_mask = second_mask_dir / "mask.png"
    source_image.write_bytes(b"source")
    background_image.write_bytes(b"background")
    element_image.write_bytes(b"element")
    first_mask.write_bytes(b"first-mask")
    second_mask.write_bytes(b"second-mask")

    element_manifest_path = tmp_path / "element_manifest.json"
    element_manifest_path.write_text(
        json.dumps(
            {
                "source_image_path": str(source_image),
                "background": {"image_path": str(background_image)},
                "elements": [
                    {
                        "id": "element-1",
                        "image_path": str(element_image),
                        "mask_path": str(first_mask),
                    },
                    {
                        "id": "element-2",
                        "image_path": str(element_image),
                        "mask_path": str(second_mask),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = RenderManifest(
        task_id="task-element-animation-case-collision",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="image_default",
        element_animation_manifest_path=str(element_manifest_path),
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project(manifest, template_params={})
    localized_element_manifest = json.loads(
        (project_paths.data_dir / "element_animation_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    first_localized_mask = localized_element_manifest["elements"][0]["mask_path"]
    second_localized_mask = localized_element_manifest["elements"][1]["mask_path"]

    assert first_localized_mask == "assets/element_animation/Mask.png"
    assert second_localized_mask.startswith("assets/element_animation/mask_")
    assert second_localized_mask.endswith(".png")
    assert first_localized_mask != second_localized_mask
    assert (project_paths.project_dir / first_localized_mask).read_bytes() == b"first-mask"
    assert (project_paths.project_dir / second_localized_mask).read_bytes() == b"second-mask"


def test_write_project_clears_missing_element_animation_manifest_path(tmp_path):
    from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler

    missing_element_manifest_path = tmp_path / "missing_element_manifest.json"
    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "element_template"
    compositions_dir = template_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<script src="__ELEMENT_ANIMATION_MANIFEST__"></script>',
        encoding="utf-8",
    )
    (compositions_dir / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )

    manifest = RenderManifest(
        task_id="task-missing-element-animation",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="element_template",
        element_animation_manifest_path=str(missing_element_manifest_path),
    )

    service = HyperFramesProjectService(
        output_dir=str(tmp_path),
        compiler=HyperFramesCompiler(
            template_root=template_root,
            runtime_root=runtime_root,
        ),
    )
    project_paths = service.write_project(manifest, template_params={})
    render_manifest = json.loads(project_paths.manifest_path.read_text(encoding="utf-8"))
    element_asset_dir = project_paths.project_dir / "assets" / "element_animation"
    index_html = (project_paths.project_dir / "index.html").read_text(encoding="utf-8")

    assert not (project_paths.data_dir / "element_animation_manifest.json").exists()
    assert not element_asset_dir.exists() or not any(element_asset_dir.iterdir())
    assert "element_animation_manifest_path" not in render_manifest
    assert str(missing_element_manifest_path) not in index_html
    assert 'src=""' in index_html


def test_build_template_render_context_carries_element_animation_manifest_path():
    manifest = RenderManifest(
        task_id="task-element-context",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="image_default",
        element_animation_manifest_path="data/element_animation_manifest.json",
    )

    context = build_template_render_context(manifest, template_params={})

    assert (
        context.element_animation_manifest_path
        == "data/element_animation_manifest.json"
    )


def test_hyperframes_compiler_replaces_element_animation_manifest_placeholder(tmp_path):
    from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler

    template_root = tmp_path / "templates"
    runtime_root = tmp_path / "runtime"
    template_dir = template_root / "element_template"
    compositions_dir = template_dir / "compositions"
    compositions_dir.mkdir(parents=True)
    (template_dir / "index.template.html").write_text(
        '<script src="__ELEMENT_ANIMATION_MANIFEST__"></script>',
        encoding="utf-8",
    )
    (compositions_dir / "captions.template.html").write_text(
        "__CAPTIONS__",
        encoding="utf-8",
    )

    manifest = RenderManifest(
        task_id="task-element-compile",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        fps=30,
        template_id="element_template",
        element_animation_manifest_path="data/element_animation_manifest.json",
    )
    context = build_template_render_context(manifest, template_params={})

    compiler = HyperFramesCompiler(
        template_root=template_root,
        runtime_root=runtime_root,
    )
    compiler.compile(project_dir=tmp_path / "project", context=context)

    index_html = (tmp_path / "project" / "index.html").read_text(encoding="utf-8")
    assert 'src="data/element_animation_manifest.json"' in index_html


def test_write_project_data_derives_captions_from_sentence_units_when_manifest_cues_missing(tmp_path):
    manifest = RenderManifest(
        task_id="task-2",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                remapped_start=0.2,
                remapped_end=1.4,
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))

    project_paths = service.write_project_data(manifest)
    manifest_path = project_paths.data_dir / "render_manifest.json"
    captions_path = project_paths.data_dir / "captions.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    captions_data = json.loads(captions_path.read_text(encoding="utf-8"))

    expected_captions = [
        {
            "id": "sentence-1",
            "text": "Sentence 1",
            "start": 0.2,
            "end": 1.4,
            "frame_indices": [0],
            "style_profile": DEFAULT_CAPTION_STYLE_ID,
        }
    ]

    assert manifest_data["caption_cues"] == expected_captions
    assert captions_data["captions"] == [
        *expected_captions
    ]


def test_write_project_data_can_preserve_caption_punctuation_when_configured(tmp_path):
    manifest = RenderManifest(
        task_id="task-2-preserve",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        caption_punctuation_mode="preserve",
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                remapped_start=0.2,
                remapped_end=1.4,
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))

    project_paths = service.write_project_data(manifest)
    captions_data = json.loads((project_paths.data_dir / "captions.json").read_text(encoding="utf-8"))

    assert captions_data["captions"][0]["text"] == "Sentence 1."
    assert (
        captions_data["captions"][0]["style_profile"]
        == DEFAULT_CAPTION_STYLE_ID
    )


def test_write_project_data_does_not_derive_captions_when_hyperframes_not_targeted(tmp_path):
    manifest = RenderManifest(
        task_id="task-caption-targets",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        caption_rendering_enabled=True,
        caption_renderer_targets=["ass"],
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                remapped_start=0.2,
                remapped_end=1.4,
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))

    project_paths = service.write_project_data(manifest)
    manifest_data = json.loads(
        (project_paths.data_dir / "render_manifest.json").read_text(encoding="utf-8")
    )
    captions_data = json.loads(
        (project_paths.data_dir / "captions.json").read_text(encoding="utf-8")
    )
    context = build_template_render_context(manifest, template_params={})

    assert manifest_data["caption_cues"] == []
    assert captions_data["captions"] == []
    assert context.captions == []


def test_write_project_data_splits_long_sentence_captions_into_expression_level_cues(tmp_path):
    manifest = RenderManifest(
        task_id="task-2b",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Alpha, beta.",
                frame_indices=[0],
                remapped_start=0.0,
                remapped_end=2.2,
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))

    project_paths = service.write_project_data(manifest)
    captions_data = json.loads((project_paths.data_dir / "captions.json").read_text(encoding="utf-8"))

    assert captions_data["captions"] == [
        {
            "id": "sentence-1-cue-1",
            "text": "Alpha",
            "start": 0.0,
            "end": 1.2,
            "frame_indices": [0],
            "style_profile": DEFAULT_CAPTION_STYLE_ID,
        },
        {
            "id": "sentence-1-cue-2",
            "text": "beta",
            "start": 1.2,
            "end": 2.2,
            "frame_indices": [0],
            "style_profile": DEFAULT_CAPTION_STYLE_ID,
        },
    ]


def test_write_project_data_clamps_and_filters_timeline_spans_before_export(tmp_path):
    manifest = RenderManifest(
        task_id="task-3",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        master_audio_path="output/task-3/master_audio.wav",
        audio_blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1.",
                start=-1.0,
                end=6.0,
                source_frame_indices=[0],
            ),
            AudioBlock(
                id="block-2",
                text="Sentence 2.",
                start=4.0,
                end=3.0,
                source_frame_indices=[1],
            ),
        ],
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                source_start=-2.0,
                source_end=2.5,
            ),
            SentenceUnit(
                id="sentence-2",
                text="Sentence 2.",
                frame_indices=[1],
                remapped_start=4.5,
                remapped_end=8.5,
            ),
            SentenceUnit(
                id="sentence-3",
                text="Sentence 3.",
                frame_indices=[2],
                source_start=3.0,
                source_end=3.0,
            ),
        ],
        visual_clips=[
            VisualClip(
                id="clip-1",
                frame_index=0,
                start=-1.0,
                end=1.0,
                media_path="output/task-3/frames/01_raw.png",
                media_type="image",
            ),
            VisualClip(
                id="clip-2",
                frame_index=1,
                start=4.5,
                end=9.5,
                media_path="output/task-3/frames/02_raw.png",
                media_type="image",
            ),
            VisualClip(
                id="clip-3",
                frame_index=2,
                start=2.0,
                end=1.0,
                media_path="output/task-3/frames/03_raw.png",
                media_type="image",
            ),
        ],
        caption_cues=[
            CaptionCue(
                id="caption-1",
                text="Sentence 1",
                start=-1.0,
                end=2.5,
                frame_indices=[0],
                style_profile="image_life_insights_light",
            ),
            CaptionCue(
                id="caption-2",
                text="Sentence 2",
                start=4.5,
                end=7.5,
                frame_indices=[1],
                style_profile="image_life_insights_light",
            ),
            CaptionCue(
                id="caption-3",
                text="Sentence 3",
                start=3.0,
                end=3.0,
                frame_indices=[2],
                style_profile="image_life_insights_light",
            ),
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project_data(manifest, master_audio_duration=5.0)
    manifest_data = json.loads((project_paths.data_dir / "render_manifest.json").read_text(encoding="utf-8"))
    captions_data = json.loads((project_paths.data_dir / "captions.json").read_text(encoding="utf-8"))

    assert manifest_data["audio_blocks"] == [
        {
            "id": "block-1",
            "text": "Sentence 1.",
            "audio_path": None,
            "start": 0.0,
            "end": 5.0,
            "source_frame_indices": [0],
        }
    ]
    assert [sentence["id"] for sentence in manifest_data["sentence_units"]] == [
        "sentence-1",
        "sentence-2",
    ]
    assert manifest_data["sentence_units"][0]["source_start"] == 0.0
    assert manifest_data["sentence_units"][0]["source_end"] == 2.5
    assert manifest_data["sentence_units"][1]["remapped_start"] == 4.5
    assert manifest_data["sentence_units"][1]["remapped_end"] == 5.0
    assert [clip["id"] for clip in manifest_data["visual_clips"]] == ["clip-1", "clip-2"]
    assert manifest_data["visual_clips"][0]["start"] == 0.0
    assert manifest_data["visual_clips"][1]["end"] == 5.0
    assert captions_data["captions"] == [
        {
            "id": "caption-1",
            "text": "Sentence 1",
            "start": 0.0,
            "end": 2.5,
            "frame_indices": [0],
            "style_profile": "image_life_insights_light",
        },
        {
            "id": "caption-2",
            "text": "Sentence 2",
            "start": 4.5,
            "end": 5.0,
            "frame_indices": [1],
            "style_profile": "image_life_insights_light",
        },
    ]


def test_write_project_data_drops_captions_for_sentences_whose_remapped_span_collapses(tmp_path):
    manifest = RenderManifest(
        task_id="task-4",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        master_audio_path="output/task-4/trimmed_master_audio.wav",
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                source_start=0.2,
                source_end=0.8,
                remapped_start=2.0,
                remapped_end=2.5,
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project_data(manifest, master_audio_duration=1.0)

    manifest_data = json.loads((project_paths.data_dir / "render_manifest.json").read_text(encoding="utf-8"))
    captions_data = json.loads((project_paths.data_dir / "captions.json").read_text(encoding="utf-8"))

    assert manifest_data["sentence_units"][0]["source_start"] is None
    assert manifest_data["sentence_units"][0]["source_end"] is None
    assert manifest_data["sentence_units"][0]["remapped_start"] is None
    assert manifest_data["sentence_units"][0]["remapped_end"] is None
    assert captions_data["captions"] == []


def test_write_project_data_clears_sentence_block_id_when_audio_block_is_removed(tmp_path):
    manifest = RenderManifest(
        task_id="task-5",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        audio_blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1.",
                start=2.0,
                end=3.0,
                source_frame_indices=[0],
            )
        ],
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.2,
                source_end=0.8,
            )
        ],
    )

    service = HyperFramesProjectService(output_dir=str(tmp_path))
    project_paths = service.write_project_data(manifest, master_audio_duration=1.0)

    manifest_data = json.loads((project_paths.data_dir / "render_manifest.json").read_text(encoding="utf-8"))

    assert manifest_data["audio_blocks"] == []
    assert manifest_data["sentence_units"][0]["block_id"] is None
