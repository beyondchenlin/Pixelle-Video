import pytest
from PIL import Image, ImageDraw

from pixelle_video.services.render_artifact_analyzer import (
    PixelBox,
    RenderArtifactAnalyzer,
)


def _write_frame(path, *, media_left: int, baseline_shift: int = 0) -> None:
    image = Image.new("RGB", (32, 24), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((media_left, 2, media_left + 11, 21), fill=(24, 24, 24))
    draw.line((media_left, 2, media_left + 11, 2), fill=(0, 255, 0), width=1)
    draw.line((media_left, 21, media_left + 11, 21), fill=(0, 255, 0), width=1)
    draw.rectangle((media_left + 2, 4, media_left + 8, 19), outline=(0, 180, 255))
    draw.rectangle((9, 7 + baseline_shift, 22, 9 + baseline_shift), fill=(255, 255, 255))
    draw.rectangle((9, 18 + baseline_shift, 22, 20 + baseline_shift), fill=(255, 255, 255))
    image.save(path)


def test_analyzer_reads_media_edges_and_two_text_bands_from_final_pixels(tmp_path):
    frame = tmp_path / "frame.png"
    _write_frame(frame, media_left=4)

    metrics = RenderArtifactAnalyzer().analyze_frame(frame)

    assert metrics.media_box == PixelBox(4, 2, 15, 21)
    assert metrics.landmark_box == PixelBox(6, 4, 12, 19)
    assert metrics.text_box == PixelBox(9, 7, 22, 20)
    assert metrics.text_row_bands == ((7, 9), (18, 20))


def test_compare_reports_backend_edge_and_baseline_deltas(tmp_path):
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    _write_frame(left, media_left=4)
    _write_frame(right, media_left=5, baseline_shift=1)
    analyzer = RenderArtifactAnalyzer()

    difference = analyzer.compare(left_frame=left, right_frame=right)

    assert difference.media_edge_delta == (1, 0, 1, 0)
    assert difference.landmark_edge_delta == (1, 0, 1, 0)
    assert difference.text_baseline_proxy_delta == (1, 1)
    assert difference.changed_pixel_ratio > 0


def test_text_row_bands_split_at_the_first_blank_raster_row():
    assert RenderArtifactAnalyzer._contiguous_bands((10, 11, 13, 14)) == (
        (10, 11),
        (13, 14),
    )


def test_pixel_contract_rejects_two_pixel_baseline_drift(tmp_path):
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    _write_frame(left, media_left=4)
    _write_frame(right, media_left=4, baseline_shift=2)
    analyzer = RenderArtifactAnalyzer()
    left_metrics = analyzer.analyze_frame(left)
    right_metrics = analyzer.analyze_frame(right)
    difference = analyzer.compare(
        left_frame=left,
        right_frame=right,
        left_metrics=left_metrics,
        right_metrics=right_metrics,
    )

    with pytest.raises(AssertionError, match="baseline proxies exceed 1px"):
        analyzer.assert_pixel_contract(
            expected_media_box=PixelBox(4, 2, 15, 21),
            expected_landmark_box=PixelBox(6, 4, 12, 19),
            expected_text_line_count=2,
            expected_text_baseline_proxy_rows=(9, 20),
            left=left_metrics,
            right=right_metrics,
            difference=difference,
        )
