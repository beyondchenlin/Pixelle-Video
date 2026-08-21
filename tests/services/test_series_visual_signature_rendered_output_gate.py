from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.services.series_visual_signature_rendered_output_gate import (
    SeriesVisualSignatureRenderedOutputGate,
    SeriesVisualSignatureRenderedOutputGateError,
    resolve_rendered_output_max_attempts,
    resolve_rendered_output_validation_mode,
)


class _FakeVisionService:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []

    async def chat(self, *, messages, **kwargs):
        self.messages.append(messages)
        return self.responses.pop(0)

    async def aclose(self):
        return None


def _profile() -> VisualSignatureProfileSnapshot:
    return VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="斑点狗",
        core_identity_traits=("黑色墨镜", "红色项圈"),
    )


def _image(tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"generated-image-bytes")
    return path


def _gate(tmp_path, response: dict):
    gate = SeriesVisualSignatureRenderedOutputGate(
        vision_config={
            "enabled": True,
            "model": "vision-model",
            "force_supports_vision": True,
            "max_image_size_mb": 1,
        },
        mode="auto",
        task_dir=tmp_path,
    )
    fake = _FakeVisionService([json.dumps(response)])
    gate._vision_service = fake
    return gate, fake


@pytest.mark.asyncio
async def test_rendered_output_gate_passes_one_small_subordinate_identity(tmp_path) -> None:
    gate, fake = _gate(
        tmp_path,
        {
            "identity_instance_count": 1,
            "largest_identity_area_ratio": 0.14,
            "identity_traits_visible": True,
            "identity_is_primary_focus": False,
            "confidence": 0.93,
        },
    )

    result = await gate.evaluate(
        image_path=_image(tmp_path),
        frame_id="frame-1",
        generation_attempt=0,
        profile=_profile(),
        max_area_ratio=0.16,
        trace_context=SimpleNamespace(),
        trace_recorder=SimpleNamespace(),
    )

    assert result.passed is True
    assert result.accepted is True
    assert result.reason == "contract_satisfied"
    assert result.effective_area_limit == pytest.approx(0.20)
    artifact = json.loads((tmp_path / result.artifact_relative_path).read_text("utf-8"))
    assert artifact["identity_instance_count"] == 1
    artifact_text = json.dumps(artifact, ensure_ascii=False)
    assert "斑点狗" not in artifact_text
    assert "data:image" not in artifact_text
    assert fake.messages[0][1]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("review_patch", "reason"),
    [
        ({"identity_instance_count": 2}, "identity_instance_count_not_one"),
        ({"largest_identity_area_ratio": 0.35}, "identity_area_ratio_exceeded"),
        ({"identity_traits_visible": False}, "identity_traits_not_visible"),
        ({"identity_is_primary_focus": True}, "identity_became_primary_focus"),
        ({"confidence": 0.3}, "review_confidence_below_threshold"),
    ],
)
async def test_rendered_output_gate_rejects_each_visual_contract_violation(
    tmp_path,
    review_patch,
    reason,
) -> None:
    review = {
        "identity_instance_count": 1,
        "largest_identity_area_ratio": 0.12,
        "identity_traits_visible": True,
        "identity_is_primary_focus": False,
        "confidence": 0.95,
    }
    review.update(review_patch)
    gate, _ = _gate(tmp_path, review)

    result = await gate.evaluate(
        image_path=_image(tmp_path),
        frame_id="frame-1",
        generation_attempt=0,
        profile=_profile(),
        max_area_ratio=0.16,
        trace_context=SimpleNamespace(),
        trace_recorder=SimpleNamespace(),
    )

    assert result.passed is False
    assert result.accepted is False
    assert result.reason == reason


@pytest.mark.asyncio
async def test_auto_mode_skips_without_vision_but_required_mode_fails_preflight(
    tmp_path,
) -> None:
    automatic = SeriesVisualSignatureRenderedOutputGate(
        vision_config={"enabled": False},
        mode="auto",
        task_dir=tmp_path,
    )
    result = await automatic.evaluate(
        image_path=_image(tmp_path),
        frame_id="frame-1",
        generation_attempt=0,
        profile=_profile(),
        max_area_ratio=0.16,
        trace_context=None,
        trace_recorder=None,
    )
    assert result.status == "skipped"
    assert result.reason == "vision_llm_disabled"

    required = SeriesVisualSignatureRenderedOutputGate(
        vision_config={"enabled": False},
        mode="required",
        task_dir=tmp_path,
    )
    with pytest.raises(
        SeriesVisualSignatureRenderedOutputGateError,
        match="vision_llm_disabled",
    ):
        required.assert_required_capability()
    with pytest.raises(
        SeriesVisualSignatureRenderedOutputGateError,
        match="vision_llm_disabled",
    ):
        await required.evaluate(
            image_path=_image(tmp_path),
            frame_id="frame-1",
            generation_attempt=0,
            profile=_profile(),
            max_area_ratio=0.16,
            trace_context=None,
            trace_recorder=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("max_area_ratio", [0.0, -0.1, 1.1, float("nan"), True])
async def test_rendered_output_gate_rejects_invalid_area_contract(
    tmp_path,
    max_area_ratio,
) -> None:
    gate = SeriesVisualSignatureRenderedOutputGate(
        vision_config={"enabled": False},
        mode="auto",
        task_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="maximum area ratio"):
        await gate.evaluate(
            image_path=_image(tmp_path),
            frame_id="frame-1",
            generation_attempt=0,
            profile=_profile(),
            max_area_ratio=max_area_ratio,
            trace_context=None,
            trace_recorder=None,
        )


@pytest.mark.asyncio
async def test_rendered_output_gate_rejects_image_outside_task_directory(
    tmp_path,
) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    outside_image = _image(tmp_path)
    gate = SeriesVisualSignatureRenderedOutputGate(
        vision_config={"enabled": False},
        mode="auto",
        task_dir=task_dir,
    )

    with pytest.raises(ValueError, match="inside the task directory"):
        await gate.evaluate(
            image_path=outside_image,
            frame_id="frame-1",
            generation_attempt=0,
            profile=_profile(),
            max_area_ratio=0.16,
            trace_context=None,
            trace_recorder=None,
        )


def test_rendered_output_policy_bounds_cost_and_strict_mode() -> None:
    assert resolve_rendered_output_validation_mode(
        {}, strict_signature_enforcement=False
    ) == "auto"
    assert resolve_rendered_output_validation_mode(
        {}, strict_signature_enforcement=True
    ) == "required"
    with pytest.raises(ValueError, match="cannot disable"):
        resolve_rendered_output_validation_mode(
            {"series_visual_signature_output_validation_mode": "off"},
            strict_signature_enforcement=True,
        )
    assert resolve_rendered_output_max_attempts({}) == 2
    with pytest.raises(ValueError, match="between 1 and 3"):
        resolve_rendered_output_max_attempts(
            {"series_visual_signature_output_max_attempts": 4}
        )
