import pytest

from pixelle_video.services.tts_trace_artifacts import (
    TTS_TRACE_RESULT_FILE_NAME,
    validate_tts_workflow_trace_artifact,
    write_tts_workflow_result_artifact,
    write_tts_workflow_trace_context,
)


def test_tts_workflow_trace_artifact_round_trips_text_and_params(tmp_path):
    workflow_params = {
        "text": "hello world",
        "ref_audio": "voice.wav",
        "speed": 1.1,
    }

    context = write_tts_workflow_trace_context(
        tmp_path,
        task_id="task-tts",
        text="hello world",
        workflow="selfhost/tts_edge.json",
        workflow_input="workflows/selfhost/tts_edge.json",
        source="test",
        workflow_params=workflow_params,
    )

    validated = validate_tts_workflow_trace_artifact(
        context,
        text="hello world",
        workflow="selfhost/tts_edge.json",
        workflow_input="workflows/selfhost/tts_edge.json",
        workflow_params=workflow_params,
    )
    result_path = write_tts_workflow_result_artifact(
        validated,
        status="completed",
        result={"audio_path": "generated.wav"},
    )

    assert context["text"] == "hello world"
    assert result_path.is_file()


def test_tts_result_artifacts_do_not_overwrite_reused_trace_context(tmp_path):
    context = write_tts_workflow_trace_context(
        tmp_path,
        task_id="task-tts-retry",
        text="retry text",
        workflow="selfhost/tts_edge.json",
        workflow_input="workflows/selfhost/tts_edge.json",
        source="test",
        workflow_params={"text": "retry text"},
    )

    first_result = write_tts_workflow_result_artifact(
        context,
        status="error",
        result={"error": "first attempt"},
    )
    second_result = write_tts_workflow_result_artifact(
        context,
        status="completed",
        result={"audio_path": "second.wav"},
    )

    assert first_result.name == TTS_TRACE_RESULT_FILE_NAME
    assert second_result.name == "tts_workflow_result-2.md"
    assert "first attempt" in first_result.read_text(encoding="utf-8")
    assert "second.wav" in second_result.read_text(encoding="utf-8")


def test_tts_workflow_trace_artifact_rejects_text_mismatch(tmp_path):
    context = write_tts_workflow_trace_context(
        tmp_path,
        task_id="task-tts",
        text="visible text",
        workflow="selfhost/tts_edge.json",
        workflow_input="workflows/selfhost/tts_edge.json",
        source="test",
        workflow_params={"text": "visible text"},
    )

    with pytest.raises(ValueError, match="text does not match"):
        validate_tts_workflow_trace_artifact(
            context,
            text="hidden text",
            workflow="selfhost/tts_edge.json",
            workflow_input="workflows/selfhost/tts_edge.json",
            workflow_params={"text": "hidden text"},
        )
