import json

from pixelle_video.models.render_package import AudioBlock, CaptionCue, RenderManifest, SentenceUnit, VisualClip
from pixelle_video.services.hyperframes_project_service import HyperFramesProjectService


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
            "text": "Sentence 1.",
            "start": 0.2,
            "end": 1.4,
            "frame_indices": [0],
            "style_profile": "image_life_insights_light",
        }
    ]

    assert manifest_data["caption_cues"] == expected_captions
    assert captions_data["captions"] == [
        *expected_captions
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
