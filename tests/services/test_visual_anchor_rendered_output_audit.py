import hashlib
import json

import pytest
from PIL import Image

from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_PROMPT_ASSEMBLY_VERSION,
    CONTENT_STAGE_PROMPT_VERSION,
    FINALIZATION_PROMPT_PASSTHROUGH_VERSION,
    FINALIZATION_STAGE_PROMPT_VERSION,
    FUSION_PROMPT_ASSEMBLY_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    ContentStageInput,
    ContentStageModelOutput,
    ContentStageOutput,
    ContinuousSceneContext,
    FinalizationStageInput,
    FinalizationStagePromptPassthrough,
    FusionStageInput,
    FusionStageModelOutput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    TargetVisualStyle,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
    VisualAnchorTwoStageFrameResult,
    assemble_content_stage_prompt,
    assemble_fusion_negative_prompt,
    assemble_fusion_positive_prompt,
    assemble_identity_prompt_clause,
    prompt_assembly_trace_from_fusion_output,
)
from pixelle_video.services.visual_anchor_generation_binding import (
    visual_anchor_first_request_binding_artifact_relative_path,
)
from pixelle_video.services.visual_anchor_rendered_output_audit import (
    VisualAnchorRenderedOutputAudit,
    VisualAnchorRenderedOutputAuditError,
)


def _write_png(path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), color).save(path, format="PNG")


def _frame_result(tmp_path):
    reference_path = tmp_path / "reference_image/workflow.png"
    _write_png(reference_path, "blue")
    reference_sha256 = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    identity = VisualAnchorIdentityProfile(
        profile_id="profile-pixelle",
        display_name="小皮",
        core_identity_traits=["圆形白色脸", "蓝色短耳"],
        supporting_identity_traits=["橙色围巾"],
        forbidden_traits=["改变脸型"],
        source_asset_ids=[
            "asset-pixelle-reference",
            "reference-image:" + reference_sha256,
        ],
        identity_content_sha256="b" * 64,
        identity_resource_version="identity:profile-pixelle:" + "b" * 64,
    )
    reference = IdentityReferenceCondition(
        asset_sha256=reference_sha256,
        workflow_asset_relative_path="reference_image/workflow.png",
        mime_type="image/png",
        width=32,
        height=24,
        byte_size=reference_path.stat().st_size,
        resource_version="reference-image:" + reference_sha256,
        workflow_parameter="reference_image",
        workflow_node_id="92",
        workflow_node_class_type="LoadImage",
        workflow_node_input_field="image",
        conditioning_node_id="94",
        conditioning_node_class_type="TextEncodeZImageOmni",
        sampler_node_id="3",
        sampler_node_class_type="KSampler",
        binding_path_node_ids=["92", "93", "94", "3"],
    )
    target_style = TargetVisualStyle(description="真实电影感")
    content_input = ContentStageInput(
        frame_id="frame-a",
        original_storyboard_text="两位创作者在车库组装电脑。",
        article_context="两位创作者在车库组装电脑。",
        previous_frame_summary="首镜，无前一镜",
        next_frame_summary="末镜，无后一镜",
        target_image_prompt_language="中文",
    )
    content_model_output = ContentStageModelOutput(
        core_claim="两位创作者组装电脑",
        shot_purpose="让观众看清两位创作者共同组装电脑的行动",
        renderable_story_beats=["两人的手同时连接工作台上的电脑部件"],
        decisive_moment="两人的手同时停在刚接通的电脑部件两侧",
        scene_facts=[
            {"category": "person", "statement": "两位创作者组装电脑"},
            {"category": "product", "statement": "电脑正在被组装"},
        ],
        primary_subject={
            "subject_id": "subject-creators",
            "role": "primary",
            "category": "person",
            "name": "两位创作者",
            "identity": "在车库创业的电脑创作者",
            "quantity": 2,
            "action": "组装电脑",
        },
        secondary_subjects=[
            {
                "subject_id": "subject-computer",
                "role": "secondary",
                "category": "product",
                "name": "电脑",
                "identity": "工作台上的技术产品",
                "quantity": 1,
                "action": "正在被组装",
            }
        ],
        content_subject_interaction="两位创作者共同操作同一台电脑",
        composition_plan={
            "shot_scale_and_camera": "平视中景",
            "foreground": "焊锡和散开的电子元件",
            "midground": "两位创作者与正在组装的电脑",
            "background": "车库门与储物架",
            "visual_focus": "两人的手与刚接通的电脑部件",
        },
        adjacent_shot_distinction="独立镜头以共同组装动作建立事件",
        adjustable_non_core_content=["工作台工具"],
    )
    content_output = ContentStageOutput(
        **content_model_output.model_dump(mode="json"),
        prompt_assembly_version=CONTENT_PROMPT_ASSEMBLY_VERSION,
        pure_content_prompt=assemble_content_stage_prompt(
            content_model_output,
        ),
    )
    continuity = ContinuousSceneContext(
        scene_id="independent:frame-a",
        previous_frame_summary="首镜，无前一镜",
        next_frame_summary="末镜，无后一镜",
        continuity_anchors=[],
        existing_fusion_decision="无既有融合决策（独立镜头）",
    )
    fusion_input = FusionStageInput(
        frame_id="frame-a",
        original_storyboard_text=content_input.original_storyboard_text,
        content_stage_output=content_output,
        identity_profile=identity,
        identity_conditioning_mode="reference_image",
        identity_reference_condition=reference,
        workflow_identity_condition_summary="当前工作流使用真实参考图绑定身份",
        continuous_scene_context=continuity,
        target_visual_style=target_style,
        negative_prompt_supported=False,
        target_image_prompt_language="中文",
    )
    fusion_model_output = FusionStageModelOutput(
        selected_fusion_method="小皮作为工作台旁的唯一实体参与现场",
        final_manifestation="小皮的单一实体形态",
        relative_scale_and_visual_weight="膝盖高度，视觉权重低于两位创作者和电脑",
        support_carrier_and_material_relation="由车库地面支撑，前爪接触工作台下沿",
        visual_identity_scene_interaction="靠近并观察两位创作者组装电脑",
        spatial_contact_and_lighting_relation="接触地面并共享车库光照",
        inherited_existing_fusion_decision=False,
        continuity_change_reason="",
        scene_negative_prompt="",
    )
    identity_prompt_clause = assemble_identity_prompt_clause(
        fusion_model_output,
        identity_profile=identity,
        target_image_prompt_language="中文",
    )
    fusion_output = FusionStageOutput(
        **fusion_model_output.model_dump(mode="json"),
        prompt_assembly_version=FUSION_PROMPT_ASSEMBLY_VERSION,
        base_content_prompt=content_output.pure_content_prompt,
        identity_prompt_clause=identity_prompt_clause,
        final_positive_prompt=assemble_fusion_positive_prompt(
            fusion_model_output,
            content_stage_output=content_output,
            identity_prompt_clause=identity_prompt_clause,
            identity_profile=identity,
            target_visual_style=target_style,
            visible_text_policy=fusion_input.visible_text_policy,
            negative_prompt_supported=False,
            target_image_prompt_language="中文",
        ),
        final_negative_prompt=assemble_fusion_negative_prompt(
            fusion_model_output,
            identity_profile=identity,
            target_visual_style=target_style,
            visible_text_policy=fusion_input.visible_text_policy,
            negative_prompt_supported=False,
        ),
    )
    finalization_input = FinalizationStageInput(
        frame_id="frame-a",
        original_storyboard_text=content_input.original_storyboard_text,
        fusion_stage_input=fusion_input,
        fusion_stage_output=fusion_output,
        series_final_prompt_history=[],
    )
    finalization_output = FinalizationStagePromptPassthrough(
        passthrough_version=FINALIZATION_PROMPT_PASSTHROUGH_VERSION,
        raw_prompt=fusion_output.final_positive_prompt,
    )
    request = VisualAnchorImageGenerationRequest(
        task_id="task-two-stage",
        frame_id="frame-a",
        random_seed=101,
        selected_fusion_method=fusion_output.selected_fusion_method,
        final_manifestation=fusion_output.final_manifestation,
        prompt_assembly_trace=prompt_assembly_trace_from_fusion_output(fusion_output),
        final_positive_prompt=fusion_output.final_positive_prompt,
        final_negative_prompt="",
        identity_profile_id=identity.profile_id,
        identity_display_name=identity.display_name,
        identity_core_traits=identity.core_identity_traits,
        identity_forbidden_traits=identity.forbidden_traits,
        identity_resource_version=identity.identity_resource_version,
        identity_content_sha256=identity.identity_content_sha256,
        identity_conditioning_mode="reference_image",
        identity_reference_condition=reference,
        target_visual_style=target_style,
        content_stage_prompt_version=CONTENT_STAGE_PROMPT_VERSION,
        fusion_stage_prompt_version=FUSION_STAGE_PROMPT_VERSION,
        finalization_stage_prompt_version=FINALIZATION_STAGE_PROMPT_VERSION,
        negative_prompt_supported=False,
        target_image_prompt_language="中文",
        workflow_key="selfhost/image_z_image_turbo_gguf_reference.json",
        workflow_version_sha256="c" * 64,
        expected_execution=ImageWorkflowExecutionContract(
            width=32,
            height=24,
            model_files=[
                "Qwen3-4B-Q8_0.gguf",
                "ae.safetensors",
                "z-image-turbo-Q8_0.gguf",
            ],
            steps=5,
            cfg=1.0,
            sampler_name="euler",
            scheduler="simple",
            denoise=1.0,
        ),
    )
    return VisualAnchorTwoStageFrameResult(
        frame_id="frame-a",
        content_stage_input=content_input,
        content_stage_output=content_output,
        fusion_stage_input=fusion_input,
        fusion_stage_output=fusion_output,
        finalization_stage_input=finalization_input,
        finalization_stage_output=finalization_output,
        generation_request=request,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: dict) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_passed_binding(
    tmp_path,
    result_contract: VisualAnchorTwoStageFrameResult,
    image_path,
    *,
    recorded_seed: int | None = None,
):
    request = result_contract.generation_request
    binding_relative_path = visual_anchor_first_request_binding_artifact_relative_path(
        request.frame_id
    )
    binding_path = tmp_path / binding_relative_path
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    captured_path = binding_path.parent / "first_comfyui_output.png"
    captured_path.write_bytes(image_path.read_bytes())
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    seed = request.random_seed if recorded_seed is None else recorded_seed
    model_files = [
        "Qwen3-4B-Q8_0.gguf",
        "ae.safetensors",
        "z-image-turbo-Q8_0.gguf",
    ]
    sampler_config = {
        "seed": seed,
        "steps": 5,
        "cfg": 1.0,
        "sampler_name": "euler",
        "scheduler": "simple",
        "denoise": 1.0,
    }
    execution_config = {
        "workflow_key": request.workflow_key,
        "workflow_version_sha256": request.workflow_version_sha256,
        "width": 32,
        "height": 24,
        "model_files": model_files,
        "sampler": sampler_config,
        "reference_conditioning": {
            "mode": "TextEncodeZImageOmni",
            "input_count": 1,
            "width": 32,
            "height": 32,
            "crop": "disabled",
            "upscale_method": "lanczos",
            "auto_resize_images": False,
        },
    }
    binding_path.write_text(
        json.dumps(
            {
                "schema_version": "visual_anchor_first_generation_binding_audit.v6",
                "request_version": request.request_version,
                "status": "passed",
                "task_id": request.task_id,
                "frame_id": request.frame_id,
                "generation_attempt": 1,
                "random_seed": seed,
                "selected_fusion_method": request.selected_fusion_method,
                "final_manifestation": request.final_manifestation,
                "prompt_assembly_trace": request.prompt_assembly_trace.model_dump(
                    mode="json"
                ),
                "positive_prompt_sha256": _sha256_text(
                    request.final_positive_prompt
                ),
                "negative_prompt_sha256": _sha256_text(
                    request.final_negative_prompt
                ),
                "prompt_versions": {
                    "content_stage": request.content_stage_prompt_version,
                    "fusion_stage": request.fusion_stage_prompt_version,
                    "finalization_stage": (
                        request.finalization_stage_prompt_version
                    ),
                },
                "identity_profile_id": request.identity_profile_id,
                "identity_display_name": request.identity_display_name,
                "identity_core_traits": list(request.identity_core_traits),
                "identity_forbidden_traits": list(request.identity_forbidden_traits),
                "identity_resource_version": request.identity_resource_version,
                "identity_content_sha256": request.identity_content_sha256,
                "target_image_prompt_language": request.target_image_prompt_language,
                "reference_condition": (
                    request.identity_reference_condition.model_dump(mode="json")
                ),
                "workflow_key": request.workflow_key,
                "workflow_version_sha256": request.workflow_version_sha256,
                "expected_execution": request.expected_execution.model_dump(
                    mode="json"
                ),
                "actual_execution": {
                    "comfyui_prompt_id": "prompt-101",
                    "execution_status": "success",
                    "uploaded_reference_sha256": (
                        request.identity_reference_condition.asset_sha256
                    ),
                    "generated_output_sha256": image_sha256,
                    "generated_output_artifact": captured_path.relative_to(
                        tmp_path
                    ).as_posix(),
                    "reference_input_node_id": (
                        request.identity_reference_condition.workflow_node_id
                    ),
                    "conditioning_node_id": (
                        request.identity_reference_condition.conditioning_node_id
                    ),
                    "conditioning_node_class_type": "TextEncodeZImageOmni",
                    "reference_conditioning_mode": "TextEncodeZImageOmni",
                    "reference_conditioning_input_count": 1,
                    "reference_scale_node_id": "93",
                    "reference_scale_node_class_type": "ImageScale",
                    "reference_conditioning_width": 32,
                    "reference_conditioning_height": 32,
                    "reference_conditioning_crop": "disabled",
                    "reference_conditioning_upscale_method": "lanczos",
                    "reference_conditioning_auto_resize": False,
                    "sampler_node_id": (
                        request.identity_reference_condition.sampler_node_id
                    ),
                    "binding_path_node_ids": list(
                        request.identity_reference_condition.binding_path_node_ids
                    ),
                    "width": 32,
                    "height": 24,
                    "model_files": model_files,
                    "sampler_config": sampler_config,
                    "execution_config_sha256": _canonical_sha256(execution_config),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return binding_path


@pytest.mark.asyncio
async def test_rendered_audit_records_original_image_and_first_request_provenance(
    tmp_path,
):
    result_contract = _frame_result(tmp_path)
    image_path = tmp_path / "generated/frame-a.png"
    _write_png(image_path, "red")
    _write_passed_binding(tmp_path, result_contract, image_path)
    audit = VisualAnchorRenderedOutputAudit(task_dir=tmp_path)

    result = await audit.evaluate(
        image_path=image_path,
        frame_result=result_contract,
    )

    assert result.passed is True
    assert result.task_id == "task-two-stage"
    assert result.random_seed == 101
    assert result.image_sha256 == hashlib.sha256(image_path.read_bytes()).hexdigest()
    assert result.recorded_at_utc
    assert result.checks["actual_uploaded_reference_preserved"] is True
    assert result.checks["downloaded_image_matches_first_comfyui_output"] is True
    artifact = json.loads((tmp_path / result.artifact_relative_path).read_text("utf-8"))
    assert artifact["status"] == "passed"
    assert artifact["first_request_binding_artifact"].endswith(
        "first_request_binding.json"
    )


@pytest.mark.asyncio
async def test_failed_rendered_audit_is_blocking_and_never_repairs_or_retries(tmp_path):
    result_contract = _frame_result(tmp_path)
    image_path = tmp_path / "generated/frame-a.png"
    _write_png(image_path, "red")
    original_bytes = image_path.read_bytes()
    _write_passed_binding(
        tmp_path,
        result_contract,
        image_path,
        recorded_seed=999,
    )
    audit = VisualAnchorRenderedOutputAudit(task_dir=tmp_path)

    with pytest.raises(VisualAnchorRenderedOutputAuditError) as exc_info:
        await audit.evaluate(
            image_path=image_path,
            frame_result=result_contract,
        )

    result = exc_info.value.result
    assert result is not None
    assert result.status == "failed"
    assert "random_seed_preserved" in result.failure_codes
    assert "actual_sampler_config_preserved" in result.failure_codes
    assert image_path.read_bytes() == original_bytes
    artifact = json.loads((tmp_path / result.artifact_relative_path).read_text("utf-8"))
    assert artifact["status"] == "failed"
