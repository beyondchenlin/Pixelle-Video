import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_STAGE_PROMPT_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    PREFLIGHT_REVIEW_PROMPT_VERSION,
    ContentStageOutput,
    FusionStageInput,
    FusionStageOutput,
    IdentityReferenceCondition,
    PreflightReviewOutput,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
)
from pixelle_video.services.frame_processor import FrameProcessor
from pixelle_video.services.reference_image_visual_context_adapter import (
    reset_reference_image_visual_story_context_patch,
    set_reference_image_visual_story_context_patch,
)
from pixelle_video.services.visual_anchor_generation_binding import (
    validate_visual_anchor_first_generation_binding,
)
from pixelle_video.services.visual_anchor_reference_condition import (
    inspect_identity_reference_workflow,
)
from pixelle_video.services.visual_anchor_reference_workflow import (
    resolve_visual_anchor_reference_workflow_key,
)
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageError,
    VisualAnchorTwoStageService,
    _validate_content_stage_output,
    identity_profile_from_snapshot,
    resolve_registered_random_seeds,
)
from pixelle_video.services.visual_prompt_composer import (
    VisualPromptComposer,
    _content_only_visual_story_context,
    _render_two_stage_prompt,
)


class _QueuedLLM:
    def __init__(self, responses):
        self.responses = {
            response_type: list(items) for response_type, items in responses.items()
        }
        self.calls = []

    async def __call__(self, *, prompt, response_type, **kwargs):
        self.calls.append(
            {
                "prompt": prompt,
                "response_type": response_type,
                "kwargs": kwargs,
            }
        )
        return self.responses[response_type].pop(0)


def _plan(*, continuous=False):
    frames = [
        StoryboardPlanFrame(
            index=1,
            frame_id="frame-a",
            source_text="乔布斯和沃兹尼亚克在车库组装一台电脑。",
            visual_goal="表现两人在车库创业",
            prompt_intent="车库工作台场景",
            continuity_anchors=("同一车库",) if continuous else (),
        )
    ]
    if continuous:
        frames.append(
            StoryboardPlanFrame(
                index=2,
                frame_id="frame-b",
                source_text="两人继续在同一车库测试这台电脑。",
                visual_goal="延续测试动作",
                prompt_intent="同一车库连续镜头",
                continuity_anchors=("同一车库",),
            )
        )
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=" ".join(frame.source_text for frame in frames),
        frames=frames,
    )


def test_identity_profile_binds_the_real_reference_when_profile_has_no_asset_ids():
    snapshot = VisualSignatureProfileSnapshot(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=("圆形白色脸", "蓝色短耳"),
        supporting_identity_traits=("橙色围巾",),
        forbidden_traits=("改变脸型",),
        source_asset_ids=(),
    )

    identity = identity_profile_from_snapshot(
        snapshot,
        identity_reference_resource_id="reference-image:" + "a" * 64,
    )

    assert identity.source_asset_ids == ["reference-image:" + "a" * 64]
    with pytest.raises(VisualAnchorTwoStageError, match="no source assets"):
        identity_profile_from_snapshot(snapshot)


def _identity():
    return VisualAnchorIdentityProfile(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=["圆形白色脸", "蓝色短耳"],
        supporting_identity_traits=["橙色围巾"],
        forbidden_traits=["改变脸型"],
        source_asset_ids=[
            "asset-pixelle-reference",
            "reference-image:" + "a" * 64,
        ],
        identity_content_sha256="b" * 64,
        identity_resource_version="identity:profile-pixelle:" + "b" * 64,
    )


def _reference(*, asset_sha256="a" * 64):
    return IdentityReferenceCondition(
        asset_sha256=asset_sha256,
        workflow_asset_relative_path="reference_image/workflow.png",
        mime_type="image/png",
        width=512,
        height=512,
        byte_size=1024,
        resource_version="reference-image:" + asset_sha256,
        workflow_parameter="reference_image",
        workflow_node_id="92",
        workflow_node_class_type="LoadImage",
        workflow_node_input_field="image",
        conditioning_node_id="94",
        conditioning_node_class_type="ReferenceLatent",
        sampler_node_id="3",
        sampler_node_class_type="KSampler",
        binding_path_node_ids=["92", "93", "94", "3"],
    )


def _content(frame_id, source_text):
    return ContentStageOutput(
        core_claim="两位创作者在车库制作电脑",
        protected_facts=[
            {
                "fact_id": f"{frame_id}-fact-1",
                "category": "event",
                "statement": source_text,
                "source_evidence": source_text,
            }
        ],
        adjustable_non_core_content=["工作台非核心工具", "局部照明"],
        pure_content_prompt="车库内，两位创作者围绕工作台制作电脑，暖色灯光和真实材质。",
        self_check="pass",
        self_check_failures=[],
    )


def _fusion(frame_id, *, inherited=False, positive=None, fact_ids=None):
    ids = fact_ids or [f"{frame_id}-fact-1"]
    return FusionStageOutput(
        selected_fusion_method="让小皮作为参与工作台场景的唯一实体，与两人共享现场光照",
        non_core_reconstruction_summary=["重新组织工作台工具和人物间距"],
        protected_fact_checks=[
            {
                "fact_id": fact_id,
                "preserved": True,
                "final_image_evidence": "人物、车库和电脑制作事件在画面中可见",
            }
            for fact_id in ids
        ],
        final_manifestation="小皮的单一实体形态",
        target_visual_anchor_instance_count=1,
        other_scene_elements_inherit_identity_features=False,
        spatial_contact_and_lighting_relation="站在工作台旁地面，接触关系、透视和暖色光影一致",
        inherited_existing_fusion_decision=inherited,
        continuity_change_reason=(
            "继承同一连续场景决定，无形态变化"
            if inherited
            else "当前是连续场景首镜"
        ),
        final_positive_prompt=positive
        or "车库内，乔布斯和沃兹尼亚克在工作台组装电脑，小皮以圆形白色脸和蓝色短耳的单一实体站在工作台旁，所有人物共享真实透视、暖色光照与自然接触阴影。",
        final_negative_prompt="重复的小皮，副本，镜像，倒影，悬浮，贴纸边缘，穿模，严重遮挡",
        self_check="pass",
        self_check_failures=[],
    )


def _review(fusion, *, negative_supported=False):
    return PreflightReviewOutput(
        decision="pass",
        failures=[],
        allowed_final_positive_prompt=fusion.final_positive_prompt,
        allowed_final_negative_prompt=(
            fusion.final_negative_prompt if negative_supported else ""
        ),
    )


async def _run(plan, *, content_outputs=None, fusion_outputs=None, review_outputs=None):
    contents = content_outputs or [
        _content(frame.frame_id, frame.source_text) for frame in plan.frames
    ]
    fusions = fusion_outputs or [
        _fusion(frame.frame_id, inherited=index > 0)
        for index, frame in enumerate(plan.frames)
    ]
    reviews = review_outputs or [_review(fusion) for fusion in fusions]
    llm = _QueuedLLM(
        {
            ContentStageOutput: contents,
            FusionStageOutput: fusions,
            PreflightReviewOutput: reviews,
        }
    )
    result = await VisualAnchorTwoStageService().run_batch(
        llm_service=llm,
        storyboard_plan=plan,
        identity_profile=_identity(),
        identity_reference_condition=_reference(),
        target_visual_style="真实电影感",
        target_image_prompt_language="中文",
        task_id="task-two-stage",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
        random_seeds_by_frame={frame.frame_id: 101 + i for i, frame in enumerate(plan.frames)},
        negative_prompt_supported=False,
    )
    return result, llm


@pytest.mark.asyncio
async def test_content_stage_call_has_no_identity_or_reference_inputs():
    result, llm = await _run(_plan())

    first_call = llm.calls[0]
    assert first_call["response_type"] is ContentStageOutput
    assert "小皮" not in first_call["prompt"]
    assert "圆形白色脸" not in first_call["prompt"]
    assert "a" * 64 not in first_call["prompt"]
    assert "identity_profile" not in first_call["prompt"]
    assert result.frames[0].content_stage_input.model_dump().keys() == {
        "frame_id",
        "original_storyboard_text",
        "article_context",
        "previous_frame_summary",
        "next_frame_summary",
        "target_visual_style",
        "target_image_prompt_language",
        "prompt_version",
    }
    assert tuple(inspect.signature(_validate_content_stage_output).parameters) == (
        "stage_input",
        "output",
    )


@pytest.mark.asyncio
async def test_content_stage_retries_its_own_invalid_fact_contract_without_identity_input():
    plan = _plan()
    invalid = _content("frame-a", plan.frames[0].source_text)
    invalid = ContentStageOutput(
        **{
            **invalid.model_dump(),
            "protected_facts": [
                {
                    "fact_id": "frame-a-fact-1",
                    "category": "event",
                    "statement": plan.frames[0].source_text,
                    "source_evidence": "原文中不存在的证据",
                }
            ],
        }
    )

    result, llm = await _run(
        plan,
        content_outputs=[invalid, _content("frame-a", plan.frames[0].source_text)],
    )

    content_calls = [
        call for call in llm.calls if call["response_type"] is ContentStageOutput
    ]
    assert len(content_calls) == 2
    assert result.frames[0].content_stage_output.protected_facts[0].source_evidence == (
        plan.frames[0].source_text
    )


@pytest.mark.asyncio
async def test_fusion_stage_receives_every_required_input():
    result, llm = await _run(_plan())

    fusion_call = next(call for call in llm.calls if call["response_type"] is FusionStageOutput)
    for field_name in (
        "original_storyboard_text",
        "content_stage_output",
        "identity_profile",
        "identity_reference_condition",
        "continuous_scene_context",
    ):
        assert f'"{field_name}"' in fusion_call["prompt"]
    fusion_input = result.frames[0].fusion_stage_input
    assert fusion_input.identity_reference_condition.asset_sha256 == "a" * 64
    assert fusion_input.content_stage_output.protected_facts


@pytest.mark.asyncio
async def test_fusion_must_preserve_every_protected_fact():
    plan = _plan()
    content = _content("frame-a", plan.frames[0].source_text)
    content = ContentStageOutput(
        **{
            **content.model_dump(),
            "protected_facts": [
                *[fact.model_dump() for fact in content.protected_facts],
                {
                    "fact_id": "frame-a-fact-2",
                    "category": "place",
                    "statement": "地点是车库",
                    "source_evidence": "车库",
                },
            ],
        }
    )
    with pytest.raises(VisualAnchorTwoStageError, match="exactly cover"):
        await _run(
            plan,
            content_outputs=[content],
            fusion_outputs=[_fusion("frame-a"), _fusion("frame-a")],
        )


@pytest.mark.asyncio
async def test_final_prompt_rejects_candidate_language():
    with pytest.raises(VisualAnchorTwoStageError, match="candidate"):
        await _run(
            _plan(),
            fusion_outputs=[
                _fusion(
                    "frame-a",
                    positive="小皮站在工作台旁，或者也可以出现在墙面图案中。",
                ),
                _fusion(
                    "frame-a",
                    positive="小皮站在工作台旁，或者也可以出现在墙面图案中。",
                ),
            ],
        )


@pytest.mark.asyncio
async def test_preflight_reexecutes_complete_fusion_when_identity_semantics_are_missing():
    incomplete = _fusion(
        "frame-a",
        positive="车库内，乔布斯和沃兹尼亚克在工作台组装电脑，一只小鸟自然站在工作台旁。",
    )
    complete = _fusion("frame-a")

    failed_review = PreflightReviewOutput(
        decision="fail",
        failures=["最终画面缺少足以识别同一身份的核心特征"],
        allowed_final_positive_prompt="",
        allowed_final_negative_prompt="",
    )
    result, llm = await _run(
        _plan(),
        fusion_outputs=[incomplete, complete],
        review_outputs=[failed_review, _review(complete)],
    )

    fusion_calls = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ]
    assert len(fusion_calls) == 2
    assert "缺少足以识别同一身份" in fusion_calls[1]["prompt"]
    assert result.frames[0].generation_request.final_positive_prompt == (
        complete.final_positive_prompt
    )


@pytest.mark.asyncio
async def test_preflight_allows_semantically_equivalent_identity_wording():
    fusion = _fusion(
        "frame-a",
        positive=(
            "车库内，乔布斯和沃兹尼亚克在工作台组装电脑，名叫小皮的唯一小动物"
            "拥有雪白圆脸与湛蓝短耳，自然站在工作台旁并共享暖色光影。"
        ),
    )
    result, _ = await _run(_plan(), fusion_outputs=[fusion])

    assert "雪白圆脸" in result.frames[0].generation_request.final_positive_prompt


@pytest.mark.asyncio
async def test_generation_request_contains_only_one_instance_and_clean_prompt():
    result, _ = await _run(_plan())
    request = result.frames[0].generation_request

    assert request.target_visual_anchor_instance_count == 1
    assert request.generation_attempt == 1
    assert request.preflight_review_decision == "pass"
    assert "selected_fusion_method" not in request.model_dump()
    assert "non_core_reconstruction_summary" not in request.model_dump()
    assert "或者" not in request.final_positive_prompt

    with pytest.raises(ValidationError, match="candidate or planning"):
        VisualAnchorImageGenerationRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "final_negative_prompt": "另一种形式也可以",
            }
        )


@pytest.mark.asyncio
async def test_failed_preflight_reexecutes_complete_fusion_once():
    first_fusion = _fusion("frame-a")
    second_fusion = _fusion(
        "frame-a",
        positive="车库内两人继续组装电脑，小皮以圆形白色脸和蓝色短耳的单一实体自然站在工作台旁，地面接触、透视和暖色阴影完整。",
    )
    failed_review = PreflightReviewOutput(
        decision="fail",
        failures=["空间接触关系证据不足"],
        allowed_final_positive_prompt="",
        allowed_final_negative_prompt="",
    )
    result, llm = await _run(
        _plan(),
        fusion_outputs=[first_fusion, second_fusion],
        review_outputs=[failed_review, _review(second_fusion)],
    )

    assert result.frames[0].fusion_attempt_count == 2
    fusion_calls = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ]
    assert len(fusion_calls) == 2
    assert "空间接触关系证据不足" in fusion_calls[1]["prompt"]
    assert result.frames[0].generation_request.final_positive_prompt == (
        second_fusion.final_positive_prompt
    )


@pytest.mark.asyncio
async def test_two_stage_result_renders_without_audit_fields_leaking_into_image_prompt():
    result, _ = await _run(_plan())
    rendered = _render_two_stage_prompt(result.frames[0])

    assert rendered.prompt == result.frames[0].generation_request.final_positive_prompt
    assert rendered.negative_prompt is None
    assert "selected_fusion_method" not in rendered.prompt
    assert rendered.metadata_to_dict()["generation_request"][
        "target_visual_anchor_instance_count"
    ] == 1


@pytest.mark.asyncio
async def test_enabled_composer_uses_two_stage_contract_and_preserves_disabled_path(
    monkeypatch,
):
    plan = _plan()

    async def fake_base_batch(**kwargs):
        raise AssertionError(
            "enabled two-stage fusion must bypass the legacy prompt generator"
        )

    monkeypatch.setattr(
        "pixelle_video.services.visual_prompt_composer.generate_styled_image_prompt_batch",
        fake_base_batch,
    )
    contents = [_content("frame-a", plan.frames[0].source_text)]
    fusions = [_fusion("frame-a")]
    llm = _QueuedLLM(
        {
            ContentStageOutput: contents,
            FusionStageOutput: fusions,
            PreflightReviewOutput: [
                _review(fusions[0], negative_supported=True)
            ],
        }
    )
    project_root = Path(__file__).resolve().parents[2]
    workflow_path = (
        project_root
        / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
    )
    media_service = SimpleNamespace(
        _resolve_workflow=lambda **kwargs: {
            "source": "selfhost",
            "path": str(workflow_path),
            "key": "selfhost/image_z_image_turbo_gguf_reference.json",
        }
    )
    reference_patch_token = set_reference_image_visual_story_context_patch(
        {
            "reference_image": {
                "enabled": True,
                "asset": {
                    "sha256": "a" * 64,
                    "workflow_asset_relative_path": "reference_image/workflow.png",
                    "mime_type": "image/png",
                    "width": 512,
                    "height": 512,
                    "byte_size": 1024,
                },
            }
        }
    )
    try:
        batch = await VisualPromptComposer().compose(
            llm_service=llm,
            storyboard_plan=plan,
            image_config={},
            workflow="selfhost/image_z_image_turbo_gguf_reference.json",
            media_service=media_service,
            media_type="image",
            series_visual_signature_request=SeriesVisualSignatureRequest(
                enabled=True,
                asset_bible_id="bible-a",
                profile_id="profile-pixelle",
                user_hint="private-user-hint-must-not-be-persisted",
                generation_world_hint="private-world-hint-must-not-be-persisted",
            ),
            series_visual_signature_profile_snapshot=VisualSignatureProfileSnapshot(
                profile_id="profile-pixelle",
                display_name="小皮",
                core_identity_traits=("圆形白色脸", "蓝色短耳"),
                supporting_identity_traits=("橙色围巾",),
                forbidden_traits=("改变脸型",),
                source_asset_ids=("asset-pixelle-reference",),
            ),
            task_id="task-two-stage",
            random_seeds_by_frame={"frame-a": 101},
        )
    finally:
        reset_reference_image_visual_story_context_patch(reference_patch_token)

    assert batch.prompts == [fusions[0].final_positive_prompt]
    assert batch.planning_snapshot["visual_anchor_generation_request_by_frame"][
        "frame-a"
    ]["random_seed"] == 101
    assert "series_visual_signature_trace_by_frame" not in batch.planning_snapshot
    assert batch.prompt_plan_bundle.prompt_plans[0].final_prompt == (
        fusions[0].final_positive_prompt
    )
    request_audit = batch.planning_snapshot[
        "series_visual_signature_request_audit"
    ]
    assert request_audit["contains_user_hint"] is True
    assert request_audit["contains_generation_world_hint"] is True
    assert "private-user-hint-must-not-be-persisted" not in str(
        batch.planning_snapshot
    )
    assert "private-world-hint-must-not-be-persisted" not in str(
        batch.planning_snapshot
    )


def test_missing_reference_condition_fails_before_fusion():
    plan = _plan()
    with pytest.raises(ValidationError):
        FusionStageInput.model_validate(
            {
                "frame_id": "frame-a",
                "original_storyboard_text": plan.frames[0].source_text,
                "content_stage_output": _content(
                    "frame-a", plan.frames[0].source_text
                ).model_dump(),
                "identity_profile": _identity().model_dump(),
                "continuous_scene_context": {
                    "scene_id": "scene-a",
                    "previous_frame_summary": "首镜，无前一镜",
                    "next_frame_summary": "末镜，无后一镜",
                    "continuity_anchors": [],
                    "existing_fusion_decision": "无既有融合决策",
                },
                "target_visual_style": "真实电影感",
                "target_image_prompt_language": "中文",
            }
        )


@pytest.mark.parametrize("decision", ["unknown", "skipped", "timeout"])
def test_unknown_skipped_or_timeout_review_state_cannot_pass(decision):
    with pytest.raises(ValidationError):
        PreflightReviewOutput.model_validate(
            {
                "decision": decision,
                "failures": [],
                "allowed_final_positive_prompt": "小皮在场景中",
                "allowed_final_negative_prompt": "",
            }
        )


@pytest.mark.asyncio
async def test_continuous_scene_inherits_previous_fusion_decision():
    result, llm = await _run(_plan(continuous=True))

    second = result.frames[1]
    assert second.fusion_stage_input.continuous_scene_context.scene_id == (
        result.frames[0].fusion_stage_input.continuous_scene_context.scene_id
    )
    assert "最终表现形态" in (
        second.fusion_stage_input.continuous_scene_context.existing_fusion_decision
    )
    second_fusion_call = [
        call for call in llm.calls if call["response_type"] is FusionStageOutput
    ][1]
    assert "小皮的单一实体形态" in second_fusion_call["prompt"]


@pytest.mark.asyncio
async def test_visual_anchor_frame_disallows_generation_retries():
    result, _ = await _run(_plan())
    request = result.frames[0].generation_request
    frame = StoryboardFrame(
        index=0,
        frame_id="frame-a",
        narration="旁白",
        image_prompt=request.final_positive_prompt,
        generation_seed=request.random_seed,
        visual_anchor_generation_request=request.model_dump(mode="json"),
    )
    with pytest.raises(ValueError, match="exactly one"):
        await FrameProcessor(SimpleNamespace())._step_generate_media_with_validation(
            frame,
            SimpleNamespace(),
            max_attempts=2,
        )


def test_actual_workflow_reference_input_reaches_first_image_sampler():
    project_root = Path(__file__).resolve().parents[2]
    workflow_path = (
        project_root
        / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
    )
    inspection = inspect_identity_reference_workflow(
        workflow_info={
            "source": "selfhost",
            "path": str(workflow_path),
            "key": "selfhost/image_z_image_turbo_gguf_reference.json",
        },
        reference_asset_trace={
            "sha256": "a" * 64,
            "workflow_asset_relative_path": "reference_image/workflow.png",
            "mime_type": "image/png",
            "width": 512,
            "height": 512,
            "byte_size": 1024,
        },
        project_root=project_root,
    )

    assert inspection.condition.workflow_parameter == "reference_image"
    assert inspection.condition.binding_path_node_ids == ["92", "93", "94", "3"]
    assert inspection.condition.conditioning_node_class_type == "ReferenceLatent"
    assert inspection.condition.sampler_node_class_type == "KSampler"


def test_default_z_image_workflow_resolves_same_model_reference_variant():
    project_root = Path(__file__).resolve().parents[2]
    workflow_by_key = {
        "selfhost/image_z_image_turbo_gguf.json": (
            project_root / "workflows/selfhost/image_z_image_turbo_gguf.json"
        ),
        "selfhost/image_z_image_turbo_gguf_reference.json": (
            project_root
            / "workflows/selfhost/image_z_image_turbo_gguf_reference.json"
        ),
    }

    class _MediaService:
        def _resolve_workflow(self, *, workflow=None, workflow_domain=None):
            assert workflow_domain == "image"
            key = workflow or "selfhost/image_z_image_turbo_gguf.json"
            return {
                "source": "selfhost",
                "path": str(workflow_by_key[key]),
                "key": key,
            }

    assert resolve_visual_anchor_reference_workflow_key(
        media_service=_MediaService(),
        workflow=None,
    ) == "selfhost/image_z_image_turbo_gguf_reference.json"


def test_first_generation_binding_validates_actual_task_local_reference(tmp_path):
    reference_path = tmp_path / "reference_image/workflow.png"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"identity-reference")
    reference_sha256 = hashlib.sha256(b"identity-reference").hexdigest()
    request = VisualAnchorImageGenerationRequest(
        task_id="task-two-stage",
        frame_id="frame-a",
        random_seed=101,
        final_positive_prompt="小皮在车库工作台旁",
        final_negative_prompt="",
        identity_profile_id="profile-pixelle",
        identity_resource_version="identity-v1",
        identity_content_sha256="b" * 64,
        identity_reference_condition=_reference(asset_sha256=reference_sha256),
        content_stage_prompt_version=CONTENT_STAGE_PROMPT_VERSION,
        fusion_stage_prompt_version=FUSION_STAGE_PROMPT_VERSION,
        preflight_review_prompt_version=PREFLIGHT_REVIEW_PROMPT_VERSION,
        preflight_review_decision="pass",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
    )
    binding = {
        "status": "injected",
        "injection_mode": "required",
        "summary": {
            "param_names": ["reference_image"],
            "asset": {
                "sha256": "d" * 64,
                "workflow_sha256": reference_sha256,
                "workflow_asset_relative_path": "reference_image/workflow.png",
            },
        },
    }
    audit = validate_visual_anchor_first_generation_binding(
        request_payload=request.model_dump(mode="json"),
        prompt=request.final_positive_prompt,
        negative_prompt=None,
        seed=101,
        media_type="image",
        trace_context={
            "task_id": "task-two-stage",
            "frame_id": "frame-a",
            "task_root": str(tmp_path),
        },
        workflow_info={"key": request.workflow_key, "source": "selfhost"},
        workflow_file_trace={"workflow_file_sha256": "c" * 64},
        reference_binding_trace=binding,
        workflow_params={"reference_image": str(reference_path)},
    )

    assert audit["status"] == "ready_to_submit"
    assert audit["actual_binding"]["asset_sha256"] == reference_sha256
    from pixelle_video.services.visual_anchor_generation_binding import (
        visual_anchor_first_request_binding_artifact_relative_path,
    )

    assert (
        tmp_path
        / visual_anchor_first_request_binding_artifact_relative_path("frame-a")
    ).is_file()


def test_reference_context_is_removed_only_from_identity_enabled_content_boundary():
    source = {
        "reference_image": {"enabled": True, "asset_sha256": "a" * 64},
        "selected_visual_route": {"route_id": "route-a", "route_name": "纪实"},
    }

    isolated = _content_only_visual_story_context(
        source,
        identity_isolation_enabled=True,
    )
    ordinary = _content_only_visual_story_context(
        source,
        identity_isolation_enabled=False,
    )

    assert "reference_image" not in isolated
    assert ordinary["reference_image"]["asset_sha256"] == "a" * 64


def test_seed_registration_is_complete_and_deterministic():
    plan = _plan(continuous=True)
    first = resolve_registered_random_seeds(
        storyboard_plan=plan,
        task_id="task-two-stage",
    )
    second = resolve_registered_random_seeds(
        storyboard_plan=plan,
        task_id="task-two-stage",
    )

    assert first == second
    assert set(first) == {"frame-a", "frame-b"}
    with pytest.raises(VisualAnchorTwoStageError, match="every frame"):
        resolve_registered_random_seeds(
            storyboard_plan=plan,
            task_id="task-two-stage",
            media_seed_by_frame={"frame-a": 1},
        )
