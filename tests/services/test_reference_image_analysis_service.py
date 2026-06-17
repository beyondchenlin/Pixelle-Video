import json
from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.models.llm_interaction_trace import LLMTraceContext
from pixelle_video.models.reference_image import ReferenceImageAsset
from pixelle_video.models.reference_image_analysis import ReferenceImageAnalysis
from pixelle_video.services.reference_image_analysis import (
    ReferenceImageAnalysisService,
    resolve_reference_image_analysis_mode,
)


class _FakeVisionLLMService:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected fake vision call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeRecorder:
    async def record_interaction(self, **kwargs):
        return None


def _trace_context() -> LLMTraceContext:
    return LLMTraceContext(
        workspace_id="workspace",
        task_id="task",
        operation="reference_image_analysis",
    )


def _asset(tmp_path: Path) -> ReferenceImageAsset:
    task_dir = tmp_path / "task"
    image_dir = task_dir / "reference_image"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "vision_abcd1234.jpg"
    Image.new("RGB", (2, 2), (255, 255, 255)).save(image_path, format="JPEG")
    return ReferenceImageAsset(
        source_kind="local_path",
        original_display_name="role.png",
        task_asset_path=str(image_path),
        task_asset_relative_path="reference_image/original_abcd1234.png",
        vision_asset_path=str(image_path),
        vision_asset_relative_path="reference_image/vision_abcd1234.jpg",
        workflow_asset_path=str(image_path),
        workflow_asset_relative_path="reference_image/workflow_abcd1234.jpg",
        sha256="a" * 64,
        mime_type="image/jpeg",
        width=2,
        height=2,
        byte_size=image_path.stat().st_size,
    )


def _valid_analysis_json() -> str:
    return json.dumps(
        {
            "subject_summary": "a small white toy character",
            "style_summary": "soft storybook illustration",
            "color_atmosphere": "warm white and pastel tones",
            "composition_summary": "centered subject, simple background",
            "identity_anchors": ["round face", "white outfit"],
            "style_anchors": ["storybook", "soft lighting"],
            "negative_constraints": ["avoid dark cyberpunk style"],
            "prompt_hint_en": "soft storybook toy character, warm lighting",
            "prompt_hint_zh": "柔和童话绘本风，小玩具角色，暖色光照",
            "confidence": 0.9,
            "limitations": [],
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_reference_image_analysis_success_writes_artifact(tmp_path):
    asset = _asset(tmp_path)
    fake_vision = _FakeVisionLLMService([_valid_analysis_json()])

    result = await ReferenceImageAnalysisService().analyze(
        vision_llm_service=fake_vision,
        asset=asset,
        prompt_language="zh_CN",
        task_dir=tmp_path / "task",
        analysis_mode="auto",
        trace_context=_trace_context(),
        trace_recorder=_FakeRecorder(),
        vision_config={"enabled": True, "model": "qwen-vl-max"},
    )

    assert result.status == "success"
    assert isinstance(result.analysis, ReferenceImageAnalysis)
    assert result.analysis.prompt_hint_zh.startswith("柔和")
    assert result.artifact_relative_path == "reference_image/analysis.json"
    artifact = json.loads((tmp_path / "task" / "reference_image" / "analysis.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "success"
    artifact_json = json.dumps(artifact, ensure_ascii=False)
    assert "base64," not in artifact_json
    assert str(asset.vision_asset_path) not in artifact_json
    assert fake_vision.calls[0]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_reference_image_analysis_auto_skips_when_vision_disabled(tmp_path):
    asset = _asset(tmp_path)
    fake_vision = _FakeVisionLLMService([])

    result = await ReferenceImageAnalysisService().analyze(
        vision_llm_service=fake_vision,
        asset=asset,
        prompt_language="zh_CN",
        task_dir=tmp_path / "task",
        analysis_mode="auto",
        vision_config={"enabled": False, "model": ""},
    )

    assert result.status == "skipped"
    assert result.reason == "vision_llm_disabled"
    assert fake_vision.calls == []
    artifact = json.loads((tmp_path / "task" / "reference_image" / "analysis.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "skipped"


@pytest.mark.asyncio
async def test_reference_image_analysis_required_raises_when_vision_disabled(tmp_path):
    asset = _asset(tmp_path)

    with pytest.raises(ValueError, match="required but unavailable"):
        await ReferenceImageAnalysisService().analyze(
            vision_llm_service=_FakeVisionLLMService([]),
            asset=asset,
            prompt_language="zh_CN",
            task_dir=tmp_path / "task",
            analysis_mode="required",
            vision_config={"enabled": False, "model": ""},
        )

    artifact = json.loads((tmp_path / "task" / "reference_image" / "analysis.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "failed"


@pytest.mark.asyncio
async def test_reference_image_analysis_retries_invalid_json_once(tmp_path):
    asset = _asset(tmp_path)
    fake_vision = _FakeVisionLLMService(["not json", _valid_analysis_json()])

    result = await ReferenceImageAnalysisService().analyze(
        vision_llm_service=fake_vision,
        asset=asset,
        prompt_language="zh_CN",
        task_dir=tmp_path / "task",
        analysis_mode="auto",
        trace_context=_trace_context(),
        trace_recorder=_FakeRecorder(),
        vision_config={"enabled": True, "model": "qwen-vl-max"},
    )

    assert result.status == "success"
    assert len(fake_vision.calls) == 2


def test_resolve_reference_image_analysis_mode_from_params_and_config():
    assert resolve_reference_image_analysis_mode({"reference_image_analysis_mode": "required"}, {"analysis_mode": "off"}) == "required"
    assert resolve_reference_image_analysis_mode({}, {"analysis_mode": "auto"}) == "auto"
    assert resolve_reference_image_analysis_mode({}, {}) == "off"
