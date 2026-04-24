import json

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
