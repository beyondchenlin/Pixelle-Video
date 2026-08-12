import json

import pytest

from pixelle_video.services.render_output_probe import (
    RenderOutputContractError,
    RenderOutputProbe,
)


def _probe_payload() -> dict:
    return {
        "format": {"duration": "2.400000"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 320,
                "height": 180,
                "pix_fmt": "yuv420p",
                "color_range": "tv",
                "color_space": "bt709",
                "color_primaries": "bt709",
                "color_transfer": "bt709",
                "r_frame_rate": "30/1",
                "avg_frame_rate": "30/1",
                "duration": "2.400000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "duration": "2.400000",
            },
        ],
    }


def test_render_output_probe_accepts_complete_contract(tmp_path, monkeypatch):
    output = tmp_path / "final.mp4"
    output.write_bytes(b"video")
    monkeypatch.setattr(
        "pixelle_video.services.render_output_probe.ffmpeg.probe",
        lambda _path: _probe_payload(),
    )

    result = RenderOutputProbe().validate(
        output_path=output,
        width=320,
        height=180,
        fps=30,
        duration=2.4,
        subtitle_end=2.2,
        report_path=tmp_path / "probe.json",
    )

    assert result.ok is True
    assert json.loads((tmp_path / "probe.json").read_text(encoding="utf-8"))["ok"] is True


def test_render_output_probe_rejects_missing_color_and_truncated_audio(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "final.mp4"
    output.write_bytes(b"video")
    payload = _probe_payload()
    payload["streams"][0].pop("color_space")
    payload["streams"][1]["duration"] = "2.000000"
    monkeypatch.setattr(
        "pixelle_video.services.render_output_probe.ffmpeg.probe",
        lambda _path: payload,
    )
    report = tmp_path / "probe.json"

    with pytest.raises(RenderOutputContractError, match="color_space mismatch"):
        RenderOutputProbe().validate(
            output_path=output,
            width=320,
            height=180,
            fps=30,
            duration=2.4,
            report_path=report,
        )

    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert any("audio duration mismatch" in error for error in result["errors"])


def test_render_output_probe_rejects_video_that_runs_past_master_timeline(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "final.mp4"
    output.write_bytes(b"video")
    payload = _probe_payload()
    payload["streams"][0]["duration"] = "2.900000"
    monkeypatch.setattr(
        "pixelle_video.services.render_output_probe.ffmpeg.probe",
        lambda _path: payload,
    )

    with pytest.raises(RenderOutputContractError, match="video duration mismatch"):
        RenderOutputProbe().validate(
            output_path=output,
            width=320,
            height=180,
            fps=30,
            duration=2.4,
        )


def test_render_output_probe_persists_diagnostics_when_output_is_not_probeable(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "broken.mp4"
    output.write_bytes(b"broken")
    report = tmp_path / "probe.json"
    monkeypatch.setattr(
        "pixelle_video.services.render_output_probe.ffmpeg.probe",
        lambda _path: (_ for _ in ()).throw(OSError("ffprobe unavailable")),
    )

    with pytest.raises(RenderOutputContractError, match="could not be probed"):
        RenderOutputProbe().validate(
            output_path=output,
            width=320,
            height=180,
            fps=30,
            duration=2.4,
            report_path=report,
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert "ffprobe unavailable" in payload["errors"][0]
