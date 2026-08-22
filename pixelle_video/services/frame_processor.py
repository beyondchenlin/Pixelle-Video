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
Frame processor - Process single frame through complete pipeline

Orchestrates: TTS 鈫?Image Generation 鈫?Frame Composition 鈫?Video Segment

Key Feature:
- TTS-driven video duration: Audio duration from TTS is passed to video generation workflows
  to ensure perfect sync between audio and video (no padding, no trimming needed)
"""

import hashlib
import inspect
import os
import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable, Optional

from loguru import logger

from pixelle_video.models.progress import ProgressEvent, ProgressEventType, ProgressFrameAction
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.visual_anchor_two_stage import (
    VisualAnchorImageGenerationRequest,
)
from pixelle_video.services.prompt_trace_artifacts import (
    build_media_prompt_trace_context,
    build_workflow_params_trace,
    write_single_media_prompt_trace_context,
)
from pixelle_video.services.remote_media import (
    configured_workflow_output_origins,
    configured_workflow_output_roots,
    materialize_media_source,
)
from pixelle_video.services.tts_segmentation import build_external_tts_segmentation_plan
from pixelle_video.services.visual_anchor_generation_binding import (
    VISUAL_ANCHOR_GENERATION_REQUEST_PARAM,
)
from pixelle_video.tts_split_strategy import INTERNAL_ONLY_TTS_SPLIT_MODE
from pixelle_video.tts_workflow_contract import (
    is_index_tts2_workflow_key,
    resolve_workflow_output_audio_extension_from_info,
    resolve_workflow_output_audio_extension_from_key,
)
from pixelle_video.utils.template_util import get_template_type
from pixelle_video.utils.text_splitting import format_caption_text

IMAGE_SEGMENT_MIN_FPS = 90


def _media_call_trace_output_dir(
    trace_context: dict,
    *,
    frame_index: int,
    generation_attempt: int = 0,
) -> Path:
    artifact_path = Path(str(trace_context.get("artifact_path") or ""))
    if artifact_path.name:
        prompt_trace_root = next(
            (
                parent
                for parent in artifact_path.parents
                if parent.name == "prompt_traces"
            ),
            None,
        )
        task_root = prompt_trace_root.parent if prompt_trace_root else artifact_path.parent
    else:
        task_root = Path(".")
    output_dir = task_root / "media_prompt_calls" / f"frame_{frame_index + 1:03d}"
    if generation_attempt > 0:
        output_dir = output_dir / f"retry_{generation_attempt:02d}"
    return output_dir


@asynccontextmanager
async def _maybe_local_comfyui_workflow_session(
    core,
    *,
    backend_role: str = "default",
    stop_after_session: bool = False,
):
    session_factory = getattr(core, "local_comfyui_workflow_session", None)
    if callable(session_factory):
        try:
            signature = inspect.signature(session_factory)
        except (TypeError, ValueError):
            supports_stop_after_session = True
            supports_legacy_release_after_session = False
            supports_backend_role = True
        else:
            supports_variadic_keywords = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            supports_stop_after_session = (
                "stop_after_session" in signature.parameters
                or supports_variadic_keywords
            )
            supports_legacy_release_after_session = (
                "release_after_session" in signature.parameters
                or supports_variadic_keywords
            )
            supports_backend_role = (
                "backend_role" in signature.parameters
                or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                )
            )

        session_kwargs = {}
        if supports_stop_after_session:
            session_kwargs["stop_after_session"] = stop_after_session
        elif supports_legacy_release_after_session:
            session_kwargs["release_after_session"] = stop_after_session
        if supports_backend_role:
            session_kwargs["backend_role"] = backend_role

        session_context = session_factory(**session_kwargs) if session_kwargs else session_factory()
        async with session_context:
            yield
        return

    yield


def _resolve_local_comfyui_tts_backend_role(core, workflow_key) -> str:
    get_registry = getattr(core, "_get_comfyui_backend_registry", None)
    if not callable(get_registry):
        return "default"
    return get_registry().resolve_role_for_tts(workflow_key)


def _format_template_body_text(
    default_body_text: str,
    template_body_text: Optional[str] = None,
    *,
    punctuation_mode: str = "strip_all",
) -> str:
    """Resolve text explicitly intended for the HTML template body."""
    source_text = default_body_text if template_body_text is None else template_body_text
    return format_caption_text(source_text, punctuation_mode=punctuation_mode)


def _get_image_segment_fps(configured_fps: int) -> int:
    """Use a higher internal fps for still-image segments to reduce timing quantization."""
    return max(configured_fps, IMAGE_SEGMENT_MIN_FPS)


def _generation_retry_seed(
    *,
    task_id: str,
    frame_index: int,
    generation_attempt: int,
) -> int | None:
    if type(generation_attempt) is not int or generation_attempt < 0:
        raise ValueError("generation_attempt must be a non-negative integer")
    if generation_attempt == 0:
        return None
    material = f"{task_id}:{frame_index}:{generation_attempt}".encode("utf-8")
    value = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return (value % 2_147_483_646) + 1


class FrameProcessor:
    """Frame processor"""

    def __init__(self, pixelle_video_core):
        """
        Initialize

        Args:
            pixelle_video_core: PixelleVideoCore instance
        """
        self.core = pixelle_video_core

    async def __call__(
        self,
        frame: StoryboardFrame,
        storyboard: 'Storyboard',
        config: StoryboardConfig,
        total_frames: int = 1,
        progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
        template_body_text: Optional[str] = None,
        element_motion_materializer: Optional[
            Callable[[StoryboardFrame], Awaitable[None]]
        ] = None,
        media_validator: Optional[
            Callable[[StoryboardFrame, int], Awaitable[bool]]
        ] = None,
        media_generation_max_attempts: int = 1,
    ) -> StoryboardFrame:
        """
        Process single frame through complete pipeline

        Steps:
        1. Generate audio (TTS)
        2. Generate image (ComfyKit)
        3. Compose frame (add subtitle)
        4. Create video segment (image + audio)

        Args:
            frame: Storyboard frame to process
            storyboard: Storyboard instance
            config: Storyboard configuration
            total_frames: Total number of frames in storyboard
            progress_callback: Optional callback for progress updates (receives ProgressEvent)
            template_body_text: Optional text to render inside the HTML template body.
                An empty string means shell-only rendering; None lets the configured
                template text policy choose its legacy default.

        Returns:
            Processed frame with all paths filled
        """
        logger.info(f"Processing frame {frame.index}...")

        frame_num = frame.index + 1

        # Determine if this frame needs image generation
        # If image_path or video_path is already set (e.g. asset-based pipeline), we consider it "has existing media" but skip generation
        has_existing_media = frame.image_path is not None or frame.video_path is not None
        needs_generation = frame.image_prompt is not None

        try:
            # Step 1: Generate audio (TTS)
            if not frame.audio_path:
                if progress_callback:
                    progress_callback(ProgressEvent(
                        event_type=ProgressEventType.FRAME_STEP,
                        progress=0.0,
                        frame_current=frame_num,
                        frame_total=total_frames,
                        step=1,
                        action=ProgressFrameAction.AUDIO
                    ))
                await self._step_generate_audio(frame, config)
            else:
                logger.debug(f"  1/4: Using existing audio: {frame.audio_path}")

            # Step 2: Generate media (image or video, conditional)
            if needs_generation:
                if progress_callback:
                    progress_callback(ProgressEvent(
                        event_type=ProgressEventType.FRAME_STEP,
                        progress=0.25,
                        frame_current=frame_num,
                        frame_total=total_frames,
                        step=2,
                        action=ProgressFrameAction.MEDIA
                    ))
                await self._step_generate_media_with_validation(
                    frame,
                    config,
                    media_validator=media_validator,
                    max_attempts=media_generation_max_attempts,
                )
            elif has_existing_media:
                # Log appropriate message based on media type
                if frame.video_path:
                    logger.debug(f"  2/4: Using existing video: {frame.video_path}")
                else:
                    logger.debug(f"  2/4: Using existing image: {frame.image_path}")
            else:
                frame.image_path = None
                frame.media_type = None
                logger.debug("  2/4: Skipped media generation (not required by template)")

            # Step 3: Compose frame (add subtitle)
            if progress_callback:
                progress_callback(ProgressEvent(
                    event_type=ProgressEventType.FRAME_STEP,
                    progress=0.50 if (needs_generation or has_existing_media) else 0.33,
                    frame_current=frame_num,
                    frame_total=total_frames,
                    step=3,
                    action=ProgressFrameAction.COMPOSE
                ))
            await self._step_compose_frame(
                frame,
                storyboard,
                config,
                template_body_text=template_body_text,
            )

            if element_motion_materializer is not None:
                await element_motion_materializer(frame)

            # Step 4: Create video segment
            if progress_callback:
                progress_callback(ProgressEvent(
                    event_type=ProgressEventType.FRAME_STEP,
                    progress=0.75 if (needs_generation or has_existing_media) else 0.67,
                    frame_current=frame_num,
                    frame_total=total_frames,
                    step=4,
                    action=ProgressFrameAction.VIDEO
                ))

            await self._step_create_video_segment(frame, config)

            logger.info(f"鉁?Frame {frame.index} completed")
            return frame

        except Exception as e:
            logger.error(f"鉂?Failed to process frame {frame.index}: {e}")
            raise

    async def _step_generate_audio(
        self,
        frame: StoryboardFrame,
        config: StoryboardConfig
    ):
        """Step 1: Generate audio using TTS"""
        logger.debug(f"  1/4: Generating audio for frame {frame.index}...")

        # Generate output path using task_id
        from pixelle_video.utils.os_util import get_task_frame_path
        output_path = get_task_frame_path(config.task_id, frame.index, "audio")
        segment_texts = [frame.narration]
        uses_index_tts2 = self._uses_index_tts2_workflow(config)
        tts_workflow_key = config.tts_workflow
        tts_resolver = getattr(getattr(self.core, "tts", None), "_resolve_workflow", None)
        if callable(tts_resolver):
            try:
                tts_workflow_info = tts_resolver(workflow=tts_workflow_key)
            except TypeError:
                tts_workflow_info = tts_resolver(tts_workflow_key)
            if isinstance(tts_workflow_info, dict):
                tts_workflow_key = (
                    tts_workflow_info.get("key")
                    or tts_workflow_info.get("path")
                    or tts_workflow_key
                )
        tts_backend_role = _resolve_local_comfyui_tts_backend_role(
            self.core,
            tts_workflow_key,
        )

        if (
            uses_index_tts2
            and config.tts_split_mode != INTERNAL_ONLY_TTS_SPLIT_MODE
        ):
            plan = build_external_tts_segmentation_plan(
                frame.narration,
                max_chars_per_segment=config.max_chars_per_tts_segment,
                boundary_search_radius=config.tts_boundary_search_radius,
                soft_overflow_chars=config.tts_soft_overflow_chars,
                source_unit_type="frame",
                source_unit_id=f"frame-{frame.index + 1}",
                overflow_policy=config.tts_split_overflow_policy,
            )
            segment_texts = [segment.text for segment in plan.segments] or [frame.narration]

        source_extension = self._resolve_tts_source_extension(config)
        if len(segment_texts) > 1:
            final_output_path = str(Path(output_path).with_suffix(".wav"))
            segment_paths = []
            output_base = Path(final_output_path)
            async with _maybe_local_comfyui_workflow_session(
                self.core,
                backend_role=tts_backend_role,
                stop_after_session=True,
            ):
                for index, segment_text in enumerate(segment_texts, start=1):
                    segment_output_path = str(
                        output_base.with_name(
                            f"{output_base.stem}_segment_{index}_source{source_extension}"
                        )
                    )
                    await self.core.tts(
                        **self._build_tts_params(
                            text=segment_text,
                            output_path=segment_output_path,
                            config=config,
                            index=frame.index + 1,
                        )
                    )
                    segment_paths.append(segment_output_path)

            self._concat_audio_files(
                segment_paths,
                final_output_path,
                fade_ms=config.tts_audio_boundary_fade_ms,
            )
            audio_path = final_output_path
        elif uses_index_tts2:
            final_output_path = str(Path(output_path).with_suffix(".wav"))
            output_base = Path(final_output_path)
            source_output_path = str(
                output_base.with_name(f"{output_base.stem}_source{source_extension}")
            )
            async with _maybe_local_comfyui_workflow_session(
                self.core,
                backend_role=tts_backend_role,
                stop_after_session=True,
            ):
                await self.core.tts(
                    **self._build_tts_params(
                        text=segment_texts[0],
                        output_path=source_output_path,
                        config=config,
                        index=frame.index + 1,
                    )
                )
            audio_path = self._normalize_audio_for_frame(source_output_path, final_output_path)
        else:
            if config.tts_inference_mode == "comfyui":
                async with _maybe_local_comfyui_workflow_session(
                    self.core,
                    backend_role=tts_backend_role,
                    stop_after_session=True,
                ):
                    audio_path = await self.core.tts(
                        **self._build_tts_params(
                            text=segment_texts[0],
                            output_path=output_path,
                            config=config,
                            index=frame.index + 1,
                        )
                    )
            else:
                audio_path = await self.core.tts(
                    **self._build_tts_params(
                        text=segment_texts[0],
                        output_path=output_path,
                        config=config,
                        index=frame.index + 1,
                    )
                )

        frame.audio_path = audio_path

        # Get audio duration
        frame.duration = await self._get_audio_duration(audio_path)

        logger.debug(f"  鉁?Audio generated: {audio_path} ({frame.duration:.2f}s)")

    def _build_tts_params(
        self,
        *,
        text: str,
        output_path: str,
        config: StoryboardConfig,
        index: int,
    ) -> dict:
        tts_params = {
            "text": text,
            "inference_mode": config.tts_inference_mode,
            "output_path": output_path,
        }

        if config.tts_inference_mode == "local":
            # Local mode: pass voice and speed
            if config.voice_id:
                tts_params["voice"] = config.voice_id
            if config.tts_speed is not None:
                tts_params["speed"] = config.tts_speed
        else:  # comfyui
            # ComfyUI mode: pass workflow, voice, speed, and ref_audio
            tts_params["index"] = index  # 1-based index for workflow
            if config.tts_workflow:
                tts_params["workflow"] = config.tts_workflow
            if config.voice_id:
                tts_params["voice"] = config.voice_id
            if config.tts_speed is not None:
                tts_params["speed"] = config.tts_speed
            if config.ref_audio:
                tts_params["ref_audio"] = config.ref_audio
            if config.ref_audio_text:
                tts_params["ref_audio_text"] = config.ref_audio_text

        return tts_params

    def _uses_index_tts2_workflow(self, config: StoryboardConfig) -> bool:
        if config.tts_inference_mode != "comfyui":
            return False

        workflow_key = config.tts_workflow or ""
        tts_service = getattr(self.core, "tts", None)
        if tts_service is not None and hasattr(tts_service, "_resolve_workflow"):
            try:
                workflow_key = tts_service._resolve_workflow(workflow=config.tts_workflow)["key"]
            except Exception:
                workflow_key = config.tts_workflow or workflow_key

        return is_index_tts2_workflow_key(workflow_key)

    def _resolve_tts_source_extension(self, config: StoryboardConfig) -> str:
        if config.tts_inference_mode != "comfyui":
            return ".mp3"

        tts_service = getattr(self.core, "tts", None)
        if tts_service is not None and hasattr(tts_service, "_resolve_workflow"):
            try:
                workflow_info = tts_service._resolve_workflow(workflow=config.tts_workflow)
                extension = resolve_workflow_output_audio_extension_from_info(
                    workflow_info,
                    default=".mp3",
                )
                return extension or ".mp3"
            except Exception:
                pass

        extension = resolve_workflow_output_audio_extension_from_key(
            config.tts_workflow,
            default=".mp3",
        )
        return extension or ".mp3"

    def _concat_audio_files(self, audio_paths: list[str], output_path: str, *, fade_ms: int = 0) -> None:
        if not audio_paths:
            raise ValueError("Frame TTS audio synthesis requires at least one segment.")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if len(audio_paths) == 1:
            shutil.copy2(audio_paths[0], output_path)
            return

        fade_duration = max(float(fade_ms), 0.0) / 1000.0
        command = ["ffmpeg"]
        filter_parts: list[str] = []
        labels: list[str] = []

        for index, audio_path in enumerate(audio_paths):
            command.extend(["-i", audio_path])
            duration = max(self._get_audio_duration_sync(audio_path), 0.01)
            boundary_fade = min(fade_duration, duration / 4)
            filters = ["aresample=async=1:first_pts=0"]

            if boundary_fade > 0 and index > 0:
                filters.append(f"afade=t=in:st=0:d={self._format_ffmpeg_time(boundary_fade)}")
            if boundary_fade > 0 and index < len(audio_paths) - 1:
                fade_out_start = max(duration - boundary_fade, 0.0)
                filters.append(
                    "afade=t=out:"
                    f"st={self._format_ffmpeg_time(fade_out_start)}:"
                    f"d={self._format_ffmpeg_time(boundary_fade)}"
                )

            label = f"a{index}"
            filter_parts.append(f"[{index}:a]{','.join(filters)}[{label}]")
            labels.append(f"[{label}]")

        filter_complex = (
            ";".join(filter_parts)
            + f";{''.join(labels)}concat=n={len(audio_paths)}:v=0:a=1[out]"
        )
        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ]
        )

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise RuntimeError(f"Failed to concatenate frame TTS audio: {detail}")

    def _normalize_audio_for_frame(self, input_path: str, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                "ffmpeg",
                "-i",
                input_path,
                "-c:a",
                "pcm_s16le",
                "-y",
                output_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise RuntimeError(f"Failed to normalize frame TTS audio: {detail}")
        return output_path

    def _get_audio_duration_sync(self, audio_path: str) -> float:
        try:
            import ffmpeg

            probe = ffmpeg.probe(audio_path)
            return float(probe["format"]["duration"])
        except Exception:
            file_size = os.path.getsize(audio_path)
            return max(1.0, file_size / 2000)

    @staticmethod
    def _format_ffmpeg_time(value: float) -> str:
        return f"{max(float(value), 0.0):.3f}".rstrip("0").rstrip(".") or "0"

    async def _step_generate_media_with_validation(
        self,
        frame: StoryboardFrame,
        config: StoryboardConfig,
        *,
        media_validator: Optional[
            Callable[[StoryboardFrame, int], Awaitable[bool]]
        ] = None,
        max_attempts: int = 1,
    ) -> None:
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError("media generation max_attempts must be between 1 and 3")
        if frame.visual_anchor_generation_request is not None and max_attempts != 1:
            raise ValueError(
                "visual-anchor generation permits exactly one first image request"
            )
        for generation_attempt in range(max_attempts):
            if generation_attempt == 0:
                await self._step_generate_media(frame, config)
            else:
                await self._step_generate_media(
                    frame,
                    config,
                    generation_attempt=generation_attempt,
                )
            if media_validator is None:
                return
            if await media_validator(frame, generation_attempt):
                return
        raise RuntimeError(
            "generated media failed rendered-output validation after bounded attempts"
        )

    async def _step_generate_media(
        self,
        frame: StoryboardFrame,
        config: StoryboardConfig,
        *,
        generation_attempt: int = 0,
    ):
        """Step 2: Generate media (image or video) using ComfyKit"""
        logger.debug(f"  2/4: Generating media for frame {frame.index}...")

        # Determine media type based on template first, then workflow name fallback.
        workflow_name = config.media_workflow or ""
        template_type = get_template_type(config.frame_template or "")
        is_video_workflow = template_type == "video" or "video_" in workflow_name.lower()
        media_type = "video" if is_video_workflow else "image"

        logger.debug(f"  鈫?Media type: {media_type} (workflow: {workflow_name})")

        # Build media generation parameters
        media_params = {
            "prompt": frame.image_prompt,
            "workflow": config.media_workflow,  # Pass workflow from config (None = use default)
            "media_type": media_type,
            "width": config.media_width,
            "height": config.media_height,
            "index": frame.index + 1,  # 1-based index for workflow
        }
        visual_anchor_request = None
        if frame.visual_anchor_generation_request is not None:
            visual_anchor_request = VisualAnchorImageGenerationRequest.model_validate(
                frame.visual_anchor_generation_request
            )
            if generation_attempt != 0:
                raise ValueError(
                    "visual-anchor generation cannot create a repair or retry image"
                )
            if visual_anchor_request.task_id != config.task_id:
                raise ValueError("visual-anchor request task id differs from storyboard")
            if visual_anchor_request.frame_id != frame.frame_id:
                raise ValueError("visual-anchor request frame id differs from storyboard")
            if visual_anchor_request.final_positive_prompt != frame.image_prompt:
                raise ValueError("visual-anchor request prompt differs from storyboard")
            if frame.generation_seed != visual_anchor_request.random_seed:
                raise ValueError("visual-anchor request seed differs from storyboard")
            if visual_anchor_request.workflow_key != config.media_workflow:
                raise ValueError(
                    "visual-anchor request workflow differs from storyboard"
                )
            if (
                visual_anchor_request.expected_execution.width != config.media_width
                or visual_anchor_request.expected_execution.height
                != config.media_height
            ):
                raise ValueError(
                    "visual-anchor request dimensions differ from storyboard"
                )
            media_params["seed"] = visual_anchor_request.random_seed
            media_params["reference_image_workflow_injection_mode"] = "required"
            media_params[VISUAL_ANCHOR_GENERATION_REQUEST_PARAM] = (
                visual_anchor_request.model_dump(mode="json")
            )
            retry_seed = None
        else:
            retry_seed = _generation_retry_seed(
                task_id=config.task_id,
                frame_index=frame.index,
                generation_attempt=generation_attempt,
            )
            if retry_seed is not None:
                media_params["seed"] = retry_seed
        frame_negative_prompt = (
            visual_anchor_request.final_negative_prompt
            if visual_anchor_request is not None
            else frame.negative_prompt or config.media_negative_prompt
        )
        if (
            visual_anchor_request is not None
            and (frame_negative_prompt or "")
            != visual_anchor_request.final_negative_prompt
        ):
            raise ValueError(
                "visual-anchor request negative prompt differs from storyboard"
            )
        if frame_negative_prompt:
            media_params["negative_prompt"] = frame_negative_prompt

        # For video workflows: pass audio duration as target video duration
        # This ensures video length matches audio length from the source
        if is_video_workflow and frame.duration:
            media_params["duration"] = frame.duration
            logger.info(f"  鈫?Generating video with target duration: {frame.duration:.2f}s (from TTS audio)")

        trace_context = getattr(config, "media_prompt_trace_context", None)
        if trace_context:
            frame_ids_by_index = trace_context.get("frame_ids_by_index") or {}
            legacy_frame_id = (
                frame_ids_by_index.get(str(frame.index))
                if isinstance(frame_ids_by_index, dict)
                else None
            )
            resolved_frame_id = str(
                frame.frame_id or legacy_frame_id or frame.index + 1
            )
            workflow_params_for_trace = {
                "prompt": frame.image_prompt or "",
                "width": config.media_width,
                "height": config.media_height,
                "index": media_params["index"],
            }
            if "seed" in media_params:
                workflow_params_for_trace["seed"] = media_params["seed"]
            if frame_negative_prompt:
                workflow_params_for_trace["negative_prompt"] = frame_negative_prompt
            if "duration" in media_params:
                workflow_params_for_trace["duration"] = media_params["duration"]
            workflow_param_trace = build_workflow_params_trace(
                workflow_params_for_trace,
                prompt=frame.image_prompt or "",
            )
            if workflow_param_trace:
                media_params["media_prompt_trace_context"] = (
                    write_single_media_prompt_trace_context(
                        _media_call_trace_output_dir(
                            trace_context,
                            frame_index=frame.index,
                            generation_attempt=generation_attempt,
                        ),
                        task_id=trace_context.get("task_id") or config.task_id or "",
                        prompt=frame.image_prompt or "",
                        negative_prompt=frame_negative_prompt or "",
                        workflow=str(
                            trace_context.get("workflow")
                            or trace_context.get("workflow_input")
                            or config.media_workflow
                            or ""
                        ),
                        workflow_input=str(
                            trace_context.get("workflow_input")
                            or trace_context.get("workflow")
                            or config.media_workflow
                            or ""
                        ),
                        media_type=media_type,
                        source="frame_processor_media_call",
                        frame_id=resolved_frame_id,
                        media_width=config.media_width,
                        media_height=config.media_height,
                        generation_context={
                            "source_artifact_path": trace_context.get("artifact_path"),
                            "frame_index": frame.index,
                            "generation_attempt": (
                                visual_anchor_request.generation_attempt
                                if visual_anchor_request is not None
                                else generation_attempt
                            ),
                            "visual_anchor_generation_request": (
                                visual_anchor_request.model_dump(mode="json")
                                if visual_anchor_request is not None
                                else None
                            ),
                        },
                        workflow_params=workflow_params_for_trace,
                        task_root=trace_context.get("task_root"),
                    )
                )
            else:
                media_params["media_prompt_trace_context"] = build_media_prompt_trace_context(
                    artifact_path=trace_context.get("artifact_path", ""),
                    task_id=trace_context.get("task_id") or config.task_id or "",
                    prompt=frame.image_prompt or "",
                    negative_prompt=frame_negative_prompt or "",
                    workflow_context=trace_context,
                    media_type=media_type,
                    frame_id=resolved_frame_id,
                    media_width=config.media_width,
                    media_height=config.media_height,
                    task_root=trace_context.get("task_root"),
                )

        # Call Media generation
        media_result = await self.core.media(**media_params)

        # Store media type
        frame.media_type = media_result.media_type

        if media_result.is_image:
            # Download image to local (pass task_id)
            local_path = await self._download_media(
                media_result.url,
                frame.index,
                config.task_id,
                media_type="image"
            )
            frame.image_path = local_path
            logger.debug(f"  鉁?Image generated: {local_path}")

        elif media_result.is_video:
            # Download video to local (pass task_id)
            local_path = await self._download_media(
                media_result.url,
                frame.index,
                config.task_id,
                media_type="video"
            )
            frame.video_path = local_path

            # Update duration from video if available
            if media_result.duration:
                frame.duration = media_result.duration
                logger.debug(f"  鉁?Video generated: {local_path} (duration: {frame.duration:.2f}s)")
            else:
                # Get video duration from file
                frame.duration = await self._get_video_duration(local_path)
                logger.debug(f"  鉁?Video generated: {local_path} (duration: {frame.duration:.2f}s)")

        else:
            raise ValueError(f"Unknown media type: {media_result.media_type}")

    async def _step_compose_frame(
        self,
        frame: StoryboardFrame,
        storyboard: 'Storyboard',
        config: StoryboardConfig,
        *,
        template_body_text: Optional[str] = None,
    ):
        """Step 3: Compose frame with subtitle using HTML template"""
        logger.debug(f"  3/4: Composing frame {frame.index}...")

        # Generate output path using task_id
        from pixelle_video.utils.os_util import get_task_frame_path
        output_path = get_task_frame_path(config.task_id, frame.index, "composed")

        # For video type: render HTML as transparent overlay image
        # For image type: render HTML with image background
        # In both cases, we need the composed image
        composed_path = await self._compose_frame_html(
            frame,
            storyboard,
            config,
            output_path,
            template_body_text=template_body_text,
        )

        frame.composed_image_path = composed_path

        logger.debug(f"  鉁?Frame composed: {composed_path}")

    async def _compose_frame_html(
        self,
        frame: StoryboardFrame,
        storyboard: 'Storyboard',
        config: StoryboardConfig,
        output_path: str,
        *,
        template_body_text: Optional[str] = None,
    ) -> str:
        """Compose frame using HTML template"""
        from pixelle_video.models.template_text_policy import (
            resolve_caption_renderer_text,
            resolve_template_text_policy_for_body_override,
        )
        from pixelle_video.services.template_visual_materializer import TemplateVisualMaterializer
        from pixelle_video.utils.template_util import resolve_template_path

        # Resolve template path (handles various input formats)
        template_path = resolve_template_path(config.frame_template)
        text_policy = resolve_template_text_policy_for_body_override(
            getattr(config, "template_text_policy", "caption_renderer"),
            template_body_text,
        )
        body_text = _format_template_body_text(
            frame.narration,
            template_body_text,
            punctuation_mode=config.caption_punctuation_mode,
        )
        caption_text = resolve_caption_renderer_text(body_text, text_policy)

        # Use video_path for video media, image_path for images
        media_path = frame.video_path if frame.media_type == "video" else frame.image_path
        logger.debug(f"Generating frame with media: '{media_path}' (type: {frame.media_type})")

        asset = await TemplateVisualMaterializer().materialize_frame(
            title=storyboard.title,
            template_body_text=body_text,
            caption_text=caption_text,
            media_path=media_path,
            frame_index=frame.index,
            template_path=template_path,
            template_id=Path(template_path).stem,
            output_path=output_path,
            text_policy=text_policy,
            template_params=config.template_params or {},
            canvas_width=getattr(config, "canvas_width", None),
            canvas_height=getattr(config, "canvas_height", None),
            media_layout_mode=getattr(config, "media_layout_mode", "template"),
            media_type=frame.media_type or "image",
            media_width=config.media_width,
            media_height=config.media_height,
            media_placement=config.media_placement,
            text_rendering=getattr(config, "text_rendering", None) or {},
            template_display=getattr(config, "template_display", None),
            layered_template_spec=getattr(config, "layered_template_spec", None),
        )

        frame.template_visual_path = asset.path
        return asset.path

    async def _step_create_video_segment(
        self,
        frame: StoryboardFrame,
        config: StoryboardConfig
    ):
        """Step 4: Create video segment from media + audio"""
        logger.debug(f"  4/4: Creating video segment for frame {frame.index}...")

        # Generate output path using task_id
        from pixelle_video.utils.os_util import get_task_frame_path
        output_path = get_task_frame_path(config.task_id, frame.index, "segment")

        from pixelle_video.services.video import VideoService
        video_service = VideoService()

        if frame.element_motion_video_path:
            logger.debug("  -> Using element motion video as segment source")
            if frame.audio_path:
                segment_path = video_service.merge_audio_video(
                    video=frame.element_motion_video_path,
                    audio=frame.audio_path,
                    output=output_path,
                    replace_audio=True,
                    audio_volume=1.0,
                )
            else:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(frame.element_motion_video_path, output_path)
                segment_path = output_path
            frame.video_segment_path = segment_path
            logger.debug(f"  Video segment created: {segment_path}")
            return

        # Branch based on media type
        if frame.media_type == "video":
            # Video workflow: overlay HTML template on video, then add audio
            logger.debug("  鈫?Using video-based composition with HTML overlay")

            # Step 1: Overlay transparent HTML image on video
            # The composed_image_path contains the rendered HTML with transparent background
            temp_video_with_overlay = get_task_frame_path(config.task_id, frame.index, "video") + "_overlay.mp4"

            video_service.overlay_image_on_video(
                video=frame.video_path,
                overlay_image=frame.composed_image_path,
                output=temp_video_with_overlay,
                scale_mode="contain"  # Scale video to fit template size (contain mode)
            )

            # Step 2: Add narration audio to the overlaid video
            # Note: The video might have audio (replaced) or be silent (audio added)
            segment_path = video_service.merge_audio_video(
                video=temp_video_with_overlay,
                audio=frame.audio_path,
                output=output_path,
                replace_audio=True,  # Replace video audio with narration
                audio_volume=1.0
            )

            # Clean up temp file
            import os
            if os.path.exists(temp_video_with_overlay):
                os.unlink(temp_video_with_overlay)

        elif frame.media_type == "image" or frame.media_type is None:
            # Image workflow: Use composed image directly
            # The asset_default.html template includes the image in the composition
            logger.debug("  鈫?Using image-based composition")

            segment_path = video_service.create_video_from_image(
                image=frame.composed_image_path,
                audio=frame.audio_path,
                output=output_path,
                fps=_get_image_segment_fps(config.video_fps)
            )

        else:
            raise ValueError(f"Unknown media type: {frame.media_type}")

        frame.video_segment_path = segment_path

        logger.debug(f"  鉁?Video segment created: {segment_path}")

    async def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds"""
        try:
            # Try using ffmpeg-python
            import ffmpeg
            probe = ffmpeg.probe(audio_path)
            duration = float(probe['format']['duration'])
            return duration
        except Exception as e:
            logger.warning(f"Failed to get audio duration: {e}, using estimate")
            # Fallback: estimate based on file size (very rough)
            import os
            file_size = os.path.getsize(audio_path)
            # Assume ~16kbps for MP3, so 2KB per second
            estimated_duration = file_size / 2000
            return max(1.0, estimated_duration)  # At least 1 second

    async def _download_media(
        self,
        url: str,
        frame_index: int,
        task_id: str,
        media_type: str
    ) -> str:
        """Download media (image or video) from URL to local file"""
        from pixelle_video.utils.os_util import get_task_frame_path
        output_path = get_task_frame_path(task_id, frame_index, media_type)

        await materialize_media_source(
            url,
            output_path,
            media_type=media_type,
            trusted_private_origins=configured_workflow_output_origins(self.core),
            trusted_local_roots=configured_workflow_output_roots(),
        )

        return output_path

    async def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds"""
        try:
            import ffmpeg
            probe = ffmpeg.probe(video_path)
            duration = float(probe['format']['duration'])
            return duration
        except Exception as e:
            logger.warning(f"Failed to get video duration: {e}, using audio duration")
            # Fallback: use audio duration if available
            return 1.0  # Default to 1 second if unable to determine
