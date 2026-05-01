from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
)
from pixelle_video.services.text_cue_compiler import TextCueCompiler


def test_compiler_prefers_remapped_sentence_timing():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="重点词",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0, "sentence_id": "s1"},
                ),
            )
        ),
    )
    sentences = [
        SentenceUnit(
            id="s1",
            text="重点词来自这一句。",
            frame_indices=[0],
            source_start=1.0,
            source_end=3.0,
            remapped_start=0.5,
            remapped_end=2.2,
        )
    ]

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=sentences,
    )

    assert tracks[0].id == "track-hyperframes-keyword"
    assert tracks[0].kind == "keyword"
    assert cues[0].start == 0.5
    assert cues[0].end == 2.2
    assert cues[0].source["candidate_id"] == "candidate-1"


def test_compiler_uses_source_sentence_timing_when_no_remap_exists():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Source timing",
                    role="keyword",
                    renderer_targets=("ass",),
                    source={"frame_index": 0, "sentence_id": "s1"},
                ),
            )
        ),
    )
    sentences = [
        SentenceUnit(
            id="s1",
            text="Source timing sentence.",
            frame_indices=[0],
            source_start=1.25,
            source_end=2.75,
        )
    ]

    _, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=sentences,
    )

    assert cues[0].start == 1.25
    assert cues[0].end == 2.75


def test_compiler_uses_frame_fallback_when_sentence_timing_missing():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="稳定",
                    role="keyword",
                    renderer_targets=("ass",),
                    source={"frame_index": 2},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=1.5,
    )

    assert tracks[0].renderer_targets == ("ass",)
    assert cues[0].start == 3.0
    assert cues[0].end == 4.5


def test_compiler_uses_frame_windows_before_uniform_duration_fallback():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Frame window",
                    role="keyword",
                    renderer_targets=("ass",),
                    source={"frame_index": 1},
                ),
            )
        ),
    )

    _, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_windows={0: (0.0, 2.0), 1: (2.0, 5.5)},
        frame_duration=1.5,
    )

    assert cues[0].start == 2.0
    assert cues[0].end == 5.5


def test_compiler_maps_native_hint_role_to_native_track_kind():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Pixelle",
                    role="model_native_hint",
                    renderer_targets=("native_prompt",),
                    source={"frame_index": 0},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=2.0,
    )

    assert tracks[0].kind == "native_hint"
    assert cues[0].role == "model_native_hint"


def test_text_cue_compiler_assigns_overlay_style_profile():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Key idea",
                    role="keyword",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=1.5,
    )

    assert tracks[0].style_profile == DEFAULT_OVERLAY_STYLE_ID
    assert cues[0].style_profile == DEFAULT_OVERLAY_STYLE_ID


def test_text_cue_compiler_assigns_caption_style_profile_to_subtitles():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Subtitle text",
                    role="subtitle",
                    renderer_targets=("ass",),
                    source={"frame_index": 0},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=1.5,
    )

    assert tracks[0].style_profile == DEFAULT_CAPTION_STYLE_ID
    assert cues[0].style_profile == DEFAULT_CAPTION_STYLE_ID


def test_text_cue_compiler_keeps_native_hint_style_profile_empty():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Pixelle",
                    role="model_native_hint",
                    renderer_targets=("native_prompt",),
                    source={"frame_index": 0},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=1.5,
    )

    assert tracks[0].style_profile is None
    assert cues[0].style_profile is None


def test_text_cue_compiler_keeps_native_hint_alias_style_profile_empty():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Pixelle",
                    role="native_hint",
                    renderer_targets=("native_prompt",),
                    source={"frame_index": 0},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=1.5,
    )

    assert tracks[0].style_profile is None
    assert cues[0].style_profile is None


def test_text_cue_compiler_merges_targets_for_shared_tracks():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="HyperFrames cue",
                    role="keyword",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0},
                ),
                TextOverlayCandidate(
                    id="candidate-2",
                    text="Shared cue",
                    role="keyword",
                    renderer_targets=("hyperframes", "ass"),
                    source={"frame_index": 1},
                ),
            )
        ),
    )

    tracks, cues = TextCueCompiler().compile(
        package=package,
        sentence_units=[],
        frame_duration=1.5,
    )

    assert len(tracks) == 1
    assert tracks[0].renderer_targets == ("hyperframes", "ass")
    assert tracks[0].style_profile == DEFAULT_OVERLAY_STYLE_ID
    assert [cue.track_id for cue in cues] == [tracks[0].id, tracks[0].id]
