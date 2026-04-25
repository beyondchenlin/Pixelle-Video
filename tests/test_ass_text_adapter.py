from pixelle_video.models.render_package import RenderManifest, TextCue, TextTrack
from pixelle_video.models.text_style import TextStyleProfile
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
    assert "Style: caption-default" in subtitle_text
    assert "Style: overlay-default" in overlay_text
    assert "重点，词" in overlay_text
    assert "第一行" not in overlay_text


def test_ass_export_uses_manifest_profile_for_subtitle_style(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Styled subtitle",
        width=1080,
        height=1920,
        fps=30,
        template_id="styled",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-yellow",
                name="Caption Yellow",
                font_size=72,
                primary_color="#FFFF00",
                stroke_width=5,
            )
        ],
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
                style_profile="caption-yellow",
            )
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="Styled caption",
                start=0.0,
                end=1.0,
                role="subtitle",
            )
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)
    master_text = outputs.master.read_text(encoding="utf-8")

    assert "Style: caption-yellow" in master_text
    assert ",72," in master_text
    assert "&H0000FFFF" in master_text
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,caption-yellow" in master_text


def test_ass_export_cue_style_overrides_track_style(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Cue override",
        width=1080,
        height=1920,
        fps=30,
        template_id="styled",
        text_style_profiles=[
            TextStyleProfile(id="track-style", name="Track Style"),
            TextStyleProfile(id="cue-style", name="Cue Style", primary_color="#00FF00"),
        ],
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
                style_profile="track-style",
            )
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="Cue wins",
                start=0.0,
                end=1.0,
                role="subtitle",
                style_profile="cue-style",
            )
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)
    master_text = outputs.master.read_text(encoding="utf-8")

    assert "Style: cue-style" in master_text
    assert "Style: track-style" not in master_text
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,cue-style" in master_text


def test_ass_export_track_style_applies_when_cue_style_absent(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Track style",
        width=1080,
        height=1920,
        fps=30,
        template_id="styled",
        text_style_profiles=[
            TextStyleProfile(id="track-style", name="Track Style", font_size=70)
        ],
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
                style_profile="track-style",
            )
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="Track wins",
                start=0.0,
                end=1.0,
                role="subtitle",
            )
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)
    master_text = outputs.master.read_text(encoding="utf-8")

    assert "Style: track-style" in master_text
    assert ",70," in master_text
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,track-style" in master_text


def test_ass_export_exposes_fallback_diagnostics_for_missing_style(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Fallback",
        width=1080,
        height=1920,
        fps=30,
        template_id="styled",
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
                style_profile="missing-style",
            )
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="Fallback caption",
                start=0.0,
                end=1.0,
                role="subtitle",
            )
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)
    master_text = outputs.master.read_text(encoding="utf-8")

    assert "Style: caption-default" in master_text
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,caption-default" in master_text
    assert outputs.diagnostics == {
        "fallbacks": [
            {
                "cue_id": "s1",
                "missing_style_id": "missing-style",
                "resolved_style_id": "caption-default",
            }
        ]
    }


def test_ass_export_empty_overlay_split_keeps_ass_structure(tmp_path):
    manifest = RenderManifest(
        task_id="task-1",
        title="Subtitle only",
        width=1080,
        height=1920,
        fps=30,
        template_id="styled",
        text_tracks=[
            TextTrack(
                id="subtitle",
                kind="subtitle",
                name="Subtitle",
                renderer_targets=("ass",),
            )
        ],
        text_cues=[
            TextCue(
                id="s1",
                track_id="subtitle",
                text="Only subtitle",
                start=0.0,
                end=1.0,
                role="subtitle",
            )
        ],
    )

    outputs = AssTextAdapter().export(manifest=manifest, output_dir=tmp_path)
    overlay_text = outputs.overlay_only.read_text(encoding="utf-8")

    assert "[Script Info]" in overlay_text
    assert "[V4+ Styles]" in overlay_text
    assert "[Events]" in overlay_text
    assert "Dialogue:" not in overlay_text


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
