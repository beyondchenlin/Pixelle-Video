from pixelle_video.models.render_package import RenderManifest, TextCue, TextTrack
from pixelle_video.services.ass_text_adapter import AssTextAdapter


def test_ass_export_writes_master_and_split_tracks_with_escaped_text(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Text test",
        width=1080,
        height=1920,
        fps=30,
        template_id="legacy",
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
            ),
            TextTrack(
                id="overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("ass",),
            ),
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="第一行 {测试}\n第二行",
                start=0.0,
                end=1.0,
                role="subtitle",
                layer=0,
            ),
            TextCue(
                id="k1",
                track_id="overlay",
                text="重点,词",
                start=0.5,
                end=1.5,
                role="keyword",
                slot="center",
                layer=2,
            ),
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)

    assert outputs.master.name == "master.ass"
    assert outputs.subtitle_only.name == "subtitle_only.ass"
    assert outputs.overlay_only.name == "overlay_only.ass"

    master_text = outputs.master.read_text(encoding="utf-8")
    subtitle_text = outputs.subtitle_only.read_text(encoding="utf-8")
    overlay_text = outputs.overlay_only.read_text(encoding="utf-8")

    assert r"\{测试\}\N第二行" in master_text
    assert "Style: Default" in subtitle_text
    assert "重点，词" in overlay_text
    assert "第一行" not in overlay_text


def test_ass_export_ignores_tracks_without_ass_target(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Text test",
        width=1080,
        height=1920,
        fps=30,
        template_id="legacy",
        text_tracks=[
            TextTrack(
                id="overlay",
                kind="overlay",
                name="Overlay",
                renderer_targets=("hyperframes",),
            ),
        ],
        text_cues=[
            TextCue(
                id="k1",
                track_id="overlay",
                text="不应导出",
                start=0.0,
                end=1.0,
                role="keyword",
            ),
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)

    assert "不应导出" not in outputs.master.read_text(encoding="utf-8")
