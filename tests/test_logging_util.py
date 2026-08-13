import json

from loguru import logger

from pixelle_video.utils.logging_util import (
    build_content_observability,
    log_exception_once,
    new_correlation_id,
    redact_credentials_in_text,
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


def test_credential_redaction_handles_provider_error_variants_without_masking_usage():
    message = (
        'client_secret="oauth secret with spaces" '
        "X-API-Key=provider-key private_key='private key value' "
        "authorization=Bearer bearer-secret "
        "url=https://user:password@example.test/v1"
    )

    redacted = redact_credentials_in_text(message, replacement="[REDACTED]")
    mapping = redact_mapping(
        {
            "client_secret": "oauth-secret",
            "total_tokens": 42,
            "private_key": "private-key",
        }
    )

    assert "oauth secret with spaces" not in redacted
    assert "provider-key" not in redacted
    assert "private key value" not in redacted
    assert "bearer-secret" not in redacted
    assert "user:password" not in redacted
    assert mapping["client_secret"] == "***"
    assert mapping["private_key"] == "***"
    assert mapping["total_tokens"] == 42


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


def test_setup_logging_preserves_utf8_chinese_and_emoji(tmp_path):
    sink_ids = setup_logging(service_name="web", config=_logging_config(tmp_path))
    try:
        logger.info("🎬 视频生成完成")
    finally:
        teardown_logging(sink_ids)

    raw = (tmp_path / "web.jsonl").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "🎬 视频生成完成" in raw.decode("utf-8")


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


def test_exception_logging_is_single_line_structured_safe_and_deduplicated(tmp_path):
    sink_ids = setup_logging(service_name="web", config=_logging_config(tmp_path))
    hidden_path = tmp_path / "private" / "missing.mp3"
    private_message = (
        f"private user body; windows={hidden_path}; "
        "posix=/home/alice/private/missing.mp3; "
        r"unc=\\server\private\missing.mp3"
    )
    try:
        try:
            raise ValueError(private_message)
        except ValueError as error:
            assert log_exception_once(error, "generation failed") is True
            assert log_exception_once(error, "duplicate boundary") is False
    finally:
        teardown_logging(sink_ids)

    raw = (tmp_path / "web.jsonl").read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["message"] == "generation failed"
    assert payload["exception_type"] == "ValueError"
    assert payload["exception_message"] == "<redacted>"
    assert payload["exception_message_length"] == len(private_message)
    assert len(payload["exception_message_hash"]) == 16
    assert "Traceback (most recent call last)" in payload["exception_traceback"]
    assert str(tmp_path.resolve()) not in raw
    assert "/home/alice" not in raw
    assert "server\\private" not in raw
    assert "private user body" not in raw
    assert "duplicate boundary" not in raw


def test_direct_exception_object_message_is_not_persisted(tmp_path):
    sink_ids = setup_logging(service_name="web", config=_logging_config(tmp_path))
    private_body = "short private user正文"
    try:
        try:
            raise RuntimeError(private_body)
        except RuntimeError as error:
            logger.exception(error)
    finally:
        teardown_logging(sink_ids)

    raw = (tmp_path / "web.jsonl").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload["message"] == "RuntimeError raised"
    assert payload["exception_message"] == "<redacted>"
    assert private_body not in raw
