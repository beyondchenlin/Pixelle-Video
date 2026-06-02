import json

from loguru import logger

from pixelle_video.utils.logging_util import (
    build_content_observability,
    new_correlation_id,
    redact_mapping,
    redact_text,
    setup_logging,
    teardown_logging,
)


def _logging_config(tmp_path):
    return {
        "enabled": True,
        "level": "INFO",
        "log_dir": str(tmp_path),
        "rotation_mb": 50,
        "retention_days": 14,
        "task_logs_enabled": True,
        "ai_creation_logs_enabled": True,
        "preview_chars": 12,
    }


def test_redact_mapping_masks_sensitive_keys_by_substring_and_suffix():
    payload = {
        "api_key": "sk-secret",
        "comfyui_api_key": "comfy-secret",
        "runninghub_api_key": "rh-secret",
        "nested": {"access_token": "abc123", "model": "qwen-max"},
    }

    redacted = redact_mapping(payload)

    assert redacted["api_key"] == "***"
    assert redacted["comfyui_api_key"] == "***"
    assert redacted["runninghub_api_key"] == "***"
    assert redacted["nested"]["access_token"] == "***"
    assert redacted["nested"]["model"] == "qwen-max"


def test_redact_mapping_summarizes_raw_generation_params():
    payload = {
        "video_params": {
            "prompt_text": "总有人问我，正定的浪漫藏在哪里？",
            "ref_audio_text": "今天我带着你，走过七处印记。",
            "ref_audio": "data/reference_audio/omnivoice/妮-omnivoice.wav",
            "character_assets": ["uploads/person.png"],
            "workflow_key": "runninghub/i2v_LTX2.json",
        }
    }

    redacted = redact_mapping(payload)
    raw = json.dumps(redacted, ensure_ascii=False)
    params = redacted["video_params"]

    assert "正定的浪漫" not in raw
    assert "七处印记" not in raw
    assert "妮-omnivoice" not in raw
    assert params["prompt_text"]["redacted"] is True
    assert params["ref_audio_text"]["input_length"] > 0
    assert params["ref_audio"]["suffix"] == ".wav"
    assert params["character_assets"]["count"] == 1
    assert params["workflow_key"] == "runninghub/i2v_LTX2.json"


def test_redact_text_masks_secret_bearing_message_fragments():
    message = "ComfyKit config: {'runninghub_api_key': 'rh-secret', 'model': 'x'}"

    redacted = redact_text(message)

    assert "rh-secret" not in redacted
    assert "***" in redacted
    assert "model" in redacted


def test_redact_text_masks_private_generation_param_fragments():
    message = (
        "video_params: {'prompt_text': '总有人问我，正定的浪漫藏在哪里？', "
        "'ref_audio_text': '今天我带着你，走过七处印记。', "
        "'ref_audio': 'data/reference_audio/omnivoice/妮-omnivoice.wav', "
        "'audio_assets': ['input.wav']}"
    )

    redacted = redact_text(message)

    assert "正定的浪漫" not in redacted
    assert "七处印记" not in redacted
    assert "妮-omnivoice" not in redacted
    assert "input.wav" not in redacted
    assert "'prompt_text': '***'" in redacted
    assert "'audio_assets': [***]" in redacted


def test_setup_logging_writes_complete_flat_jsonl_record(tmp_path):
    sink_ids = setup_logging(service_name="web", config=_logging_config(tmp_path))
    try:
        logger.bind(
            channel="ai_creation",
            service="pipeline",
            request_id="req_1",
            session_id="sess_1",
            api_task_id=None,
            task_id="task-1",
            pipeline="standard",
            stage="title_generation",
            event="end",
            status="success",
            provider="dashscope",
            model="qwen-max",
            latency_ms=12,
            llm_call_count=1,
            retry_count=0,
            attempt=1,
            batch_index=None,
            batch_total=None,
            narration_count=5,
            workflow="selfhost/image.json",
            template="1080x1920/default.html",
        ).info("title generation completed")
    finally:
        teardown_logging(sink_ids)

    payload = json.loads((tmp_path / "web.jsonl").read_text(encoding="utf-8").splitlines()[0])

    expected_keys = {
        "timestamp",
        "level",
        "service",
        "channel",
        "message",
        "request_id",
        "session_id",
        "api_task_id",
        "task_id",
        "pipeline",
        "stage",
        "event",
        "status",
        "provider",
        "model",
        "latency_ms",
        "llm_call_count",
        "retry_count",
        "attempt",
        "batch_index",
        "batch_total",
        "narration_count",
        "workflow",
        "template",
        "extra",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["service"] == "pipeline"
    assert payload["channel"] == "ai_creation"
    assert payload["llm_call_count"] == 1


def test_content_observability_uses_hash_length_and_bounded_preview():
    summary = build_content_observability("abcdefghijklmnopqrstuvwxyz", preview_chars=8)

    assert summary["input_length"] == 26
    assert summary["preview"] == "abcdefgh..."
    assert len(summary["content_hash"]) == 16


def test_new_correlation_id_uses_prefix():
    request_id = new_correlation_id("req")
    session_id = new_correlation_id("sess")

    assert request_id.startswith("req_")
    assert session_id.startswith("sess_")
    assert request_id != session_id
