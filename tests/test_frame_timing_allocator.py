import pytest

from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.services.frame_timing_allocator import allocate_frame_timing_windows


def test_allocate_frame_timing_windows_splits_shared_sentence_evenly():
    windows = allocate_frame_timing_windows(
        frame_count=2,
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="One spoken unit spans two frames.",
                frame_indices=[0, 1],
                source_start=0.0,
                source_end=10.0,
            )
        ],
    )

    assert [(window.frame_index, window.start, window.end) for window in windows] == [
        (0, pytest.approx(0.0), pytest.approx(5.0)),
        (1, pytest.approx(5.0), pytest.approx(10.0)),
    ]


def test_allocate_frame_timing_windows_uses_frame_weights_when_available():
    windows = allocate_frame_timing_windows(
        frame_count=2,
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="Weighted spoken unit.",
                frame_indices=[0, 1],
                frame_weights={0: 1.0, 1: 3.0},
                source_start=0.0,
                source_end=8.0,
            )
        ],
    )

    assert [(window.frame_index, window.start, window.end) for window in windows] == [
        (0, pytest.approx(0.0), pytest.approx(2.0)),
        (1, pytest.approx(2.0), pytest.approx(8.0)),
    ]


def test_continuous_windows_preserve_leading_inter_scene_and_trailing_silence():
    windows = allocate_frame_timing_windows(
        frame_count=2,
        sentence_units=[
            SentenceUnit(
                id="sentence-1",
                text="First",
                frame_indices=[0],
                source_start=0.4,
                source_end=1.2,
            ),
            SentenceUnit(
                id="sentence-2",
                text="Second",
                frame_indices=[1],
                source_start=1.6,
                source_end=2.4,
            ),
        ],
        timeline_start=0.0,
        timeline_end=3.0,
    )

    assert [(window.frame_index, window.start, window.end) for window in windows] == [
        (0, pytest.approx(0.0), pytest.approx(1.6)),
        (1, pytest.approx(1.6), pytest.approx(3.0)),
    ]


def test_continuous_windows_allocate_frames_without_sentences():
    windows = allocate_frame_timing_windows(
        frame_count=3,
        sentence_units=[],
        timeline_start=0.0,
        timeline_end=3.0,
    )

    assert [(window.frame_index, window.start, window.end) for window in windows] == [
        (0, pytest.approx(0.0), pytest.approx(1.0)),
        (1, pytest.approx(1.0), pytest.approx(2.0)),
        (2, pytest.approx(2.0), pytest.approx(3.0)),
    ]


@pytest.mark.parametrize(
    ("timeline_start", "timeline_end"),
    [(None, 1.0), (0.0, None), (1.0, 1.0), (2.0, 1.0)],
)
def test_continuous_windows_reject_invalid_timeline_bounds(
    timeline_start,
    timeline_end,
):
    with pytest.raises(ValueError, match="timeline"):
        allocate_frame_timing_windows(
            frame_count=1,
            sentence_units=[],
            timeline_start=timeline_start,
            timeline_end=timeline_end,
        )
