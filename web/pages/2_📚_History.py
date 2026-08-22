# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
History Page - View generation history and manage tasks
"""
# ruff: noqa: E402

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime
from html import escape
from pathlib import Path

# Add project root to sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from PIL import Image

from pixelle_video.config import config_manager
from pixelle_video.platform_context import CONFIGURED_API_BASE_URL
from pixelle_video.services.visual_anchor_generation_binding import (
    visual_anchor_first_request_binding_artifact_relative_path,
)
from pixelle_video.services.visual_anchor_manual_acceptance import (
    VisualAnchorManualAcceptanceChecks,
    VisualAnchorManualAcceptanceRecord,
    manual_acceptance_artifact_relative_path,
    record_visual_anchor_manual_acceptance,
)
from pixelle_video.utils.os_util import get_task_path
from pixelle_video.utils.secret_redaction import redact_credentials_in_text
from web.components.header import render_header
from web.components.style_config import resolve_storyboard_preset_label
from web.i18n import tr
from web.state.session import get_pixelle_video, init_i18n, init_session_state
from web.utils.async_helpers import run_async
from web.utils.output_media_urls import OutputMediaUrls, build_output_media_urls
from web.utils.render_backend_ui import (
    format_task_boolean,
    get_task_caption_rendering_summary,
    get_task_image_text_policy_summary,
    get_task_render_backend,
    get_task_render_backend_fallback_reason,
    get_task_text_layer_summary,
)
from web.utils.storyboard_history import resolve_history_storyboard_scene_count

# Page config
st.set_page_config(
    page_title="History - 懒人同城",
    page_icon="📚",
    layout="wide",
)


def build_history_page_css() -> str:
    """Build scoped CSS for History task card actions."""
    return """
    <style>
    div[class*="st-key-history_card_actions_"] div[data-testid="stHorizontalBlock"] {
        width: min(12rem, 82%);
        margin-inline: auto;
        gap: 0.6rem !important;
        justify-content: space-between;
    }
    div[class*="st-key-history_card_actions_"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: 0 !important;
    }
    div[class*="st-key-history_card_actions_"] .stColumn button {
        width: 2.2rem !important;
        min-height: 1.45rem;
        padding: 0;
        margin-inline: 0;
        border-radius: 6px;
        font-size: 0.72rem;
        line-height: 1;
    }
    .history-video-cover-link {
        display: block;
        position: relative;
        width: 100%;
        border-radius: 4px;
        overflow: hidden;
        background: #f0f0f0;
    }
    .history-video-cover-link:focus-visible {
        outline: 3px solid #ff4b4b;
        outline-offset: 2px;
    }
    .history-video-cover {
        display: block;
        width: 100%;
        height: 180px;
        object-fit: cover;
        transition: transform 160ms ease, filter 160ms ease;
    }
    .history-video-cover-link:hover .history-video-cover {
        transform: scale(1.02);
        filter: brightness(0.88);
    }
    .history-video-cover-play {
        position: absolute;
        inset: 50% auto auto 50%;
        transform: translate(-50%, -50%);
        display: grid;
        place-items: center;
        width: 2.6rem;
        height: 2.6rem;
        border-radius: 999px;
        color: white;
        background: rgba(15, 23, 42, 0.78);
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.28);
        pointer-events: none;
    }
    @media (prefers-reduced-motion: reduce) {
        .history-video-cover {
            transition: none;
        }
    }
    </style>
    """


def format_duration(seconds: float) -> str:
    """Format duration in seconds to readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def format_file_size(bytes_size: int) -> str:
    """Format file size in bytes to readable string"""
    if bytes_size < 1024:
        return f"{bytes_size}B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f}KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / 1024 / 1024:.1f}MB"
    else:
        return f"{bytes_size / 1024 / 1024 / 1024:.2f}GB"


def format_datetime(iso_string: str) -> str:
    """Format ISO datetime string to readable format"""
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return iso_string


def truncate_text(text: str, max_length: int = 60) -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def build_history_media_urls(
    media_path: str | Path,
    *,
    download_name: str | None = None,
) -> OutputMediaUrls | None:
    """Resolve persistent output media through the file-service boundary."""

    return build_output_media_urls(
        media_path,
        api_base_url=st.session_state.get(
            "api_base_url",
            CONFIGURED_API_BASE_URL,
        ),
        download_name=download_name,
    )


def render_history_video_cover(
    media_urls: OutputMediaUrls,
    *,
    title: str,
) -> bool:
    """Render a lightweight cover without opening the video during list views."""

    if not media_urls.cover_url:
        return False
    stream_url = escape(media_urls.stream_url, quote=True)
    cover_url = escape(media_urls.cover_url, quote=True)
    label = escape(title, quote=True)
    st.markdown(
        (
            f'<a class="history-video-cover-link" href="{stream_url}" '
            'target="_blank" rel="noopener noreferrer" '
            f'aria-label="{label}">'
            f'<img class="history-video-cover" src="{cover_url}" alt="{label}" '
            'loading="lazy" decoding="async" fetchpriority="low" />'
            '<span class="history-video-cover-play" aria-hidden="true">▶</span>'
            "</a>"
        ),
        unsafe_allow_html=True,
    )
    return True


def extract_storyboard_planning_snapshot(detail: dict) -> dict:
    """Read storyboard planning snapshot from task detail payloads."""
    storyboard = detail.get("storyboard")
    storyboard_snapshot = getattr(storyboard, "planning_snapshot", None)
    if storyboard_snapshot:
        return dict(storyboard_snapshot)

    metadata = detail.get("metadata", {}) or {}
    input_snapshot = metadata.get("input", {}).get("storyboard_planning_snapshot")
    if input_snapshot:
        return dict(input_snapshot)

    result_snapshot = metadata.get("result", {}).get("storyboard_planning_snapshot")
    if result_snapshot:
        return dict(result_snapshot)

    return {}


def summarize_storyboard_planning_snapshot(snapshot: dict) -> list[tuple[str, str]]:
    """Summarize the key storyboard planning fields for History UI."""

    def _resolve_preset_label_from_snapshot(
        snapshot_preset: object | None,
        candidate_ids: list[str | None],
        library: dict,
    ) -> str | None:
        if snapshot_preset not in (None, ""):
            snapshot_label = resolve_storyboard_preset_label(snapshot_preset)
            if snapshot_label:
                return snapshot_label

        first_non_empty_candidate = None
        for preset_id in candidate_ids:
            if preset_id in (None, ""):
                continue
            if first_non_empty_candidate is None:
                first_non_empty_candidate = str(preset_id)
            for item in library.get("items", []):
                if item.get("preset_id") == preset_id:
                    return resolve_storyboard_preset_label(item)

        return first_non_empty_candidate

    def _translate_storyboard_option(category: str, value: str | None) -> str | None:
        if value in (None, ""):
            return None

        translation_key = f"storyboard.option.{category}.{value}"
        localized_value = tr(translation_key)
        if localized_value != translation_key:
            return localized_value
        return str(value)

    world_preset_label = _resolve_preset_label_from_snapshot(
        snapshot.get("world_preset"),
        [snapshot.get("world_preset_id")],
        config_manager.get_storyboard_world_preset_library(),
    )
    shot_preset_label = _resolve_preset_label_from_snapshot(
        snapshot.get("shot_preset"),
        [
            snapshot.get("requested_shot_preset_id"),
            snapshot.get("effective_final_shot_preset"),
            snapshot.get("shot_preset_id"),
        ],
        config_manager.get_storyboard_shot_preset_library(),
    )

    summary_items = [
        ("history.detail.storyboard_world_preset", world_preset_label),
        ("history.detail.storyboard_shot_preset", shot_preset_label),
        (
            "history.detail.storyboard_content_mode",
            _translate_storyboard_option(
                "content_mode",
                snapshot.get("resolved_content_mode") or snapshot.get("content_mode"),
            ),
        ),
        (
            "history.detail.storyboard_prompt_language",
            _translate_storyboard_option(
                "prompt_language",
                snapshot.get("storyboard_prompt_language"),
            ),
        ),
        (
            "history.detail.storyboard_consistency",
            _translate_storyboard_option(
                "consistency",
                snapshot.get("selected_consistency_strength")
                or snapshot.get("consistency_strength"),
            ),
        ),
        (
            "history.detail.storyboard_role_strategy",
            _translate_storyboard_option(
                "role_strategy",
                snapshot.get("resolved_role_strategy") or snapshot.get("role_strategy"),
            ),
        ),
        (
            "history.detail.storyboard_role_locking",
            snapshot.get("selected_role_locking_strength")
            or snapshot.get("role_locking_strength"),
        ),
        (
            "history.detail.storyboard_shot_strategy",
            _translate_storyboard_option(
                "shot_strategy",
                snapshot.get("selected_shot_strategy") or snapshot.get("shot_strategy"),
            ),
        ),
    ]

    normalized: list[tuple[str, str]] = []
    for label_key, value in summary_items:
        if value in (None, ""):
            continue
        normalized.append((label_key, str(value)))
    return normalized


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_evidence_runtime_config(value: object) -> dict:
    source = _mapping(value)
    allowed_keys = (
        "llm_model",
        "llm_base_url",
        "comfyui_url",
        "runninghub_enabled",
        "render_backend",
        "render_backend_requested",
        "render_backend_effective",
    )
    return {
        key: redact_credentials_in_text(source[key])
        for key in allowed_keys
        if key in source and source[key] is not None
    }


def _read_task_json_artifact(task_id: str, relative_path: object) -> dict:
    text = str(relative_path or "").strip()
    if not text:
        return {}
    task_root = Path(get_task_path(task_id)).resolve()
    artifact_path = (task_root / text).resolve()
    try:
        artifact_path.relative_to(task_root)
    except ValueError:
        return {}
    if not artifact_path.is_file() or artifact_path.suffix.casefold() != ".json":
        return {}
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return _mapping(payload)


def _task_artifact_file(task_id: str, relative_path: object) -> Path | None:
    text = str(relative_path or "").strip()
    if not text:
        return None
    task_root = Path(get_task_path(task_id)).resolve()
    artifact_path = (task_root / text).resolve()
    try:
        artifact_path.relative_to(task_root)
    except ValueError:
        return None
    if not artifact_path.is_file() or artifact_path.is_symlink():
        return None
    return artifact_path


def _captured_visual_anchor_output(
    task_id: str,
    actual_execution: Mapping[str, object],
) -> Path | None:
    direct = _task_artifact_file(
        task_id,
        actual_execution.get("generated_output_artifact"),
    )
    if direct is not None:
        return direct
    candidates = actual_execution.get("captured_first_output_artifacts")
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        path = _task_artifact_file(task_id, candidate)
        if path is not None:
            return path
    return None


def _visual_anchor_generated_image(frame: object) -> Path | None:
    image_path = str(getattr(frame, "image_path", "") or "").strip()
    if not image_path:
        return None
    path = Path(image_path).resolve()
    return path if path.is_file() else None


def _image_dimensions(path: Path | None) -> str:
    if path is None:
        return "N/A"
    with Image.open(path) as image:
        width, height = image.size
    return f"{width}×{height}"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_visual_anchor_manual_acceptance_form(
    *,
    task_id: str,
    task_title: str,
    frame_id: str,
    random_seed: object,
    generated_image: Path | None,
    preflight_output: Mapping[str, object],
    generation_request: Mapping[str, object],
    reference_condition: Mapping[str, object],
    binding_audit: Mapping[str, object],
    audit: Mapping[str, object],
    manual_acceptance: Mapping[str, object],
) -> None:
    if manual_acceptance:
        st.success("该原图的人工验收记录已锁定；再次判断必须创建新任务。")
        return
    if generated_image is None:
        st.error("缺少未经修改的首次生成原图，不能提交人工验收。")
        return

    audit_checks = _mapping(audit.get("checks"))
    actual_execution = _mapping(binding_audit.get("actual_execution"))
    deterministic_checks = {
        "唯一方案已下发": (
            generation_request.get("target_visual_anchor_instance_count") == 1
            and generation_request.get("generation_attempt") == 1
        ),
        "真实参考已进入首次生成": (
            binding_audit.get("status") == "passed"
            and actual_execution.get("uploaded_reference_sha256")
            == reference_condition.get("asset_sha256")
        ),
        "生成前审查与生成后链路审计完整": (
            preflight_output.get("decision") == "pass"
            and audit.get("status") == "passed"
        ),
        "原图与本地首次生成输出一致": (
            audit_checks.get("downloaded_image_matches_first_comfyui_output") is True
        ),
    }
    st.markdown("**逐图片人工视觉验收**")
    st.json(deterministic_checks, expanded=False)
    if not all(deterministic_checks.values()):
        st.error("确定性链路门禁未全部通过，不能提交人工视觉通过结论。")
        return

    visual_fields = (
        ("protected_facts_visible", "文案核心事实完整可见"),
        ("identity_present", "目标身份真实存在"),
        ("identity_instance_count_one", "目标身份只有一个实例"),
        ("identity_traits_recognizable", "核心身份特征可识别"),
        (
            "perspective_lighting_material_natural",
            "透视、比例、光照和材质符合场景逻辑",
        ),
        (
            "support_contact_occlusion_natural",
            "支撑、接触和遮挡关系自然",
        ),
        (
            "no_sticker_floating_or_penetration",
            "没有贴图感、漂浮、穿模或后贴效果",
        ),
        (
            "size_and_position_fit_current_composition",
            "大小和位置适合当前构图，未套固定比例或位置",
        ),
        (
            "continuous_scene_consistency",
            "连续场景无无理由形态跳变；独立画面核对为不适用通过",
        ),
    )
    form_key = f"visual_anchor_acceptance_{task_id}_{frame_id}"
    with st.form(form_key, clear_on_submit=False):
        acceptance_batch_id = st.text_input(
            "验收批次编号",
            value=task_title if task_title != "N/A" else task_id,
        )
        acceptance_round = st.number_input(
            "验收轮次",
            min_value=1,
            step=1,
            value=1,
        )
        sample_id = st.text_input(
            "样本编号",
            value=f"{task_id}-{frame_id}-{random_seed}",
        )
        reviewer = st.text_input("验收人", value="本地人工验收")
        visual_values = {
            field_name: st.checkbox(label, value=False, key=f"{form_key}_{field_name}")
            for field_name, label in visual_fields
        }
        submitted = st.form_submit_button("锁定本张原图验收结论")
    if not submitted:
        return

    task_root = Path(get_task_path(task_id)).resolve()
    rendered_audit_path = (
        task_root / str(audit.get("artifact_relative_path") or "")
    ).resolve()
    binding_path = (
        task_root / str(audit.get("first_request_binding_artifact") or "")
    ).resolve()
    failed_labels = [
        label
        for field_name, label in visual_fields
        if not visual_values[field_name]
    ]
    checks = VisualAnchorManualAcceptanceChecks(
        **visual_values,
        unique_final_plan_submitted=deterministic_checks["唯一方案已下发"],
        first_generation_reference_bound=deterministic_checks[
            "真实参考已进入首次生成"
        ],
        preflight_and_post_audit_complete=deterministic_checks[
            "生成前审查与生成后链路审计完整"
        ],
        original_first_generation_unmodified=deterministic_checks[
            "原图与本地首次生成输出一致"
        ],
    )
    try:
        seed = int(random_seed)
        record = VisualAnchorManualAcceptanceRecord(
            task_id=task_id,
            acceptance_batch_id=acceptance_batch_id,
            acceptance_round=int(acceptance_round),
            sample_id=sample_id,
            frame_id=frame_id,
            random_seed=seed,
            image_sha256=_file_sha256(generated_image),
            rendered_audit_sha256=_file_sha256(rendered_audit_path),
            first_request_binding_sha256=_file_sha256(binding_path),
            status="passed" if checks.all_passed else "failed",
            checks=checks,
            failure_reasons=[f"{label}未通过" for label in failed_labels],
            reviewer=reviewer,
        )
        record_visual_anchor_manual_acceptance(
            task_dir=task_root,
            image_path=generated_image,
            rendered_audit_path=rendered_audit_path,
            first_request_binding_path=binding_path,
            record=record,
        )
    except (OSError, TypeError, ValueError) as exc:
        st.error(f"人工验收记录保存失败：{exc}")
        return
    st.success("人工验收记录已保存并锁定。")
    st.rerun()


def _render_prompt_evidence(label: str, value: object) -> None:
    st.markdown(f"**{label}**")
    st.code(str(value or "N/A"), language=None, wrap_lines=True)


def render_visual_anchor_two_stage_evidence(
    *,
    task_id: str,
    metadata: dict,
    storyboard: object,
    planning_snapshot: dict,
) -> None:
    """Render screenshot-ready evidence from persisted two-stage task records."""

    batch = _mapping(planning_snapshot.get("visual_anchor_two_stage"))
    raw_frames = batch.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        return

    workflow = _mapping(
        planning_snapshot.get("identity_reference_workflow_inspection")
    )
    audits = _mapping(
        planning_snapshot.get("visual_anchor_rendered_output_audit_by_frame")
    )
    runtime_frames = {
        str(getattr(frame, "frame_id", "") or ""): frame
        for frame in list(getattr(storyboard, "frames", []) or [])
    }
    input_params = _mapping(metadata.get("input"))
    task_title = str(input_params.get("title") or "N/A")
    created_at = str(metadata.get("created_at") or "N/A")
    completed_at = str(metadata.get("completed_at") or "N/A")
    prompt_versions = _mapping(batch.get("prompt_versions"))
    model_files = workflow.get("model_files")
    model_label = "\n".join(str(item) for item in model_files or []) or "N/A"

    st.divider()
    st.markdown("## 视觉锚点二次融合验收证据")
    st.caption(
        f"任务编号：{task_id} ｜ 验收批次编号：{task_title} ｜ "
        f"开始时间：{created_at} ｜ 完成时间：{completed_at}"
    )
    st.caption(
        "提示词版本："
        f"第一阶段 {prompt_versions.get('content_stage', 'N/A')} ｜ "
        f"第二阶段 {prompt_versions.get('fusion_stage', 'N/A')} ｜ "
        f"生成前审查 {prompt_versions.get('preflight_review', 'N/A')}"
    )

    for frame_number, raw_frame in enumerate(raw_frames, start=1):
        if not isinstance(raw_frame, dict):
            continue
        frame_record = dict(raw_frame)
        frame_id = str(frame_record.get("frame_id") or "")
        content_input = _mapping(frame_record.get("content_stage_input"))
        content_output = _mapping(frame_record.get("content_stage_output"))
        fusion_input = _mapping(frame_record.get("fusion_stage_input"))
        fusion_output = _mapping(frame_record.get("fusion_stage_output"))
        preflight_output = _mapping(frame_record.get("preflight_review_output"))
        generation_request = _mapping(frame_record.get("generation_request"))
        identity_profile = _mapping(fusion_input.get("identity_profile"))
        reference_condition = _mapping(
            generation_request.get("identity_reference_condition")
        )
        expected_execution = _mapping(
            generation_request.get("expected_execution")
        )
        audit = _mapping(audits.get(frame_id))
        binding_artifact = (
            audit.get("first_request_binding_artifact")
            or visual_anchor_first_request_binding_artifact_relative_path(
                frame_id
            )
        )
        binding_audit = _read_task_json_artifact(task_id, binding_artifact)
        actual_execution = _mapping(binding_audit.get("actual_execution"))
        actual_model_files = actual_execution.get("model_files")
        actual_model_label = (
            "\n".join(str(item) for item in actual_model_files)
            if isinstance(actual_model_files, list) and actual_model_files
            else model_label
        )
        manual_acceptance = _read_task_json_artifact(
            task_id,
            manual_acceptance_artifact_relative_path(frame_id),
        )
        runtime_frame = runtime_frames.get(frame_id)
        generated_image = (
            _visual_anchor_generated_image(runtime_frame)
            or _captured_visual_anchor_output(task_id, actual_execution)
        )
        audit_status = str(
            audit.get("status")
            or (
                f"首次请求绑定{binding_audit.get('status')}"
                if binding_audit.get("status")
                else "未记录"
            )
        )
        visual_acceptance_status = str(
            manual_acceptance.get("status")
            or audit.get("visual_acceptance_status")
            or "未记录"
        )
        preflight_decision = str(preflight_output.get("decision") or "未记录")

        with st.expander(
            f"分镜 {frame_number} ｜ {frame_id} ｜ 随机种子 "
            f"{generation_request.get('random_seed', 'N/A')} ｜ "
            f"生成前审查 {preflight_decision} ｜ 生成后链路审计 {audit_status} ｜ "
            f"人工图像验收 {visual_acceptance_status}",
            expanded=False,
        ):
            image_column, evidence_column = st.columns([1, 1.35])
            with image_column:
                st.markdown("**未经修改的首次生成原图**")
                if generated_image is None:
                    st.error("首次生成原图不存在")
                else:
                    st.image(str(generated_image), width="stretch")
                st.caption(
                    f"分辨率：{_image_dimensions(generated_image)} ｜ "
                    f"图片校验值："
                    f"{audit.get('image_sha256') or (_file_sha256(generated_image) if generated_image else 'N/A')}"
                )
                st.markdown(
                    f"**任务编号：** {task_id}  \n"
                    f"**分镜编号：** {frame_id}  \n"
                    f"**随机种子：** {generation_request.get('random_seed', 'N/A')}  \n"
                    f"**生成次数：** {generation_request.get('generation_attempt', 'N/A')}  \n"
                    f"**首次生成记录时间：** "
                    f"{binding_audit.get('recorded_at_utc') or audit.get('recorded_at_utc') or 'N/A'}  \n"
                    f"**目标锚点实例数：** "
                    f"{generation_request.get('target_visual_anchor_instance_count', 'N/A')}"
                )
                if manual_acceptance:
                    st.markdown(
                        f"**验收批次编号：** "
                        f"{manual_acceptance.get('acceptance_batch_id', 'N/A')}  \n"
                        f"**验收轮次：** "
                        f"{manual_acceptance.get('acceptance_round', 'N/A')}  \n"
                        f"**样本编号：** "
                        f"{manual_acceptance.get('sample_id', 'N/A')}  \n"
                        f"**验收记录时间：** "
                        f"{manual_acceptance.get('recorded_at_utc', 'N/A')}"
                    )

            with evidence_column:
                _render_prompt_evidence(
                    "原始分镜文案",
                    content_input.get("original_storyboard_text"),
                )
                _render_prompt_evidence(
                    "第一阶段纯内容画面提示词",
                    content_output.get("pure_content_prompt"),
                )
                st.markdown("**受保护事实**")
                st.json(content_output.get("protected_facts") or [], expanded=True)
                st.markdown("**可调整的非核心内容**")
                st.json(
                    content_output.get("adjustable_non_core_content") or [],
                    expanded=True,
                )
                _render_prompt_evidence(
                    "第二阶段选中的唯一融合方式",
                    fusion_output.get("selected_fusion_method"),
                )
                _render_prompt_evidence(
                    "第二阶段目标画面风格",
                    fusion_input.get("target_visual_style"),
                )
                st.markdown("**未进入图片模型的候选摘要**")
                st.json(
                    fusion_output.get("unselected_candidate_summaries") or [],
                    expanded=False,
                )
                st.markdown("**第二阶段非核心重构摘要**")
                st.json(
                    fusion_output.get("non_core_reconstruction_summary") or [],
                    expanded=True,
                )
                st.markdown("**第一阶段偏差及纠正记录**")
                st.json(
                    fusion_output.get("content_stage_deviations") or [],
                    expanded=True,
                )
                _render_prompt_evidence(
                    "视觉锚点最终表现形态",
                    fusion_output.get("final_manifestation"),
                )
                st.markdown("**核心身份特征与最终提示词证据**")
                st.json(
                    generation_request.get("identity_trait_checks") or [],
                    expanded=True,
                )
                _render_prompt_evidence(
                    "单实例提示词证据",
                    generation_request.get("single_instance_prompt_evidence"),
                )
                _render_prompt_evidence(
                    "最终生图正向提示词",
                    generation_request.get("final_positive_prompt"),
                )
                _render_prompt_evidence(
                    "最终生图反向提示词",
                    generation_request.get("final_negative_prompt"),
                )

            st.markdown("**身份档案与真实参考条件**")
            identity_column, workflow_column, review_column = st.columns(3)
            with identity_column:
                st.markdown(
                    f"**身份档案：** {identity_profile.get('display_name', 'N/A')}  \n"
                    f"**档案编号：** {identity_profile.get('profile_id', 'N/A')}  \n"
                    f"**身份资源版本：** "
                    f"{generation_request.get('identity_resource_version', 'N/A')}  \n"
                    f"**生成请求版本：** "
                    f"{generation_request.get('request_version', 'N/A')}  \n"
                    f"**第一阶段提示词版本：** "
                    f"{generation_request.get('content_stage_prompt_version', 'N/A')}  \n"
                    f"**第二阶段提示词版本：** "
                    f"{generation_request.get('fusion_stage_prompt_version', 'N/A')}  \n"
                    f"**生成前审查提示词版本：** "
                    f"{generation_request.get('preflight_review_prompt_version', 'N/A')}  \n"
                    f"**参考资源标识：** "
                    f"{', '.join(identity_profile.get('source_asset_ids') or []) or 'N/A'}  \n"
                    f"**参考图校验值：** "
                    f"{reference_condition.get('asset_sha256', 'N/A')}"
                )
            with workflow_column:
                st.markdown(
                    f"**图片模型文件：**  \n{actual_model_label}  \n"
                    f"**工作流：** {generation_request.get('workflow_key', 'N/A')}  \n"
                    f"**工作流路径：** "
                    f"{workflow.get('workflow_relative_path', 'N/A')}  \n"
                    f"**工作流版本：** "
                    f"{generation_request.get('workflow_version_sha256', 'N/A')}  \n"
                    f"**请求分辨率：** "
                    f"{expected_execution.get('width', 'N/A')}×"
                    f"{expected_execution.get('height', 'N/A')}  \n"
                    f"**请求模型文件：** "
                    f"{expected_execution.get('model_files', 'N/A')}  \n"
                    f"**请求采样配置：** "
                    f"{{'steps': {expected_execution.get('steps', 'N/A')}, "
                    f"'cfg': {expected_execution.get('cfg', 'N/A')}, "
                    f"'sampler_name': {expected_execution.get('sampler_name', 'N/A')}, "
                    f"'scheduler': {expected_execution.get('scheduler', 'N/A')}, "
                    f"'denoise': {expected_execution.get('denoise', 'N/A')}}}  \n"
                    f"**实际分辨率：** "
                    f"{actual_execution.get('width', 'N/A')}×"
                    f"{actual_execution.get('height', 'N/A')}  \n"
                    f"**实际配置版本：** "
                    f"{actual_execution.get('execution_config_sha256', 'N/A')}  \n"
                    f"**实际采样配置：** "
                    f"{actual_execution.get('sampler_config', 'N/A')}  \n"
                    f"**本地生成任务编号：** "
                    f"{actual_execution.get('comfyui_prompt_id', 'N/A')}"
                )
            with review_column:
                st.markdown(
                    f"**实际参考输入：** "
                    f"{reference_condition.get('workflow_parameter', 'N/A')} → "
                    f"{reference_condition.get('workflow_node_input_field', 'N/A')}  \n"
                    f"**输入节点：** {reference_condition.get('workflow_node_id', 'N/A')} "
                    f"({reference_condition.get('workflow_node_class_type', 'N/A')})  \n"
                    f"**条件节点：** {reference_condition.get('conditioning_node_id', 'N/A')} "
                    f"({reference_condition.get('conditioning_node_class_type', 'N/A')})  \n"
                    f"**实际参考条件方式：** "
                    f"{actual_execution.get('reference_conditioning_mode', 'N/A')}  \n"
                    f"**实际参考图数量：** "
                    f"{actual_execution.get('reference_conditioning_input_count', 'N/A')}  \n"
                    f"**实际参考条件尺寸：** "
                    f"{actual_execution.get('reference_conditioning_width', 'N/A')}×"
                    f"{actual_execution.get('reference_conditioning_height', 'N/A')}  \n"
                    f"**实际参考缩放方式：** "
                    f"{actual_execution.get('reference_conditioning_upscale_method', 'N/A')}  \n"
                    f"**实际参考裁剪方式：** "
                    f"{actual_execution.get('reference_conditioning_crop', 'N/A')}  \n"
                    f"**参考图自动放大：** "
                    f"{actual_execution.get('reference_conditioning_auto_resize', 'N/A')}  \n"
                    f"**采样节点：** {reference_condition.get('sampler_node_id', 'N/A')} "
                    f"({reference_condition.get('sampler_node_class_type', 'N/A')})  \n"
                    f"**绑定路径：** "
                    f"{' → '.join(reference_condition.get('binding_path_node_ids') or []) or 'N/A'}"
                )

            st.markdown("**生成前审查与生成后审计**")
            st.json(
                {
                    "生成前审查": preflight_output,
                    "首次生成参考绑定证据": binding_audit,
                    "生成后首次请求完整性审计": audit,
                    "真实图片人工验收": (
                        manual_acceptance
                        if manual_acceptance
                        else {
                            "status": visual_acceptance_status,
                            "reason": "尚未提交逐图片人工验收记录",
                        }
                    ),
                },
                expanded=True,
            )
            _render_visual_anchor_manual_acceptance_form(
                task_id=task_id,
                task_title=task_title,
                frame_id=frame_id,
                random_seed=generation_request.get("random_seed"),
                generated_image=generated_image,
                preflight_output=preflight_output,
                generation_request=generation_request,
                reference_condition=reference_condition,
                binding_audit=binding_audit,
                audit=audit,
                manual_acceptance=manual_acceptance,
            )
            st.markdown("**任务运行配置（已排除凭证）**")
            st.json(
                _safe_evidence_runtime_config(metadata.get("config")),
                expanded=True,
            )


def render_sidebar_controls(pixelle_video):
    """Render sidebar with statistics and filters"""
    with st.sidebar:
        # Statistics
        st.markdown(f"**📊 {tr('history.total_tasks')}**")
        stats = run_async(pixelle_video.history.get_statistics())
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(tr("history.completed_count"), stats.get("completed", 0))
        with col2:
            st.metric(tr("history.failed_count"), stats.get("failed", 0))
        
        st.divider()
        
        # Filters
        st.markdown(f"**🔍 {tr('history.filter_status')}**")
        status_options = {
            "all": tr("history.status_all"),
            "completed": tr("history.status_completed"),
            "failed": tr("history.status_failed"),
            "running": tr("history.status_running"),
            "pending": tr("history.status_pending"),
        }
        
        selected_status = st.selectbox(
            tr("history.filter_status"),
            options=list(status_options.keys()),
            format_func=lambda x: status_options[x],
            key="filter_status",
            label_visibility="collapsed"
        )
        
        filter_status = None if selected_status == "all" else selected_status
        
        # Sort
        st.markdown(f"**📊 {tr('history.sort_by')}**")
        
        sort_options = {
            "created_at": tr("history.sort_created_at"),
            "completed_at": tr("history.sort_completed_at"),
            "title": tr("history.sort_title"),
            "duration": tr("history.sort_duration"),
        }
        
        sort_by = st.selectbox(
            tr("history.sort_by"),
            options=list(sort_options.keys()),
            format_func=lambda x: sort_options[x],
            key="sort_by",
            label_visibility="collapsed"
        )
        
        sort_order_options = {
            "desc": tr("history.sort_order_desc"),
            "asc": tr("history.sort_order_asc"),
        }
        
        sort_order = st.radio(
            "Sort Order",
            options=list(sort_order_options.keys()),
            format_func=lambda x: sort_order_options[x],
            key="sort_order",
            label_visibility="collapsed",
            horizontal=True
        )
        
        # Page size
        page_size = st.selectbox(
            tr("history.page_size"),
            options=[15, 30, 60],
            index=0,
            key="page_size"
        )
        
        return filter_status, sort_by, sort_order, page_size


def render_grid_task_card(task: dict, pixelle_video):
    """Render a compact grid task card"""
    task_id = task["task_id"]
    title = str(task.get("title") or "Untitled")
    status = task.get("status", "unknown")
    created_at = task.get("created_at", "")
    duration = task.get("duration", 0)
    n_frames = task.get("n_frames", 0)
    video_path = task.get("video_path", "")
    download_stem = title[:-4] if title.casefold().endswith(".mp4") else title
    media_urls = (
        build_history_media_urls(
            video_path,
            download_name=f"{download_stem[:120]}.mp4",
        )
        if video_path
        else None
    )
    
    # Status badge
    status_map = {
        "completed": "✅",
        "failed": "❌",
        "running": "⏳",
        "pending": "⏸️",
    }
    status_icon = status_map.get(status, "❓")
    
    # Get input text
    detail = run_async(pixelle_video.history.get_task_detail(task_id))
    input_text = ""
    if detail and detail.get("metadata"):
        input_params = detail["metadata"].get("input", {})
        input_text = input_params.get("text", "")
    
    # Card container
    with st.container():
        # Video preview at top
        if media_urls is None or not render_history_video_cover(
            media_urls,
            title=title,
        ):
            st.markdown(
                "<div style='background: #f0f0f0; height: 180px; display: flex; align-items: center; "
                "justify-content: center; border-radius: 4px; font-size: 48px;'>📹</div>",
                unsafe_allow_html=True
            )
        
        # Title + Status (compact) - show actual title from task
        st.markdown(f"**{status_icon} {truncate_text(title, 50)}**")
        
        # Input content (very short)
        if input_text:
            st.caption(truncate_text(input_text, 60))
        
        # Meta info (one line)
        st.caption(f"🕒 {format_datetime(created_at)} | ⏱️ {format_duration(duration)} | 🎬 {n_frames}")
        
        # Action buttons (compact, centered, 3 actions)
        with st.container(key=f"history_card_actions_{task_id}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("👁️", key=f"view_{task_id}", help=tr("history.task_card.view_detail"), width="stretch"):
                    st.session_state[f"detail_{task_id}"] = True
                    st.rerun()
            
            with col2:
                if media_urls is not None:
                    st.link_button(
                        "⬇️",
                        media_urls.download_url,
                        help=tr("history.task_card.download"),
                        width="stretch",
                    )
                else:
                    st.button("⬇️", key=f"download_disabled_{task_id}", disabled=True, width="stretch")
            
            with col3:
                if st.button("🗑️", key=f"delete_{task_id}", help=tr("history.task_card.delete"), width="stretch"):
                    st.session_state[f"confirm_delete_{task_id}"] = True
                    st.rerun()
        
        # Delete confirmation (show in modal-like way)
        if st.session_state.get(f"confirm_delete_{task_id}", False):
            st.warning("⚠️ 确认删除?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅", key=f"confirm_yes_{task_id}", width="stretch"):
                    try:
                        success = run_async(pixelle_video.history.delete_task(task_id))
                        if success:
                            st.success(tr("history.action.delete_success"))
                            st.session_state[f"confirm_delete_{task_id}"] = False
                            st.rerun()
                        else:
                            st.error("删除失败")
                    except Exception as e:
                        st.error(f"删除失败: {str(e)}")
            with col2:
                if st.button("❌", key=f"confirm_no_{task_id}", width="stretch"):
                    st.session_state[f"confirm_delete_{task_id}"] = False
                    st.rerun()


def render_task_detail_modal(task_id: str, pixelle_video):
    """Render task detail in three-column layout"""
    detail = run_async(pixelle_video.history.get_task_detail(task_id))
    
    if not detail:
        st.error("Task not found")
        return
    
    metadata = detail["metadata"]
    storyboard = detail["storyboard"]
    planning_snapshot = extract_storyboard_planning_snapshot(detail)
    
    # Close button at the top
    if st.button("❌ " + tr("history.detail.close"), key=f"close_detail_top_{task_id}"):
        st.session_state[f"detail_{task_id}"] = False
        st.rerun()
    
    st.markdown(f"**{tr('history.detail.modal_title')}**")
    st.caption(f"{tr('history.detail.task_id')}: {task_id}")
    
    # Three-column layout
    col_input, col_storyboard, col_video = st.columns([1, 1, 1])
    
    # Left column: Input and config
    with col_input:
        st.markdown(f"**📝 {tr('history.detail.input_params')}**")
        
        input_params = metadata.get("input", {})
        
        # Display input parameters
        st.markdown(f"**{tr('history.detail.mode')}:** {input_params.get('mode', 'N/A')}")
        st.markdown(
            f"**{tr('history.detail.storyboard_scene_count')}:** "
            f"{resolve_history_storyboard_scene_count(detail) or 'N/A'}"
        )
        st.markdown(f"**{tr('history.detail.tts_mode')}:** {input_params.get('tts_inference_mode', 'N/A')}")
        st.markdown(f"**{tr('history.detail.voice')}:** {input_params.get('tts_voice', 'N/A')}")
        st.markdown(
            f"**{tr('history.detail.render_backend')}:** {get_task_render_backend(metadata) or 'N/A'}"
        )
        render_backend_fallback_reason = get_task_render_backend_fallback_reason(metadata)
        if render_backend_fallback_reason:
            st.markdown(f"**{tr('history.detail.render_backend_fallback')}**")
            st.caption(
                tr(
                    "history.detail.render_backend_fallback_reason",
                    reason=render_backend_fallback_reason,
                )
            )
        caption_rendering_summary = get_task_caption_rendering_summary(metadata)
        if caption_rendering_summary:
            st.markdown(f"**{tr('history.detail.caption_rendering')}**")
            st.markdown(
                tr(
                    "history.detail.caption_rendering_summary",
                    enabled=format_task_boolean(
                        caption_rendering_summary["enabled"],
                        true_label=tr("history.detail.boolean_yes"),
                        false_label=tr("history.detail.boolean_no"),
                    ),
                    cue_count=caption_rendering_summary["caption_cue_count"],
                    style_profile=caption_rendering_summary["style_profile_id"],
                    targets=caption_rendering_summary["renderer_targets"],
                )
            )
        text_layer_summary = get_task_text_layer_summary(metadata)
        if text_layer_summary:
            st.markdown(f"**{tr('history.detail.text_layer')}**")
            st.markdown(
                tr(
                    "history.detail.text_layer_summary",
                    renderer=text_layer_summary["renderer"],
                    cue_count=text_layer_summary["cue_count"],
                    native_count=text_layer_summary["native_prompt_hint_count"],
                )
            )
        image_text_policy_summary = get_task_image_text_policy_summary(metadata)
        if image_text_policy_summary:
            st.markdown(f"**{tr('history.detail.image_text_policy')}**")
            st.markdown(
                tr(
                    "history.detail.image_text_policy_summary",
                    status=image_text_policy_summary["status"],
                    suppress_embedded_text=format_task_boolean(
                        image_text_policy_summary["suppress_embedded_text"],
                        true_label=tr("history.detail.boolean_yes"),
                        false_label=tr("history.detail.boolean_no"),
                    ),
                )
            )
        planning_summary = summarize_storyboard_planning_snapshot(planning_snapshot)
        if planning_summary:
            st.markdown(f"**{tr('history.detail.storyboard_planning')}**")
            for label_key, value in planning_summary:
                st.markdown(f"**{tr(label_key)}:** {value}")
            override_count = len(planning_snapshot.get("frame_overrides") or [])
            st.markdown(
                f"**{tr('history.detail.storyboard_override_count')}:** {override_count}"
            )
        
        # Input text
        with st.expander(tr("history.detail.text"), expanded=True):
            st.text_area(
                "Input Text",
                value=input_params.get('text', 'N/A'),
                height=200,
                disabled=True,
                label_visibility="collapsed"
            )
    
    # Middle column: Storyboard frames
    with col_storyboard:
        st.markdown(f"**🎬 {tr('history.detail.storyboard')}**")
        
        if storyboard and storyboard.frames:
            for frame in storyboard.frames:
                with st.expander(f"{tr('history.detail.frame')} {frame.index + 1}", expanded=False):
                    st.markdown(f"**{tr('history.detail.narration')}:**")
                    st.caption(frame.narration)
                    
                    if frame.image_prompt:
                        st.markdown(f"**{tr('history.detail.image_prompt')}:**")
                        st.caption(frame.image_prompt)
                    
                    # Show frame preview (small)
                    col1, col2 = st.columns(2)
                    with col1:
                        if frame.composed_image_path and os.path.exists(frame.composed_image_path):
                            st.image(frame.composed_image_path)
                        elif frame.image_path and os.path.exists(frame.image_path):
                            st.image(frame.image_path)
                    with col2:
                        segment_media_urls = (
                            build_history_media_urls(frame.video_segment_path)
                            if frame.video_segment_path
                            else None
                        )
                        if segment_media_urls is not None:
                            st.video(segment_media_urls.stream_url)
                    
                    # Audio player (compact)
                    if frame.audio_path and os.path.exists(frame.audio_path):
                        st.audio(frame.audio_path)
        else:
            st.info("No storyboard data")
    
    # Right column: Final video
    with col_video:
        st.markdown(f"**🎥 {tr('info.video_information')}**")
        
        video_path = metadata.get("result", {}).get("video_path")
        title = str(metadata.get("input", {}).get("title") or "video")
        download_stem = title[:-4] if title.casefold().endswith(".mp4") else title
        media_urls = (
            build_history_media_urls(
                video_path,
                download_name=f"{download_stem[:120]}.mp4",
            )
            if video_path
            else None
        )
        if media_urls is not None:
            st.video(media_urls.stream_url)
            
            # Video info
            result = metadata.get("result", {})
            st.markdown(f"**{tr('info.duration')}:** {format_duration(result.get('duration', 0))}")
            st.markdown(f"**{tr('info.frames')}:** {result.get('n_frames', 0)}")
            st.markdown(f"**{tr('info.file_size')}:** {format_file_size(result.get('file_size', 0))}")

            # Download button
            st.link_button(
                tr("history.detail.download_video"),
                media_urls.download_url,
                width="stretch",
            )
        else:
            st.warning("Video file not found")

    render_visual_anchor_two_stage_evidence(
        task_id=task_id,
        metadata=metadata,
        storyboard=storyboard,
        planning_snapshot=planning_snapshot,
    )
    
    st.divider()
    
    # Close button at the bottom
    if st.button("❌ " + tr("history.detail.close"), key=f"close_detail_bottom_{task_id}"):
        st.session_state[f"detail_{task_id}"] = False
        st.rerun()


def main():
    """Main entry point for History page"""
    # Initialize
    init_session_state()
    init_i18n()
    st.markdown(build_history_page_css(), unsafe_allow_html=True)
    
    # Render header
    render_header()
    
    # Initialize Pixelle-Video
    pixelle_video = get_pixelle_video()
    
    # Sidebar: Statistics + Filters
    filter_status, sort_by, sort_order, page_size = render_sidebar_controls(pixelle_video)
    
    # Initialize pagination in session state
    if "history_page" not in st.session_state:
        st.session_state.history_page = 1
    
    # Check if we need to show a detail view
    show_detail_for = None
    for key in st.session_state.keys():
        if key.startswith("detail_") and st.session_state[key]:
            show_detail_for = key.replace("detail_", "")
            break
    
    # If showing detail, render it
    if show_detail_for:
        render_task_detail_modal(show_detail_for, pixelle_video)
        return
    
    # Otherwise, show the grid list
    # Get task list
    result = run_async(pixelle_video.history.get_task_list(
        page=st.session_state.history_page,
        page_size=page_size,
        status=filter_status,
        sort_by=sort_by,
        sort_order=sort_order
    ))
    
    tasks = result["tasks"]
    total = result["total"]
    total_pages = result["total_pages"]
    
    # Page title with count
    st.markdown(f"##### 📚 {tr('history.page_title')} ({total})")
    
    # Show task cards in grid layout (4 columns)
    if not tasks:
        st.info(tr("history.no_tasks"))
    else:
        # Grid layout: 4 cards per row
        CARDS_PER_ROW = 4
        
        # Process tasks in batches of CARDS_PER_ROW
        for i in range(0, len(tasks), CARDS_PER_ROW):
            cols = st.columns(CARDS_PER_ROW)
            
            # Fill each column with a task card
            for j in range(CARDS_PER_ROW):
                task_idx = i + j
                if task_idx < len(tasks):
                    with cols[j]:
                        render_grid_task_card(tasks[task_idx], pixelle_video)
    
    # Pagination
    if total_pages > 1:
        st.divider()
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if st.button("⬅️ Previous", disabled=st.session_state.history_page == 1, width="stretch"):
                st.session_state.history_page -= 1
                st.rerun()
        
        with col2:
            st.markdown(
                f"<div style='text-align: center; padding-top: 8px;'>"
                f"{tr('history.page_info').format(page=st.session_state.history_page, total_pages=total_pages)}"
                f"</div>",
                unsafe_allow_html=True
            )
        
        with col3:
            if st.button("Next ➡️", disabled=st.session_state.history_page == total_pages, width="stretch"):
                st.session_state.history_page += 1
                st.rerun()


if __name__ == "__main__":
    main()
