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
Output preview components for web UI (right column)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from urllib.request import url2pathname

import streamlit as st
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.tts_defaults import resolve_tts_inference_mode
from pixelle_video.models.layered_template import LayeredTemplateSpec
from pixelle_video.models.media_placement import MediaPlacement, resolve_media_placement
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.render_package import resolve_media_layout_mode
from pixelle_video.models.size_contract import GenerationSizeContract
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.models.video_generation_contract import (
    STORYBOARD_GENERATION_OPTION_KEYS as CONTRACT_STORYBOARD_GENERATION_OPTION_KEYS,
)
from pixelle_video.models.video_generation_contract import (
    IPControlsContract,
    StoryboardControlsContract,
    is_plan_frame_override_payload,
)
from pixelle_video.platform_context import resolve_business_context
from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from pixelle_video.repositories.template_presets import TemplatePresetRepository
from pixelle_video.services.frame_html import HTMLFrameGenerator
from pixelle_video.services.layered_template_service import (
    LayeredTemplatePreviewFrameRequest,
    LayeredTemplateService,
)
from pixelle_video.services.template_registry import TemplateRegistry
from pixelle_video.storage.artifact_object_store import FilesystemDevArtifactObjectStore
from pixelle_video.tts_workflow_contract import tts_workflow_requires_ref_audio
from pixelle_video.utils.logging_util import build_content_observability, new_correlation_id
from pixelle_video.utils.template_util import get_template_preview_path, resolve_template_path
from web.components.layered_template_state import load_layered_template_spec_into_editor_state
from web.components.layout_preview_workbench import (
    DefaultLayoutSummary,
    TrustedPreviewHTML,
    render_layout_preview_workbench,
    trust_preview_html,
)
from web.components.prompt_generation_performance import (
    copy_prompt_generation_performance_params,
)
from web.components.recent_video_gallery import (
    render_recent_video_gallery,
    store_recent_generated_video,
)
from web.i18n import tr
from web.state.storyboard_preview import set_storyboard_preview_snapshot
from web.utils.async_helpers import run_async
from web.utils.progress_i18n import format_progress_event_message, localize_progress_extra_info
from web.utils.render_backend_ui import copy_render_backend
from web.utils.streamlit_helpers import RefreshableSlot, safe_rerun
from web.utils.tts_audio_strategy_ui import copy_tts_audio_strategy
from web.utils.tts_split_mode_ui import TTS_SPLIT_SETTING_KEYS, copy_tts_split_settings

VIDEO_PREVIEW_CONTAINER_KEY = "output_video_preview"
VIDEO_PREVIEW_WIDTH = "50%"


def _resolve_video_tts_mode(video_params):
    return resolve_tts_inference_mode(None, video_params.get("tts_inference_mode"))


def _validate_tts_reference_audio_contract(
    *,
    tts_inference_mode: str,
    tts_workflow: str | None,
    ref_audio: str | None,
) -> None:
    if tts_inference_mode != "comfyui":
        return
    if not tts_workflow_requires_ref_audio(tts_workflow):
        return
    if str(ref_audio or "").strip():
        return
    raise ValueError(
        f"TTS workflow '{tts_workflow}' requires a reference audio. "
        "Select a saved voice or upload and save a reference voice before generation."
    )


def _media_placement_payload(*sources) -> dict:
    for source in sources:
        if source is not None:
            return resolve_media_placement(source).to_dict()
    return MediaPlacement().to_dict()


ELEMENT_ANIMATION_OPTION_KEYS = (
    "element_animation_enabled",
    "element_animation_backend",
    "element_animation_subject_count",
    "element_animation_candidate_limit",
    "element_animation_prompt",
    "element_animation_intensity",
    "element_animation_workflow",
)
STORYBOARD_GENERATION_OPTION_KEYS = (
    *CONTRACT_STORYBOARD_GENERATION_OPTION_KEYS,
    "script_length_mode",
    "script_target_words",
)
SINGLE_VIDEO_GENERATING_KEY = "single_video_is_generating"
SINGLE_VIDEO_REQUESTED_KEY = "single_video_generation_requested"
SINGLE_VIDEO_DUPLICATE_CLICK_KEY = "single_video_duplicate_click"
SINGLE_VIDEO_BUTTON_KEY = "single_video_generate_button"
SINGLE_VIDEO_RESULT_SUMMARY_KEY = "single_video_result_summary"
LAYOUT_PREVIEW_REAL_PREVIEW_FRAME_KEY = "layout_preview_real_preview_frame"


def _plan_identity_frame_overrides(video_params):
    return [
        dict(override)
        for override in video_params.get("frame_overrides") or []
        if isinstance(override, dict) and is_plan_frame_override_payload(override)
    ]


def _storyboard_controls_contract(
    source,
    *,
    default_prompt_language: str = CHINESE_PROMPT_LANGUAGE,
):
    contract_source = dict(source)
    plan_frame_overrides = _plan_identity_frame_overrides(source)
    if plan_frame_overrides:
        contract_source["frame_overrides"] = plan_frame_overrides
    else:
        contract_source.pop("frame_overrides", None)
    return StoryboardControlsContract.from_mapping(
        contract_source,
        default_prompt_language=default_prompt_language,
    )


def _get_or_create_log_session_id(session_state) -> str:
    session_id = session_state.get("log_session_id")
    if not session_id:
        session_id = new_correlation_id("sess")
        session_state["log_session_id"] = session_id
    return session_id


def _request_single_video_generation() -> None:
    """Mark a single-video generation request unless one is already running."""
    if st.session_state.get(SINGLE_VIDEO_GENERATING_KEY):
        st.session_state[SINGLE_VIDEO_DUPLICATE_CLICK_KEY] = True
        return

    st.session_state[SINGLE_VIDEO_GENERATING_KEY] = True
    st.session_state[SINGLE_VIDEO_REQUESTED_KEY] = True


def _reset_single_video_generation_state() -> None:
    st.session_state[SINGLE_VIDEO_GENERATING_KEY] = False
    st.session_state[SINGLE_VIDEO_REQUESTED_KEY] = False


def _clear_single_video_result_summary(session_state) -> None:
    session_state.pop(SINGLE_VIDEO_RESULT_SUMMARY_KEY, None)


def _get_single_video_result_summary(session_state):
    summary = session_state.get(SINGLE_VIDEO_RESULT_SUMMARY_KEY)
    if not summary:
        return None

    video_path = summary.get("video_path")
    if not video_path or not os.path.exists(video_path):
        _clear_single_video_result_summary(session_state)
        return None

    return summary


def _build_single_video_result_summary(result, *, total_generation_time: float):
    from pixelle_video.utils.template_util import (
        parse_template_size,
        resolve_template_path,
    )

    config = result.storyboard.config
    video_width = getattr(config, "canvas_width", None)
    video_height = getattr(config, "canvas_height", None)
    if video_width is None or video_height is None:
        template_path = resolve_template_path(config.frame_template)
        video_width, video_height = parse_template_size(template_path)
    return {
        "video_path": str(result.video_path),
        "generation_time_sec": float(total_generation_time),
        "file_size_mb": float(result.file_size) / (1024 * 1024),
        "frame_count": len(result.storyboard.frames),
        "video_width": int(video_width),
        "video_height": int(video_height),
    }


def _render_single_video_result_summary(summary) -> None:
    st.success(tr("status.video_generated", path=summary["video_path"]))
    st.markdown("---")
    info_text = (
        f"{tr('info.generation_time')} {summary['generation_time_sec']:.1f}s   "
        f"{tr('info.file_size')} {summary['file_size_mb']:.2f}MB   "
        f"{tr('info.frames')} {summary['frame_count']}{tr('info.scenes_unit')}   "
        f"{tr('info.resolution')} {summary['video_width']}x{summary['video_height']}"
    )
    st.caption(info_text)


def build_video_preview_css(
    container_key: str = VIDEO_PREVIEW_CONTAINER_KEY,
    *,
    width: str = VIDEO_PREVIEW_WIDTH,
) -> str:
    """Build scoped CSS that shrinks the generated video preview inside one container."""
    return f"""
    <style>
    .st-key-{container_key} [data-testid="stVideo"] {{
        width: {width} !important;
        max-width: 100% !important;
        display: block;
        margin-inline: auto;
        height: auto;
    }}
    </style>
    """


def render_scaled_video_preview(video_path: str) -> None:
    """Render the generated video preview at a smaller, centered size."""
    st.markdown(build_video_preview_css(), unsafe_allow_html=True)
    with st.container(key=VIDEO_PREVIEW_CONTAINER_KEY):
        st.video(video_path, width="stretch")


def _build_layout_preview_html(video_params) -> TrustedPreviewHTML | None:
    spec_payload = video_params.get("layered_template_spec")
    if spec_payload:
        try:
            spec = (
                spec_payload
                if isinstance(spec_payload, LayeredTemplateSpec)
                else LayeredTemplateSpec.from_dict(spec_payload)
            )
            html = LayeredTemplateService().render_preview_html(
                spec=spec,
                title_text=video_params.get("title") or video_params.get("layout_preview_title_text") or "",
                caption_text=video_params.get("layout_preview_caption_text") or "",
                text_rendering=video_params.get("text_rendering") or {},
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(f"Failed to build layered template preview HTML: {exc}")
            return None
        return trust_preview_html(
            html,
            width=spec.canvas_width,
            height=spec.canvas_height,
        )
    return _build_frame_template_preview_html(video_params)


def _layout_preview_text(video_params, *keys: str, default: str = "") -> str:
    for key in keys:
        value = video_params.get(key)
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate:
            return candidate
    return default


def _layout_preview_title(video_params) -> str:
    explicit_title = _layout_preview_text(
        video_params,
        "title",
        "layout_preview_title_text",
    )
    if explicit_title:
        return explicit_title
    return _preview_text_excerpt(
        _layout_preview_text(video_params, "text"),
        max_chars=28,
        default="模板预览",
    )


def _layout_preview_caption(video_params) -> str:
    return _preview_text_excerpt(
        _layout_preview_text(
            video_params,
            "layout_preview_caption_text",
            "text",
        ),
        max_chars=90,
        default="当前模板即时预览",
    )


def _preview_text_excerpt(value: str, *, max_chars: int, default: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        return default
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max(1, max_chars - 1)].rstrip()}…"


def _layout_preview_media_layout_mode(video_params) -> str:
    return resolve_media_layout_mode(
        video_params.get("media_layout_mode"),
        sync_media_size_to_canvas=bool(video_params.get("sync_media_size_to_canvas")),
    )


def _local_media_uri(value: object) -> str | None:
    if value is None:
        return None
    source = str(value).strip()
    if not source:
        return None
    if source.startswith(("http://", "https://", "data:", "file://")):
        return source
    path = Path(source)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return None
    return path.resolve().as_uri()


def _iter_layout_preview_media_candidates(video_params):
    for key in (
        "layout_preview_media_path",
        "layout_preview_image_path",
        "preview_media_ref",
        "preview_media_path",
        "image_path",
        "media_path",
        "composed_image_path",
    ):
        yield video_params.get(key)

    template_params = video_params.get("template_params")
    if isinstance(template_params, dict):
        for key in ("image", "media", "media_path", "image_path"):
            yield template_params.get(key)

    for key in ("assets", "image_assets", "character_assets", "goods_assets"):
        value = video_params.get(key)
        if isinstance(value, (list, tuple)):
            yield from value


def _resolve_layout_preview_media_source(
    video_params,
    *,
    frame_template: str,
) -> str:
    for candidate in _iter_layout_preview_media_candidates(video_params):
        uri = _local_media_uri(candidate)
        if uri:
            return uri

    default_media = _local_media_uri(Path("resources") / "example.png")
    if default_media:
        return default_media

    template_preview = get_template_preview_path(frame_template)
    template_uri = _local_media_uri(template_preview)
    if template_uri:
        return template_uri

    return _build_layout_preview_media_placeholder()


def _build_layout_preview_media_placeholder() -> str:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="768" height="768" viewBox="0 0 768 768">
      <rect width="768" height="768" fill="#f6f1e8"/>
      <rect x="48" y="48" width="672" height="672" rx="28" fill="none" stroke="#b98242" stroke-width="8" stroke-dasharray="24 18" opacity=".55"/>
      <path d="M188 508 308 388l78 78 86-118 120 160" fill="none" stroke="#8b785e" stroke-width="20" stroke-linecap="round" stroke-linejoin="round" opacity=".7"/>
      <circle cx="286" cy="268" r="46" fill="#b98242" opacity=".35"/>
      <text x="384" y="640" text-anchor="middle" font-family="Arial, sans-serif" font-size="34" font-weight="700" fill="#6a5a43">Media Preview</text>
    </svg>
    """
    return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"


def _build_frame_template_preview_html(video_params) -> TrustedPreviewHTML | None:
    frame_template = video_params.get("frame_template")
    if not frame_template:
        return None
    try:
        size_contract = GenerationSizeContract.from_params(video_params)
        generator = HTMLFrameGenerator(
            resolve_template_path(str(frame_template)),
            canvas_width=size_contract.canvas_width,
            canvas_height=size_contract.canvas_height,
        )
        html = generator._build_render_html(
            title=_layout_preview_title(video_params),
            text=_layout_preview_caption(video_params),
            image=_resolve_layout_preview_media_source(
                video_params,
                frame_template=str(frame_template),
            ),
            ext={
                "index": 1,
                "media_layout_mode": _layout_preview_media_layout_mode(video_params),
            },
            media_placement=_media_placement_payload(
                video_params.get("media_placement"),
                st.session_state.get("media_placement"),
            ),
            media_type="image",
            media_width=size_contract.media_width,
            media_height=size_contract.media_height,
        )
        return trust_preview_html(
            generator._prepare_html_for_render(html),
            width=generator.template_width,
            height=generator.template_height,
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        logger.warning(f"Failed to build frame template preview HTML: {exc}")
        return None


def _list_layout_preview_recent_presets(video_params):
    explicit_presets = video_params.get("layout_preview_recent_presets")
    if explicit_presets is not None:
        return explicit_presets
    try:
        return TemplateRegistry().list_recent(limit=5)
    except (OSError, ValueError) as exc:
        logger.warning(f"Failed to load recent layered template presets: {exc}")
        return []


def _mark_layout_preview_preset_used(preset_id: str | None) -> None:
    if not preset_id:
        return
    try:
        TemplateRegistry().mark_used(str(preset_id))
    except KeyError:
        logger.warning(f"Selected layered template preset no longer exists: {preset_id}")
    except (OSError, ValueError) as exc:
        logger.warning(f"Failed to mark layered template preset as used: {exc}")


def _coerce_layered_template_spec(spec_payload) -> LayeredTemplateSpec | None:
    if not spec_payload:
        return None
    try:
        return (
            spec_payload
            if isinstance(spec_payload, LayeredTemplateSpec)
            else LayeredTemplateSpec.from_dict(spec_payload)
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(f"Invalid layered template spec for workbench action: {exc}")
        return None


def _generation_layered_template_spec_payload(spec_payload) -> dict | None:
    if spec_payload is None:
        return None
    spec = (
        spec_payload
        if isinstance(spec_payload, LayeredTemplateSpec)
        else LayeredTemplateSpec.from_dict(spec_payload)
    )
    if not spec.layers:
        return None
    return spec.to_dict()


def _layout_preview_summary_text(video_params, *keys: str) -> str | None:
    for key in keys:
        value = video_params.get(key)
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate:
            return candidate
    return None


def _build_layout_preview_default_summary(video_params) -> DefaultLayoutSummary:
    size_contract = GenerationSizeContract.from_params(video_params)
    return DefaultLayoutSummary(
        canvas_width=size_contract.canvas_width,
        canvas_height=size_contract.canvas_height,
        media_width=size_contract.media_width,
        media_height=size_contract.media_height,
        media_placement=resolve_media_placement(
            _media_placement_payload(
                video_params.get("media_placement"),
                st.session_state.get("media_placement"),
            )
        ),
        render_summary=_layout_preview_summary_text(
            video_params,
            "layout_preview_render_summary",
            "render_backend",
        ),
        template_summary=_layout_preview_summary_text(
            video_params,
            "layout_preview_template_summary",
            "selected_template_preset_id",
            "frame_template",
        ),
    )


def _build_layout_preview_frame_request(
    video_params,
    *,
    spec: LayeredTemplateSpec,
) -> LayeredTemplatePreviewFrameRequest:
    business_context = resolve_business_context(video_params, st.session_state)
    return LayeredTemplatePreviewFrameRequest(
        workspace_id=business_context["workspace_id"],
        spec=spec,
        title_text=video_params.get("title")
        or video_params.get("layout_preview_title_text")
        or "",
        caption_text=video_params.get("layout_preview_caption_text") or "",
        text_rendering=video_params.get("text_rendering") or {},
    )


def _refresh_layout_preview_frame(video_params, *, spec: LayeredTemplateSpec) -> dict[str, str]:
    request = _build_layout_preview_frame_request(video_params, spec=spec)
    object_store = _resolve_layout_preview_object_store(video_params)
    service = (
        LayeredTemplateService(object_store=object_store)
        if object_store is not None
        else LayeredTemplateService()
    )
    result = run_async(service.render_preview_frame(request))
    frame_payload = {
        "storage_key": result.storage_key,
        "url": result.url,
        "fingerprint": result.fingerprint,
    }
    st.session_state[LAYOUT_PREVIEW_REAL_PREVIEW_FRAME_KEY] = frame_payload
    return frame_payload


def _resolve_layout_preview_object_store(video_params):
    configured_store = video_params.get("artifact_object_store") or getattr(
        video_params.get("pixelle_video"),
        "artifact_object_store",
        None,
    )
    if configured_store is not None:
        return configured_store
    return FilesystemDevArtifactObjectStore(
        root=video_params.get("artifact_base_path", "output"),
        base_url=video_params.get("artifact_base_url", "/api/files"),
    )


def _resolve_layout_preview_thumbnail_source_path(video_params, *, storage_key: str) -> Path:
    object_store = _resolve_layout_preview_object_store(video_params)
    if object_store is None:
        raise RuntimeError("artifact object store is not configured for layered template save")
    get_local_file_uri = getattr(object_store, "get_local_file_uri", None)
    if get_local_file_uri is None:
        raise RuntimeError("artifact object store does not support local preview file access")
    local_uri = run_async(get_local_file_uri(storage_key))
    parsed = urlparse(str(local_uri))
    if parsed.scheme != "file":
        raise RuntimeError("preview thumbnail must resolve to a local file URI before saving")
    thumbnail_path = Path(url2pathname(unquote(parsed.path)))
    if not thumbnail_path.is_file():
        raise FileNotFoundError(f"preview thumbnail file not found: {thumbnail_path}")
    return thumbnail_path


def _validate_layout_preview_persistable_spec(spec: LayeredTemplateSpec) -> None:
    for layer in spec.layers:
        if layer.source is None:
            continue
        if layer.source.kind == "asset":
            ref = str(layer.source.ref)
            if not ref.startswith("assets/"):
                raise ValueError("asset layers must reference repository asset keys before saving")
            continue
        if layer.source.kind == "generated_media":
            ref = str(layer.source.ref)
            if ref != "generated://primary":
                raise ValueError("generated media layers must use the primary generated-media ref")


def _build_user_template_spec(spec: LayeredTemplateSpec) -> LayeredTemplateSpec:
    metadata = dict(spec.metadata)
    metadata["source_kind"] = "user"
    metadata["source_template_id"] = spec.template_id
    template_name = str(spec.template_name).strip() or "Layer Design"
    slug = "".join(
        char.lower() if char.isalnum() else "_"
        for char in template_name
    ).strip("_") or "layer_design"
    if slug.startswith("system_"):
        slug = slug.removeprefix("system_") or "layer_design"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    preset_id = spec.template_id
    if not str(preset_id).startswith("user:"):
        preset_id = f"user:{slug}_{timestamp}"
    return LayeredTemplateSpec(
        version=spec.version,
        template_id=preset_id,
        template_name=template_name,
        template_type=spec.template_type,
        canvas_width=spec.canvas_width,
        canvas_height=spec.canvas_height,
        media_width=spec.media_width,
        media_height=spec.media_height,
        safe_area=spec.safe_area,
        layers=spec.layers,
        metadata=metadata,
    )


def _build_user_template_preset(spec: LayeredTemplateSpec, *, thumbnail_ref: str) -> TemplatePreset:
    timestamp = datetime.now(timezone.utc).isoformat()
    orientation = str(spec.metadata.get("orientation") or "")
    if not orientation:
        if spec.canvas_width > spec.canvas_height:
            orientation = "landscape"
        elif spec.canvas_width < spec.canvas_height:
            orientation = "portrait"
        else:
            orientation = "square"
    return TemplatePreset(
        preset_id=spec.template_id,
        name=spec.template_name,
        source="user",
        orientation=orientation,
        template_type=spec.template_type,
        spec=spec,
        thumbnail_ref=thumbnail_ref,
        editable=True,
        created_at=timestamp,
        updated_at=timestamp,
        last_used_at=timestamp,
    )


def save_layered_template_design(video_params, *, spec: LayeredTemplateSpec) -> TemplatePreset:
    save_spec = _build_user_template_spec(spec)
    _validate_layout_preview_persistable_spec(save_spec)
    frame_payload = _refresh_layout_preview_frame(video_params, spec=save_spec)
    repository = TemplatePresetRepository(
        root=video_params.get("template_presets_root", "data/template_presets")
    )
    thumbnail_source = _resolve_layout_preview_thumbnail_source_path(
        video_params,
        storage_key=frame_payload["storage_key"],
    )
    thumbnail_ref = repository.persist_thumbnail(
        source_path=thumbnail_source,
        preset_id=save_spec.template_id,
    )
    preset = _build_user_template_preset(save_spec, thumbnail_ref=thumbnail_ref)
    repository.save(preset)
    TemplateRegistry().mark_used(preset.preset_id, preset.last_used_at)
    st.session_state["selected_template_preset_id"] = preset.preset_id
    return preset


def _save_layout_preview_template(video_params, *, spec: LayeredTemplateSpec) -> TemplatePreset:
    return save_layered_template_design(video_params, spec=spec)


def _render_layout_preview_workbench_section(video_params, *, key_suffix: str = "") -> None:
    spec_payload = video_params.get("layered_template_spec")
    selected = render_layout_preview_workbench(
        spec_payload=spec_payload,
        recent_presets=_list_layout_preview_recent_presets(video_params),
        preview_html=_build_layout_preview_html(video_params),
        default_layout_summary=_build_layout_preview_default_summary(video_params),
        render_summary=video_params.get("layout_preview_render_summary")
        or video_params.get("render_backend"),
        template_summary=video_params.get("layout_preview_template_summary")
        or video_params.get("selected_template_preset_id")
        or video_params.get("frame_template"),
        media_placement=video_params.get("media_placement"),
        real_preview_frame=st.session_state.get(LAYOUT_PREVIEW_REAL_PREVIEW_FRAME_KEY),
        key_suffix=key_suffix,
        ui=st,
    )
    action = selected.get("action") if selected else None
    spec = _coerce_layered_template_spec(spec_payload)
    if action == "refresh_preview_frame":
        if spec is None:
            st.error("当前没有可刷新的分层模板规格")
            return
        try:
            _refresh_layout_preview_frame(video_params, spec=spec)
            st.success("已刷新真实预览帧")
        except Exception as exc:
            st.error(str(exc))
        return
    if action == "save_template":
        if spec is None:
            st.error("当前没有可保存的分层模板规格")
            return
        try:
            _save_layout_preview_template(video_params, spec=spec)
            st.success("已保存到我的模板")
        except Exception as exc:
            st.error(str(exc))
        return
    if action == "delete_recent_preset":
        preset_id = selected.get("preset_id") if selected else None
        if not preset_id:
            return
        try:
            deleted = TemplateRegistry().delete_recent(str(preset_id))
            if deleted:
                st.success("已删除最近模板")
            else:
                st.success("最近模板已不存在")
            rerun = getattr(st, "rerun", None)
            if callable(rerun):
                rerun()
        except Exception as exc:
            st.error(str(exc))
        return
    if selected and selected.get("spec_payload"):
        selected_preset_id = selected.get("preset_id")
        load_layered_template_spec_into_editor_state(
            st.session_state,
            selected["spec_payload"],
        )
        st.session_state["selected_template_preset_id"] = selected_preset_id
        _mark_layout_preview_preset_used(selected_preset_id)
        rerun = getattr(st, "rerun", None)
        if callable(rerun):
            rerun()


def copy_element_animation_options(source, target):
    """Copy element animation UI params into a generation request dict."""
    for key in ELEMENT_ANIMATION_OPTION_KEYS:
        if key in source and source[key] is not None:
            target[key] = source[key]


def copy_storyboard_generation_options(source, target):
    """Copy storyboard generation contract params into a generation request dict."""
    storyboard_contract = _storyboard_controls_contract(source)
    target.update(storyboard_contract.to_generation_dict())
    script_length_mode = source.get("script_length_mode")
    target["script_length_mode"] = (
        script_length_mode if script_length_mode not in (None, "") else "auto"
    )
    if source.get("script_target_words") is not None:
        target["script_target_words"] = source["script_target_words"]


def copy_ip_prompt_chain_options(source, target):
    """Copy IP prompt-chain controls into a generation request dict."""
    if "ip_enabled" not in source:
        return
    contract = IPControlsContract.from_mapping(source)
    target.update(contract.to_dict())


def render_output_preview(pixelle_video, video_params):
    """Render output preview section (right column)"""
    # Check if batch mode
    is_batch = video_params.get("batch_mode", False)

    if is_batch:
        # Batch generation mode
        render_batch_output(pixelle_video, video_params)
    else:
        # Single video generation mode (original logic)
        render_single_output(pixelle_video, video_params)


def build_single_generation_request(video_params, *, progress_callback, session_state):
    """Build a single generate_video() request from UI params."""
    storyboard_contract = _storyboard_controls_contract(video_params)
    size_contract = GenerationSizeContract.from_params(video_params)
    business_context = resolve_business_context(session_state, video_params)
    request = {
        "text": video_params.get("text", ""),
        "mode": video_params.get("mode", "generate"),
        "title": video_params.get("title") if video_params.get("title") else None,
        "media_workflow": video_params.get("media_workflow"),
        "frame_template": video_params.get("frame_template"),
        "prompt_prefix": video_params.get("prompt_prefix", ""),
        "bgm_path": video_params.get("bgm_path"),
        "bgm_volume": video_params.get("bgm_volume", 0.2)
        if video_params.get("bgm_path")
        else 0.2,
        "progress_callback": progress_callback,
        **size_contract.to_params(),
        "media_placement": _media_placement_payload(
            video_params.get("media_placement"),
            session_state.get("media_placement"),
        ),
        "tts_inference_mode": _resolve_video_tts_mode(video_params),
        "world_preset_id": storyboard_contract.world_preset_id,
        "shot_preset_id": storyboard_contract.shot_preset_id,
        "consistency_strength": storyboard_contract.consistency_strength or "standard",
        "content_mode": storyboard_contract.content_mode,
        "role_strategy": storyboard_contract.role_strategy,
        "role_locking_strength": storyboard_contract.role_locking_strength,
        "shot_strategy": storyboard_contract.shot_strategy,
        **business_context,
    }
    if storyboard_contract.frame_overrides:
        request["frame_overrides"] = [
            dict(override) for override in storyboard_contract.frame_overrides
        ]

    if request["tts_inference_mode"] == "local":
        request["tts_voice"] = video_params.get("tts_voice")
    else:
        request["tts_workflow"] = video_params.get("tts_workflow")
        ref_audio_path = video_params.get("ref_audio")
        _validate_tts_reference_audio_contract(
            tts_inference_mode=request["tts_inference_mode"],
            tts_workflow=request.get("tts_workflow"),
            ref_audio=str(ref_audio_path) if ref_audio_path else None,
        )
        if ref_audio_path:
            request["ref_audio"] = str(ref_audio_path)
        ref_audio_text = video_params.get("ref_audio_text")
        if ref_audio_text:
            request["ref_audio_text"] = ref_audio_text

    tts_speed = video_params.get("tts_speed")
    if tts_speed is not None:
        request["tts_speed"] = tts_speed

    template_params = video_params.get("template_params", {})
    if template_params:
        request["template_params"] = template_params
    copy_render_backend(video_params, request)
    copy_tts_audio_strategy(video_params, request)
    copy_tts_split_settings(video_params, request)
    copy_storyboard_generation_options(video_params, request)
    copy_element_animation_options(video_params, request)
    copy_ip_prompt_chain_options(video_params, request)
    copy_prompt_generation_performance_params(video_params, request)
    if video_params.get("text_rendering") is not None:
        request["text_rendering"] = video_params["text_rendering"]
    layered_template_spec = _generation_layered_template_spec_payload(
        video_params.get("layered_template_spec")
    )
    if layered_template_spec is not None:
        request["layered_template_spec"] = layered_template_spec
    if video_params.get("selected_template_preset_id") and layered_template_spec is not None:
        request["selected_template_preset_id"] = video_params[
            "selected_template_preset_id"
        ]

    if video_params.get("request_id"):
        request["request_id"] = video_params["request_id"]
    if video_params.get("session_id"):
        request["session_id"] = video_params["session_id"]
    return request


def build_batch_shared_config(video_params):
    """Build batch shared_config from Web UI params."""
    storyboard_contract = _storyboard_controls_contract(video_params)
    size_contract = GenerationSizeContract.from_params(video_params)
    business_context = resolve_business_context(video_params)
    shared_config = {
        "title_prefix": video_params.get("title_prefix"),
        "media_workflow": video_params.get("media_workflow"),
        "frame_template": video_params.get("frame_template"),
        "prompt_prefix": video_params.get("prompt_prefix") or "",
        "bgm_path": video_params.get("bgm_path"),
        "bgm_volume": video_params.get("bgm_volume") or 0.2,
        "tts_inference_mode": _resolve_video_tts_mode(video_params),
        **size_contract.to_params(),
        "media_placement": _media_placement_payload(video_params.get("media_placement")),
        "world_preset_id": storyboard_contract.world_preset_id,
        "shot_preset_id": storyboard_contract.shot_preset_id,
        "consistency_strength": storyboard_contract.consistency_strength or "standard",
        "content_mode": storyboard_contract.content_mode,
        "role_strategy": storyboard_contract.role_strategy,
        "role_locking_strength": storyboard_contract.role_locking_strength,
        "shot_strategy": storyboard_contract.shot_strategy,
        **business_context,
    }
    if storyboard_contract.frame_overrides:
        shared_config["frame_overrides"] = [
            dict(override) for override in storyboard_contract.frame_overrides
        ]

    tts_speed = video_params.get("tts_speed")
    if tts_speed is not None:
        shared_config["tts_speed"] = tts_speed

    if shared_config["tts_inference_mode"] == "local":
        tts_voice = video_params.get("tts_voice")
        if tts_voice:
            shared_config["tts_voice"] = tts_voice
    else:
        tts_workflow = video_params.get("tts_workflow")
        if tts_workflow:
            shared_config["tts_workflow"] = tts_workflow
        ref_audio = video_params.get("ref_audio")
        _validate_tts_reference_audio_contract(
            tts_inference_mode=shared_config["tts_inference_mode"],
            tts_workflow=shared_config.get("tts_workflow"),
            ref_audio=str(ref_audio) if ref_audio else None,
        )
        if ref_audio:
            shared_config["ref_audio"] = str(ref_audio)
        ref_audio_text = video_params.get("ref_audio_text")
        if ref_audio_text:
            shared_config["ref_audio_text"] = ref_audio_text

    if video_params.get("template_params"):
        shared_config["template_params"] = video_params["template_params"]
    if video_params.get("session_id"):
        shared_config["session_id"] = video_params["session_id"]

    copy_render_backend(video_params, shared_config)
    copy_tts_audio_strategy(video_params, shared_config)
    copy_tts_split_settings(video_params, shared_config)
    copy_storyboard_generation_options(video_params, shared_config)
    copy_element_animation_options(video_params, shared_config)
    copy_ip_prompt_chain_options(video_params, shared_config)
    copy_prompt_generation_performance_params(video_params, shared_config)
    if video_params.get("text_rendering") is not None:
        shared_config["text_rendering"] = video_params["text_rendering"]
    layered_template_spec = _generation_layered_template_spec_payload(
        video_params.get("layered_template_spec")
    )
    if layered_template_spec is not None:
        shared_config["layered_template_spec"] = layered_template_spec
    if video_params.get("selected_template_preset_id") and layered_template_spec is not None:
        shared_config["selected_template_preset_id"] = video_params[
            "selected_template_preset_id"
        ]
    return shared_config


def render_single_output(pixelle_video, video_params):
    """Render single video generation output sections."""
    _render_single_output_sections(pixelle_video, video_params)


def _render_single_output_sections(pixelle_video, video_params):
    generation_runner = _render_generation_section(pixelle_video, video_params)
    if generation_runner is None:
        _render_layout_preview_workbench_section(
            {**video_params, "pixelle_video": pixelle_video}
        )
        render_recent_video_gallery(pixelle_video)
        return

    gallery_slot = RefreshableSlot(st.empty())

    def render_gallery(*, refresh: bool = False) -> None:
        def render_gallery_section(key_suffix: str) -> None:
            _render_layout_preview_workbench_section(
                {**video_params, "pixelle_video": pixelle_video},
                key_suffix=key_suffix,
            )
            render_recent_video_gallery(
                pixelle_video,
                key_suffix=key_suffix,
            )

        gallery_slot.render(
            render_gallery_section,
            refresh=refresh,
        )

    render_gallery()
    generation_runner(render_gallery=render_gallery)


def _render_generation_section(pixelle_video, video_params):
    """Render single video generation output with a recent-video gallery."""
    # Extract parameters from video_params dict
    text = video_params.get("text", "")
    mode = video_params.get("mode", "generate")
    title = video_params.get("title")
    bgm_path = video_params.get("bgm_path")
    bgm_volume = video_params.get("bgm_volume", 0.2)

    tts_mode = _resolve_video_tts_mode(video_params)
    selected_voice = video_params.get("tts_voice")
    tts_speed = video_params.get("tts_speed")
    tts_workflow_key = video_params.get("tts_workflow")
    ref_audio_path = video_params.get("ref_audio")
    ref_audio_text = video_params.get("ref_audio_text")

    frame_template = video_params.get("frame_template")
    custom_values_for_video = video_params.get("template_params", {})
    workflow_key = video_params.get("media_workflow")
    prompt_prefix = video_params.get("prompt_prefix", "")

    with st.container(border=True):
        st.markdown(f"**{tr('section.video_generation')}**")

        # Check if system is configured
        if not config_manager.validate():
            st.warning(tr("settings.not_configured"))

        # Generate Button
        button_slot = RefreshableSlot(st.empty())
        was_generating = bool(st.session_state.get(SINGLE_VIDEO_GENERATING_KEY, False))

        def render_generate_button(*, disabled: bool, refresh: bool = False) -> bool:
            def render_button(key_suffix: str) -> bool:
                return st.button(
                    tr("btn.generate"),
                    key=f"{SINGLE_VIDEO_BUTTON_KEY}{key_suffix}",
                    type="primary",
                    width="stretch",
                    disabled=disabled,
                    on_click=_request_single_video_generation,
                )

            return button_slot.render(render_button, refresh=refresh)

        button_clicked = render_generate_button(disabled=was_generating)
        generation_requested = bool(st.session_state.pop(SINGLE_VIDEO_REQUESTED_KEY, False))
        st.session_state[SINGLE_VIDEO_REQUESTED_KEY] = False
        if button_clicked and not generation_requested:
            if was_generating:
                st.session_state[SINGLE_VIDEO_DUPLICATE_CLICK_KEY] = True
            else:
                st.session_state[SINGLE_VIDEO_GENERATING_KEY] = True
                generation_requested = True

        if (
            st.session_state.pop(SINGLE_VIDEO_DUPLICATE_CLICK_KEY, False)
            and not generation_requested
        ):
            st.info(tr("status.generation_in_progress"))

        result_summary_slot = None
        result_summary_rendered = False

        def render_result_summary(*, refresh: bool = False) -> None:
            nonlocal result_summary_rendered

            summary = _get_single_video_result_summary(st.session_state)
            if summary:
                if result_summary_slot is None:
                    _render_single_video_result_summary(summary)
                else:
                    result_summary_slot.render(
                        lambda _key_suffix: _render_single_video_result_summary(summary),
                        refresh=refresh,
                    )
                result_summary_rendered = True

        if generation_requested:
            can_generate = True
            # Validate system configuration
            if not config_manager.validate():
                st.error(tr("settings.not_configured"))
                can_generate = False

            # Validate input
            if not text:
                st.error(tr("error.input_required"))
                can_generate = False

            if can_generate:
                _clear_single_video_result_summary(st.session_state)

                # Show progress
                progress_bar = st.progress(0)
                status_text = st.empty()
                result_summary_slot = RefreshableSlot(st.empty())

                def run_generation(*, render_gallery) -> None:
                    # Record start time for generation
                    import time

                    start_time = time.time()
                    rerun_after_generation = False

                    try:
                        request_id = new_correlation_id("req")
                        session_id = _get_or_create_log_session_id(st.session_state)
                        logger.bind(
                            channel="runtime",
                            request_id=request_id,
                            session_id=session_id,
                            content=build_content_observability(text),
                        ).info("web single generation request received")

                        # Progress callback to update UI
                        def update_progress(event: ProgressEvent):
                            """Update progress bar and status text from ProgressEvent"""
                            message = format_progress_event_message(event)

                            # Append extra_info if available (e.g., batch progress)
                            if event.extra_info:
                                localized_extra_info = localize_progress_extra_info(
                                    event.extra_info
                                )
                                if localized_extra_info:
                                    message = f"{message} - {localized_extra_info}"

                            status_text.text(message)
                            progress_bar.progress(
                                min(int(event.progress * 100), 99)
                            )

                        storyboard_contract = _storyboard_controls_contract(video_params)
                        generation_request = build_single_generation_request(
                            {
                                **video_params,
                                "text": text,
                                "mode": mode,
                                "title": title,
                                **storyboard_contract.to_generation_dict(),
                                "script_length_mode": video_params.get(
                                    "script_length_mode"
                                ),
                                "script_target_words": video_params.get(
                                    "script_target_words"
                                ),
                                "media_workflow": workflow_key,
                                "frame_template": frame_template,
                                "prompt_prefix": prompt_prefix,
                                "bgm_path": bgm_path,
                                "bgm_volume": bgm_volume,
                                "tts_inference_mode": tts_mode,
                                "tts_voice": selected_voice,
                                "tts_speed": tts_speed,
                                "tts_workflow": tts_workflow_key,
                                "ref_audio": ref_audio_path,
                                "ref_audio_text": ref_audio_text,
                                "template_params": custom_values_for_video,
                                "request_id": request_id,
                                "session_id": session_id,
                                "render_backend": video_params.get("render_backend"),
                                "tts_audio_strategy": video_params.get(
                                    "tts_audio_strategy"
                                ),
                                "layered_template_spec": video_params.get(
                                    "layered_template_spec"
                                ),
                                "selected_template_preset_id": video_params.get(
                                    "selected_template_preset_id"
                                ),
                                "ip_enabled": video_params.get("ip_enabled"),
                                "ip_asset_bible_id": video_params.get(
                                    "ip_asset_bible_id"
                                ),
                                "ip_profile_id": video_params.get("ip_profile_id"),
                                **storyboard_contract.to_planning_dict(),
                                "text_rendering": video_params.get("text_rendering"),
                                **{
                                    key: video_params.get(key)
                                    for key in TTS_SPLIT_SETTING_KEYS
                                },
                                **{
                                    key: video_params.get(key)
                                    for key in ELEMENT_ANIMATION_OPTION_KEYS
                                },
                            },
                            progress_callback=update_progress,
                            session_state=st.session_state,
                        )

                        result = run_async(pixelle_video.generate_video(**generation_request))
                        storyboard_snapshot_changed = set_storyboard_preview_snapshot(
                            st.session_state,
                            getattr(result.storyboard, "planning_snapshot", None),
                        )

                        # Calculate total generation time
                        total_generation_time = time.time() - start_time

                        progress_bar.progress(100)
                        status_text.text(tr("status.success"))

                        if os.path.exists(result.video_path):
                            st.session_state[SINGLE_VIDEO_RESULT_SUMMARY_KEY] = (
                                _build_single_video_result_summary(
                                    result,
                                    total_generation_time=total_generation_time,
                                )
                            )
                            render_result_summary(refresh=True)
                            store_recent_generated_video(result, st.session_state)
                            render_gallery(refresh=True)
                            rerun_after_generation = storyboard_snapshot_changed
                        else:
                            _clear_single_video_result_summary(st.session_state)
                            st.error(tr("status.video_not_found", path=result.video_path))

                    except Exception as e:
                        status_text.text("")
                        progress_bar.empty()
                        st.error(tr("status.error", error=str(e)))
                        logger.exception(e)
                    finally:
                        _reset_single_video_generation_state()
                        render_generate_button(disabled=False, refresh=True)
                        if rerun_after_generation:
                            safe_rerun()

                return run_generation
            else:
                _reset_single_video_generation_state()
                render_generate_button(disabled=False, refresh=True)

        # Idle reruns render stored results directly; active generations reserve a slot above the gallery.
        if not result_summary_rendered and result_summary_slot is None:
            render_result_summary()


def render_batch_output(pixelle_video, video_params):
    """Render batch generation output (minimal, redirect to History)"""
    topics = video_params.get("topics", [])

    with st.container(border=True):
        st.markdown(f"**{tr('batch.section_generation')}**")

        # Check if topics are provided
        if not topics:
            st.warning(tr("batch.no_topics"))
            return

        # Check system configuration
        if not config_manager.validate():
            st.warning(tr("settings.not_configured"))
            return

        batch_count = len(topics)

        # Display batch info
        st.info(tr("batch.prepare_info", count=batch_count))

        # Estimated time (optional)
        estimated_minutes = batch_count * 3  # Assume 3 minutes per video
        st.caption(tr("batch.estimated_time", minutes=estimated_minutes))

        # Generate button with batch semantics
        if st.button(
            tr("batch.generate_button", count=batch_count),
            type="primary",
            width="stretch",
            help=tr("batch.generate_help")
        ):
            session_id = _get_or_create_log_session_id(st.session_state)
            video_params = {**video_params, "session_id": session_id}
            # Prepare shared config
            shared_config = build_batch_shared_config(video_params)

            # UI containers
            overall_progress_container = st.container()
            current_task_container = st.container()

            # Overall progress UI
            overall_progress_bar = overall_progress_container.progress(0)
            overall_status = overall_progress_container.empty()

            # Current task progress UI
            current_task_title = current_task_container.empty()
            current_task_progress = current_task_container.progress(0)
            current_task_status = current_task_container.empty()

            # Overall progress callback
            def update_overall_progress(current, total, topic):
                progress = (current - 1) / total
                overall_progress_bar.progress(progress)
                overall_status.markdown(
                    f"📊 **{tr('batch.overall_progress')}**: {current}/{total} ({int(progress * 100)}%)"
                )

            # Single task progress callback factory
            def make_task_progress_callback(task_idx, topic):
                def callback(event: ProgressEvent):
                    # Display current task title
                    current_task_title.markdown(f"🎬 **{tr('batch.current_task')} {task_idx}**: {topic}")

                    message = format_progress_event_message(event)

                    if event.extra_info:
                        localized_extra_info = localize_progress_extra_info(event.extra_info)
                        if localized_extra_info:
                            message = f"{message} - {localized_extra_info}"

                    current_task_progress.progress(event.progress)
                    current_task_status.text(message)

                return callback

            # Execute batch generation
            import time

            from web.utils.batch_manager import SimpleBatchManager

            batch_manager = SimpleBatchManager()
            start_time = time.time()

            batch_result = batch_manager.execute_batch(
                pixelle_video=pixelle_video,
                topics=topics,
                shared_config=shared_config,
                overall_progress_callback=update_overall_progress,
                task_progress_callback_factory=make_task_progress_callback
            )

            latest_planning_snapshot = None
            for item in batch_result.get("results", []):
                planning_snapshot = item.get("planning_snapshot")
                if planning_snapshot is not None:
                    latest_planning_snapshot = planning_snapshot

            if latest_planning_snapshot is not None:
                set_storyboard_preview_snapshot(st.session_state, latest_planning_snapshot)
            else:
                set_storyboard_preview_snapshot(st.session_state, None)

            total_time = time.time() - start_time

            # Clear progress displays
            overall_progress_bar.progress(1.0)
            overall_status.markdown(f"✅ **{tr('batch.completed')}**")
            current_task_title.empty()
            current_task_progress.empty()
            current_task_status.empty()

            # Display results summary
            st.markdown("---")
            st.markdown(f"**{tr('batch.results_title')}**")

            col1, col2, col3 = st.columns(3)
            col1.metric(tr("batch.total"), batch_result["total_count"])
            col2.metric(f"✅ {tr('batch.success')}", batch_result["success_count"])
            col3.metric(f"❌ {tr('batch.failed')}", batch_result["failed_count"])

            # Display total time
            minutes = int(total_time / 60)
            seconds = int(total_time % 60)
            st.caption(f"⏱️ {tr('batch.total_time')}: {minutes}{tr('batch.minutes')}{seconds}{tr('batch.seconds')}")

            # Redirect to History page
            st.markdown("---")
            st.success(tr("batch.success_message"))
            st.info(tr("batch.view_in_history"))

            # Button to go to History page using JavaScript URL navigation
            st.markdown(
                f"""
                <a href="/History" target="_blank">
                    <button style="
                        width: 100%;
                        padding: 0.5rem 1rem;
                        background-color: white;
                        color: rgb(49, 51, 63);
                        border: 1px solid rgba(49, 51, 63, 0.2);
                        border-radius: 0.5rem;
                        cursor: pointer;
                        font-size: 1rem;
                        font-weight: 400;
                        text-align: center;
                    ">
                        📚 {tr('batch.goto_history')}
                    </button>
                </a>
                """,
                unsafe_allow_html=True
            )

            # Show failed tasks if any
            if batch_result["errors"]:
                st.markdown("---")
                st.markdown(f"#### {tr('batch.failed_list')}")

                for item in batch_result["errors"]:
                    with st.expander(f"🔴 {tr('batch.task')} {item['index']}: {item['topic']}", expanded=False):
                        st.error(f"**{tr('batch.error')}**: {item['error']}")

                        # Detailed error (collapsed)
                        with st.expander(tr("batch.error_detail")):
                            st.code(item['traceback'], language="python")
