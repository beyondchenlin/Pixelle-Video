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
