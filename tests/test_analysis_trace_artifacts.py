from types import SimpleNamespace

import pytest

from pixelle_video.services.image_analysis import ImageAnalysisService
from pixelle_video.services.video_analysis import VideoAnalysisService


@pytest.mark.asyncio
async def test_image_analysis_service_writes_analysis_trace_before_execution(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"image")
    service = ImageAnalysisService({"comfyui": {"image_analysis": {}}})
    captured = {}
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "source": "selfhost",
            "key": "selfhost/analyse_image.json",
            "path": "workflows/selfhost/analyse_image.json",
        },
    )

    async def fake_execute_workflow(*_args, **kwargs):
        captured["trace_context"] = dict(kwargs["analysis_workflow_trace_context"])
        return SimpleNamespace(
            status="completed",
            msg="",
            outputs={"6": {"text": ["a clean description"]}},
        )

    monkeypatch.setattr(service, "_execute_workflow", fake_execute_workflow)

    description = await service(
        str(image_path),
        source="selfhost",
        workflow="selfhost/analyse_image.json",
    )

    assert description == "a clean description"
    trace_context = captured["trace_context"]
    assert trace_context["workflow"] == "selfhost/analyse_image.json"
    assert trace_context["workflow_input"] == "workflows/selfhost/analyse_image.json"
    assert trace_context["media_type"] == "image"
    assert trace_context["service_domain"] == "image_analysis"
    assert trace_context["artifact_path"].is_file()
    service_result = trace_context["artifact_path"].with_name("analysis_service_result.md")
    service_result_text = service_result.read_text(encoding="utf-8")
    assert "pixelle.analysis_service_result.v1" in service_result_text
    assert "a clean description" in service_result_text


@pytest.mark.asyncio
async def test_image_analysis_service_records_non_completed_workflow_result(
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"image")
    service = ImageAnalysisService({"comfyui": {"image_analysis": {}}})
    captured = {}
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "source": "selfhost",
            "key": "selfhost/analyse_image.json",
            "path": "workflows/selfhost/analyse_image.json",
        },
    )

    async def fake_execute_workflow(*_args, **kwargs):
        captured["trace_context"] = dict(kwargs["analysis_workflow_trace_context"])
        return SimpleNamespace(
            status="failed",
            msg="provider timeout",
            outputs={"raw": {"text": ["partial diagnostic"]}},
            files=["diagnostic.txt"],
            texts=["partial diagnostic"],
        )

    monkeypatch.setattr(service, "_execute_workflow", fake_execute_workflow)

    with pytest.raises(Exception, match="provider timeout"):
        await service(
            str(image_path),
            source="selfhost",
            workflow="selfhost/analyse_image.json",
        )

    service_result = captured["trace_context"]["artifact_path"].with_name(
        "analysis_service_result.md"
    )
    service_result_text = service_result.read_text(encoding="utf-8")
    assert '"status": "failed"' in service_result_text
    assert "service_workflow_failure" in service_result_text
    assert "provider timeout" in service_result_text
    assert "partial diagnostic" in service_result_text


@pytest.mark.asyncio
async def test_video_analysis_service_writes_analysis_trace_before_execution(
    monkeypatch,
    tmp_path,
):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"video")
    service = VideoAnalysisService({"comfyui": {"video_analysis": {}}})
    captured = {}
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "source": "runninghub",
            "key": "runninghub/video_understanding.json",
            "workflow_id": "rh-video-analysis",
            "path": "workflows/runninghub/video_understanding.json",
        },
    )

    async def fake_execute_workflow(*_args, **kwargs):
        captured["trace_context"] = dict(kwargs["analysis_workflow_trace_context"])
        return SimpleNamespace(
            status="completed",
            msg="",
            outputs={},
            texts=["video description"],
        )

    monkeypatch.setattr(service, "_execute_workflow", fake_execute_workflow)

    description = await service(
        str(video_path),
        source="runninghub",
        workflow="runninghub/video_understanding.json",
    )

    assert description == "video description"
    trace_context = captured["trace_context"]
    assert trace_context["workflow"] == "runninghub/video_understanding.json"
    assert trace_context["workflow_input"] == "rh-video-analysis"
    assert trace_context["media_type"] == "video"
    assert trace_context["service_domain"] == "video_analysis"
    assert trace_context["artifact_path"].is_file()
    service_result = trace_context["artifact_path"].with_name("analysis_service_result.md")
    service_result_text = service_result.read_text(encoding="utf-8")
    assert "pixelle.analysis_service_result.v1" in service_result_text
    assert "video description" in service_result_text


@pytest.mark.asyncio
async def test_video_analysis_service_records_extraction_failure_workflow_result(
    monkeypatch,
    tmp_path,
):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"video")
    service = VideoAnalysisService({"comfyui": {"video_analysis": {}}})
    captured = {}
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "source": "runninghub",
            "key": "runninghub/video_understanding.json",
            "workflow_id": "rh-video-analysis",
            "path": "workflows/runninghub/video_understanding.json",
        },
    )

    async def fake_execute_workflow(*_args, **kwargs):
        captured["trace_context"] = dict(kwargs["analysis_workflow_trace_context"])
        return SimpleNamespace(
            status="completed",
            msg="",
            outputs={"raw_data": [{"fileType": "json", "fileUrl": "ignored"}]},
            files=["ignored.json"],
            texts=[],
        )

    monkeypatch.setattr(service, "_execute_workflow", fake_execute_workflow)

    with pytest.raises(Exception, match="No description generated"):
        await service(
            str(video_path),
            source="runninghub",
            workflow="runninghub/video_understanding.json",
        )

    service_result = captured["trace_context"]["artifact_path"].with_name(
        "analysis_service_result.md"
    )
    service_result_text = service_result.read_text(encoding="utf-8")
    assert '"status": "error"' in service_result_text
    assert "service_extraction_error" in service_result_text
    assert "No description generated from video analysis" in service_result_text
    assert "ignored.json" in service_result_text
