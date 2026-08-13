from __future__ import annotations

import json
import math
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops


@dataclass(frozen=True)
class PixelBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


@dataclass(frozen=True)
class FrameArtifactMetrics:
    frame_path: str
    media_box: PixelBox | None
    landmark_box: PixelBox | None
    text_box: PixelBox | None
    text_row_bands: tuple[tuple[int, int], ...]

    def to_dict(self) -> dict:
        return {
            "frame_path": self.frame_path,
            "media_box": asdict(self.media_box) if self.media_box else None,
            "landmark_box": asdict(self.landmark_box) if self.landmark_box else None,
            "text_box": asdict(self.text_box) if self.text_box else None,
            "text_row_bands": [list(item) for item in self.text_row_bands],
        }


@dataclass(frozen=True)
class BackendDifferenceMetrics:
    mean_absolute_channel_difference: float
    maximum_channel_difference: int
    changed_pixel_ratio: float
    media_edge_delta: tuple[int, int, int, int] | None
    landmark_edge_delta: tuple[int, int, int, int] | None
    text_edge_delta: tuple[int, int, int, int] | None
    text_baseline_proxy_delta: tuple[int, ...]

    def to_dict(self) -> dict:
        return asdict(self)


class RenderArtifactAnalyzer:
    """Inspect decoded final-video pixels, never intermediate renderer state."""

    def extract_frame(
        self,
        *,
        video_path: str | Path,
        timestamp: float,
        output_path: str | Path,
    ) -> Path:
        source = Path(video_path).resolve()
        target = Path(output_path).resolve()
        if not source.is_file():
            raise ValueError(f"video artifact must exist: {source}")
        if not math.isfinite(float(timestamp)) or float(timestamp) < 0:
            raise ValueError("frame timestamp must be a finite non-negative number")
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{float(timestamp):.6f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            str(target),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if completed.returncode != 0 or not target.is_file():
            raise RuntimeError(
                "failed to decode qualification frame: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )
        return target

    def analyze_frame(self, frame_path: str | Path) -> FrameArtifactMetrics:
        path = Path(frame_path).resolve()
        with Image.open(path) as source:
            image = source.convert("RGB")
        pixels = image.load()
        media_points: list[tuple[int, int]] = []
        landmark_points: list[tuple[int, int]] = []
        text_points: list[tuple[int, int]] = []
        text_rows: dict[int, int] = {}
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue = pixels[x, y]
                if self._is_fixed_asset_pixel(red, green, blue):
                    media_points.append((x, y))
                if self._is_landmark_pixel(red, green, blue):
                    landmark_points.append((x, y))
                if self._is_text_pixel(red, green, blue):
                    text_points.append((x, y))
                    text_rows[y] = text_rows.get(y, 0) + 1
        row_bands = self._text_row_bands(text_rows)
        return FrameArtifactMetrics(
            frame_path=str(path),
            media_box=self._pixel_box(media_points),
            landmark_box=self._pixel_box(landmark_points),
            text_box=self._pixel_box(text_points),
            text_row_bands=row_bands,
        )

    def compare(
        self,
        *,
        left_frame: str | Path,
        right_frame: str | Path,
        left_metrics: FrameArtifactMetrics | None = None,
        right_metrics: FrameArtifactMetrics | None = None,
    ) -> BackendDifferenceMetrics:
        left_path = Path(left_frame).resolve()
        right_path = Path(right_frame).resolve()
        with Image.open(left_path) as source:
            left = source.convert("RGB")
        with Image.open(right_path) as source:
            right = source.convert("RGB")
        if left.size != right.size:
            raise ValueError(
                f"backend frames must have equal dimensions: {left.size} != {right.size}"
            )
        difference = ImageChops.difference(left, right)
        histogram = difference.histogram()
        sample_count = left.width * left.height * 3
        absolute_sum = sum((index % 256) * count for index, count in enumerate(histogram))
        maximum = max(
            (index % 256 for index, count in enumerate(histogram) if count),
            default=0,
        )
        changed_pixels = 0
        diff_pixels = difference.load()
        for y in range(difference.height):
            for x in range(difference.width):
                if max(diff_pixels[x, y]) > 12:
                    changed_pixels += 1
        left_analysis = left_metrics or self.analyze_frame(left_path)
        right_analysis = right_metrics or self.analyze_frame(right_path)
        return BackendDifferenceMetrics(
            mean_absolute_channel_difference=(absolute_sum / max(1, sample_count)),
            maximum_channel_difference=maximum,
            changed_pixel_ratio=changed_pixels / max(1, left.width * left.height),
            media_edge_delta=self._edge_delta(
                left_analysis.media_box,
                right_analysis.media_box,
            ),
            landmark_edge_delta=self._edge_delta(
                left_analysis.landmark_box,
                right_analysis.landmark_box,
            ),
            text_edge_delta=self._edge_delta(
                left_analysis.text_box,
                right_analysis.text_box,
            ),
            text_baseline_proxy_delta=self._baseline_proxy_delta(
                left_analysis.text_row_bands,
                right_analysis.text_row_bands,
            ),
        )

    @staticmethod
    def assert_pixel_contract(
        *,
        expected_media_box: PixelBox,
        expected_landmark_box: PixelBox,
        expected_text_line_count: int,
        expected_text_baseline_proxy_rows: tuple[int, ...],
        left: FrameArtifactMetrics,
        right: FrameArtifactMetrics,
        difference: BackendDifferenceMetrics,
        tolerance_pixels: int = 1,
    ) -> None:
        if expected_text_line_count <= 0:
            raise ValueError("expected_text_line_count must be positive")
        if len(expected_text_baseline_proxy_rows) != expected_text_line_count:
            raise ValueError(
                "expected_text_baseline_proxy_rows must match expected_text_line_count"
            )
        failures: list[str] = []
        for backend_name, metrics in (("ffmpeg", left), ("hyperframes", right)):
            if metrics.media_box is None:
                failures.append(f"{backend_name} media boundary was not detected")
            elif max(
                abs(metrics.media_box.left - expected_media_box.left),
                abs(metrics.media_box.top - expected_media_box.top),
                abs(metrics.media_box.right - expected_media_box.right),
                abs(metrics.media_box.bottom - expected_media_box.bottom),
            ) > tolerance_pixels:
                failures.append(
                    f"{backend_name} media boundary exceeds {tolerance_pixels}px tolerance: "
                    f"expected={expected_media_box}, actual={metrics.media_box}"
                )
            if metrics.text_box is None:
                failures.append(f"{backend_name} text pixels were not detected")
            if metrics.landmark_box is None:
                failures.append(f"{backend_name} landmark boundary was not detected")
            elif max(
                abs(metrics.landmark_box.left - expected_landmark_box.left),
                abs(metrics.landmark_box.top - expected_landmark_box.top),
                abs(metrics.landmark_box.right - expected_landmark_box.right),
                abs(metrics.landmark_box.bottom - expected_landmark_box.bottom),
            ) > tolerance_pixels:
                failures.append(
                    f"{backend_name} landmark boundary exceeds {tolerance_pixels}px tolerance: "
                    f"expected={expected_landmark_box}, actual={metrics.landmark_box}"
                )
            if len(metrics.text_row_bands) != expected_text_line_count:
                failures.append(
                    f"{backend_name} wrapping must produce exactly "
                    f"{expected_text_line_count} lines: "
                    f"{metrics.text_row_bands}"
                )
            else:
                actual_proxy_rows = tuple(band[1] for band in metrics.text_row_bands)
                proxy_deltas = tuple(
                    abs(actual - expected)
                    for actual, expected in zip(
                        actual_proxy_rows,
                        expected_text_baseline_proxy_rows,
                    )
                )
                if max(proxy_deltas, default=0) > tolerance_pixels:
                    failures.append(
                        f"{backend_name} text baseline proxies exceed "
                        f"{tolerance_pixels}px tolerance: expected="
                        f"{expected_text_baseline_proxy_rows}, actual={actual_proxy_rows}"
                    )
        pairwise_tolerance = tolerance_pixels * 2
        if (
            difference.media_edge_delta is None
            or max(difference.media_edge_delta) > pairwise_tolerance
        ):
            failures.append(
                "backend-to-backend media edges exceed the canonical-error bound "
                f"{pairwise_tolerance}px: {difference.media_edge_delta}"
            )
        if (
            difference.landmark_edge_delta is None
            or max(difference.landmark_edge_delta) > pairwise_tolerance
        ):
            failures.append(
                "backend-to-backend landmark edges exceed the canonical-error bound "
                f"{pairwise_tolerance}px: {difference.landmark_edge_delta}"
            )
        if (
            difference.text_baseline_proxy_delta
            and max(difference.text_baseline_proxy_delta) > pairwise_tolerance
        ):
            failures.append(
                "backend-to-backend text baseline proxies exceed the canonical-error "
                f"bound {pairwise_tolerance}px: "
                f"{difference.text_baseline_proxy_delta}"
            )
        if failures:
            raise AssertionError("; ".join(failures))

    @staticmethod
    def write_report(path: str | Path, payload: dict) -> Path:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    @staticmethod
    def _is_fixed_asset_pixel(red: int, green: int, blue: int) -> bool:
        return (
            (green >= 160 and green - red >= 100 and green - blue >= 100)
            or (blue >= 150 and blue - red >= 100 and blue - green >= 70)
            or (
                red >= 160
                and blue >= 160
                and red - green >= 100
                and blue - green >= 100
            )
        )

    @staticmethod
    def _is_text_pixel(red: int, green: int, blue: int) -> bool:
        return min(red, green, blue) >= 210 and max(red, green, blue) - min(
            red, green, blue
        ) <= 20

    @staticmethod
    def _is_landmark_pixel(red: int, green: int, blue: int) -> bool:
        return (
            red <= 70
            and green >= 100
            and blue >= 180
            and green - red >= 80
            and 30 <= blue - green <= 140
        )

    @staticmethod
    def _pixel_box(points: Iterable[tuple[int, int]]) -> PixelBox | None:
        values = list(points)
        if not values:
            return None
        xs = [point[0] for point in values]
        ys = [point[1] for point in values]
        return PixelBox(min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _contiguous_bands(rows: Iterable[int]) -> tuple[tuple[int, int], ...]:
        sorted_rows = sorted(set(rows))
        if not sorted_rows:
            return ()
        bands: list[tuple[int, int]] = []
        start = previous = sorted_rows[0]
        for row in sorted_rows[1:]:
            if row == previous + 1:
                previous = row
                continue
            bands.append((start, previous))
            start = previous = row
        bands.append((start, previous))
        return tuple(bands)

    @classmethod
    def _text_row_bands(
        cls,
        row_counts: dict[int, int],
    ) -> tuple[tuple[int, int], ...]:
        core_bands = cls._contiguous_bands(
            row for row, count in row_counts.items() if count >= 2
        )
        return tuple(
            (
                start - 1 if row_counts.get(start - 1) == 1 else start,
                end + 1 if row_counts.get(end + 1) == 1 else end,
            )
            for start, end in core_bands
        )

    @staticmethod
    def _edge_delta(left: PixelBox | None, right: PixelBox | None) -> tuple[int, int, int, int] | None:
        if left is None or right is None:
            return None
        return (
            abs(left.left - right.left),
            abs(left.top - right.top),
            abs(left.right - right.right),
            abs(left.bottom - right.bottom),
        )

    @staticmethod
    def _baseline_proxy_delta(
        left: tuple[tuple[int, int], ...],
        right: tuple[tuple[int, int], ...],
    ) -> tuple[int, ...]:
        if len(left) != len(right):
            return ()
        return tuple(abs(a[1] - b[1]) for a, b in zip(left, right))


__all__ = [
    "BackendDifferenceMetrics",
    "FrameArtifactMetrics",
    "PixelBox",
    "RenderArtifactAnalyzer",
]
