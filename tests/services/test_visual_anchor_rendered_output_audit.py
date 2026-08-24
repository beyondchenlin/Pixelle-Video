import hashlib
import json

import pytest
from PIL import Image

from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_STAGE_PROMPT_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    ContentStageInput,
    ContentStageOutput,
    ContinuousSceneContext,
    FusionStageInput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    TargetVisualStyle,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
    VisualAnchorTwoStageFrameResult,
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
        target_visual_style=target_style,
        target_image_prompt_language="中文",
    )
    content_output = ContentStageOutput(
        core_claim="两位创作者组装电脑",
        protected_facts=[
            {
                "fact_id": "fact-1",
                "category": "person",
                "subject_ids": ["subject-creators"],
                "statement": "两位创作者组装电脑",
                "source_evidence": "两位创作者",
                "pure_content_prompt_evidence": "两位创作者",
            },
            {
                "fact_id": "fact-2",
                "category": "product",
                "subject_ids": ["subject-computer"],
                "statement": "电脑正在被组装",
                "source_evidence": "电脑",
                "pure_content_prompt_evidence": "电脑",
            },
        ],
        primary_subject={
            "subject_id": "subject-creators",
            "role": "primary",
            "category": "person",
            "name": "两位创作者",
            "identity": "在车库创业的电脑创作者",
            "quantity": 2,
            "action": "组装电脑",
            "source_evidence": "两位创作者",
            "pure_content_prompt_evidence": "两位创作者",
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
                "source_evidence": "电脑",
                "pure_content_prompt_evidence": "电脑",
            }
        ],
        adjustable_non_core_content=["工作台工具"],
        pure_content_prompt="两位创作者在车库工作台组装电脑。",
        self_check="pass",
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
        required_single_instance_prompt_fragment="画面中只有一只小皮",
    )
    fusion_output = FusionStageOutput(
        selected_fusion_method="小皮作为工作台旁的唯一实体参与现场",
        unselected_candidate_summaries=[
            {
                "manifestation": "墙面图形",
                "audit_summary": "实体形态更符合车库空间关系",
            }
        ],
        content_stage_deviations=[],
        non_core_reconstruction_summary=["重新组织工具间距"],
        protected_fact_checks=[
            {
                "fact_id": "fact-1",
                "preserved": True,
                "final_image_evidence": "两位创作者在车库组装电脑",
            },
            {
                "fact_id": "fact-2",
                "preserved": True,
                "final_image_evidence": "电脑",
            },
        ],
        primary_subject_preserved=True,
        primary_subject_final_prompt_evidence="两位创作者",
        visual_anchor_replaces_primary_subject=False,
        identity_trait_checks=[
            {
                "trait": "圆形白色脸",
                "preserved": True,
                "final_prompt_evidence": "圆形白色脸",
            },
            {
                "trait": "蓝色短耳",
                "preserved": True,
                "final_prompt_evidence": "蓝色短耳",
            },
        ],
        final_manifestation="小皮的单一实体形态",
        target_visual_anchor_instance_count=1,
        other_scene_elements_inherit_identity_features=False,
        single_instance_prompt_evidence="画面中只有一只小皮",
        spatial_contact_and_lighting_relation="接触地面并共享车库光照",
        inherited_existing_fusion_decision=False,
        continuity_change_reason="独立镜头没有既有决定",
        final_positive_prompt=(
            "两位创作者在车库组装电脑。画面中只有一只小皮，"
            "它以圆形白色脸和蓝色短耳的单一实体自然参与现场。"
        ),
        final_negative_prompt="",
        self_check="pass",
    )
    request = VisualAnchorImageGenerationRequest(
        task_id="task-two-stage",
        frame_id="frame-a",
        random_seed=101,
        selected_fusion_method=fusion_output.selected_fusion_method,
        final_manifestation=fusion_output.final_manifestation,
        protected_fact_checks=fusion_output.protected_fact_checks,
        primary_subject_name=content_output.primary_subject.name,
        primary_subject_preserved=True,
        primary_subject_final_prompt_evidence=(
            fusion_output.primary_subject_final_prompt_evidence
        ),
        visual_anchor_replaces_primary_subject=False,
        identity_trait_checks=fusion_output.identity_trait_checks,
        single_instance_prompt_evidence=(
            fusion_output.single_instance_prompt_evidence
        ),
        final_positive_prompt=fusion_output.final_positive_prompt,
        final_negative_prompt="",
        identity_profile_id=identity.profile_id,
        identity_display_name=identity.display_name,
        identity_core_traits=identity.core_identity_traits,
        identity_resource_version=identity.identity_resource_version,
        identity_content_sha256=identity.identity_content_sha256,
        identity_conditioning_mode="reference_image",
        identity_reference_condition=reference,
        target_visual_style=target_style,
        content_stage_prompt_version=CONTENT_STAGE_PROMPT_VERSION,
        fusion_stage_prompt_version=FUSION_STAGE_PROMPT_VERSION,
        negative_prompt_supported=False,
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
                "schema_version": "visual_anchor_first_generation_binding_audit.v4",
                "request_version": request.request_version,
                "status": "passed",
                "task_id": request.task_id,
                "frame_id": request.frame_id,
                "generation_attempt": 1,
                "random_seed": seed,
                "target_visual_anchor_instance_count": 1,
                "selected_fusion_method": request.selected_fusion_method,
                "final_manifestation": request.final_manifestation,
                "protected_fact_checks": [
                    check.model_dump(mode="json")
                    for check in request.protected_fact_checks
                ],
                "identity_trait_checks": [
                    check.model_dump(mode="json")
                    for check in request.identity_trait_checks
                ],
                "single_instance_prompt_evidence": (
                    request.single_instance_prompt_evidence
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
                },
                "identity_profile_id": request.identity_profile_id,
                "identity_display_name": request.identity_display_name,
                "identity_core_traits": list(request.identity_core_traits),
                "identity_resource_version": request.identity_resource_version,
                "identity_content_sha256": request.identity_content_sha256,
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
