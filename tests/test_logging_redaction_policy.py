import json
import re
from pathlib import Path

from loguru import logger

from pixelle_video.utils.logging_util import setup_logging, teardown_logging


def test_global_log_does_not_persist_secret_values_or_full_prompt_text(tmp_path):
    sink_ids = setup_logging(
        service_name="api",
        config={
            "enabled": True,
            "level": "INFO",
            "log_dir": str(tmp_path),
            "rotation_mb": 50,
            "retention_days": 14,
            "task_logs_enabled": True,
            "ai_creation_logs_enabled": True,
            "preview_chars": 10,
        },
    )
    try:
        logger.bind(
            config={
                "comfyui_api_key": "comfy-secret",
                "runninghub_api_key": "rh-secret",
            },
            content={
                "input_length": 43,
                "content_hash": "abc123",
                "preview": "Long topic...",
            },
        ).info("Submitting generation request: Long topic...")
    finally:
        teardown_logging(sink_ids)

    raw_line = (tmp_path / "api.jsonl").read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(raw_line)

    assert "comfy-secret" not in raw_line
    assert "rh-secret" not in raw_line
    assert "abcdefghijklmnopqrstuvwxyz" not in raw_line
    assert payload["extra"]["config"]["comfyui_api_key"] == "***"
    assert payload["extra"]["content"]["input_length"] == 43


def test_global_log_summarizes_accidental_raw_video_params(tmp_path):
    sink_ids = setup_logging(
        service_name="web",
        config={
            "enabled": True,
            "level": "INFO",
            "log_dir": str(tmp_path),
            "rotation_mb": 50,
            "retention_days": 14,
            "task_logs_enabled": True,
            "ai_creation_logs_enabled": True,
            "preview_chars": 10,
        },
    )
    try:
        logger.bind(
            video_params={
                "prompt_text": "总有人问我，正定的浪漫藏在哪里？",
                "ref_audio_text": "今天我带着你，走过七处印记。",
                "ref_audio": "data/reference_audio/omnivoice/妮-omnivoice.wav",
                "audio_assets": ["input.wav"],
            },
        ).info("render output preview")
    finally:
        teardown_logging(sink_ids)

    raw_line = (tmp_path / "web.jsonl").read_text(encoding="utf-8")
    payload = json.loads(raw_line.splitlines()[0])
    params = payload["extra"]["video_params"]

    assert "正定的浪漫" not in raw_line
    assert "七处印记" not in raw_line
    assert "妮-omnivoice" not in raw_line
    assert params["prompt_text"]["redacted"] is True
    assert params["ref_audio"]["suffix"] == ".wav"
    assert params["audio_assets"]["count"] == 1


def test_web_pipelines_do_not_log_raw_video_params():
    offenders = []
    pattern = re.compile(
        r"logger\.(?:trace|debug|info|warning|error|exception|success)\([^\n]*video_params"
    )
    for path in Path("web/pipelines").glob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            line_number = path.read_text(encoding="utf-8")[: match.start()].count("\n") + 1
            offenders.append(f"{path}:{line_number}")

    assert offenders == []
