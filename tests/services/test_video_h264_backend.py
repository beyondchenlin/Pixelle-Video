from __future__ import annotations

from pixelle_video.services.video import VideoService


class _RecordingExecutor:
    def __init__(self) -> None:
        self.selected_calls = 0
        self.run_calls: list[dict[str, object]] = []

    def selected_output_kwargs(self) -> dict[str, object]:
        self.selected_calls += 1
        return {
            "vcodec": "h264_qsv",
            "preset": "medium",
            "global_quality": 23,
        }

    def run_output(
        self,
        build_output,
        *,
        quiet: bool = False,
        selected_params=None,
    ) -> None:
        self.run_calls.append(
            {
                "build_output": build_output,
                "quiet": quiet,
                "selected_params": dict(selected_params or {}),
            }
        )


def test_video_service_reads_family_specific_kwargs_from_shared_executor() -> None:
    service = VideoService()
    executor = _RecordingExecutor()
    service._h264_executor = executor

    assert service._h264_encode_params() == {
        "vcodec": "h264_qsv",
        "preset": "medium",
        "global_quality": 23,
    }
    assert executor.selected_calls == 1


def test_video_service_encode_run_delegates_execution_and_quiet_flag() -> None:
    service = VideoService()
    executor = _RecordingExecutor()
    service._h264_executor = executor

    def build_output(**params):
        raise AssertionError("VideoService must not execute the output graph directly")

    service._encode_run(build_output, quiet=True)

    assert executor.selected_calls == 1
    assert len(executor.run_calls) == 1
    call = executor.run_calls[0]
    assert call["build_output"] is build_output
    assert call["quiet"] is True
    assert call["selected_params"] == {
        "vcodec": "h264_qsv",
        "preset": "medium",
        "global_quality": 23,
    }


def test_video_service_encode_run_delegates_cpu_backend_without_special_case() -> None:
    service = VideoService()

    class CpuExecutor(_RecordingExecutor):
        def selected_output_kwargs(self) -> dict[str, object]:
            self.selected_calls += 1
            return {"vcodec": "libx264", "preset": "medium", "crf": 23}

    executor = CpuExecutor()
    service._h264_executor = executor

    service._encode_run(lambda **params: object())

    assert executor.run_calls[0]["selected_params"] == {
        "vcodec": "libx264",
        "preset": "medium",
        "crf": 23,
    }
