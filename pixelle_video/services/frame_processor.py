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

Orchestrates: TTS → Image Generation → Frame Composition → Video Segment

Key Feature:
- TTS-driven video duration: Audio duration from TTS is passed to video generation workflows
  to ensure perfect sync between audio and video (no padding, no trimming needed)
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx
from loguru import logger

from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.tts_segmentation import build_external_tts_segmentation_plan
from pixelle_video.tts_split_strategy import INTERNAL_ONLY_TTS_SPLIT_MODE
from pixelle_video.tts_workflow_contract import is_index_tts2_workflow_key
from pixelle_video.utils.text_splitting import format_caption_text
from pixelle_video.utils.template_util import get_template_type

IMAGE_SEGMENT_MIN_FPS = 90


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
                        event_type="frame_step",
                        progress=0.0,
                        frame_current=frame_num,
                        frame_total=total_frames,
                        step=1,
                        action="audio"
                    ))
                await self._step_generate_audio(frame, config)
            else:
                logger.debug(f"  1/4: Using existing audio: {frame.audio_path}")
            
            # Step 2: Generate media (image or video, conditional)
            if needs_generation:
                if progress_callback:
                    progress_callback(ProgressEvent(
                        event_type="frame_step",
                        progress=0.25,
                        frame_current=frame_num,
                        frame_total=total_frames,
                        step=2,
                        action="media"
                    ))
                await self._step_generate_media(frame, config)
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
                    event_type="frame_step",
                    progress=0.50 if (needs_generation or has_existing_media) else 0.33,
                    frame_current=frame_num,
                    frame_total=total_frames,
                    step=3,
                    action="compose"
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
                    event_type="frame_step",
                    progress=0.75 if (needs_generation or has_existing_media) else 0.67,
                    frame_current=frame_num,
                    frame_total=total_frames,
                    step=4,
                    action="video"
                ))
            
            await self._step_create_video_segment(frame, config)
            
            logger.info(f"✅ Frame {frame.index} completed")
            return frame

        except Exception as e:
            logger.error(f"❌ Failed to process frame {frame.index}: {e}")
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

        if (
            self._uses_index_tts2_workflow(config)
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

        if len(segment_texts) > 1:
            final_output_path = str(Path(output_path).with_suffix(".wav"))
            segment_paths = []
            output_base = Path(final_output_path)
            for index, segment_text in enumerate(segment_texts, start=1):
                segment_output_path = str(
                    output_base.with_name(f"{output_base.stem}_segment_{index}.mp3")
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

        logger.debug(f"  ✓ Audio generated: {audio_path} ({frame.duration:.2f}s)")

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
            "index": index,  # 1-based index for workflow
        }
        
        if config.tts_inference_mode == "local":
            # Local mode: pass voice and speed
            if config.voice_id:
                tts_params["voice"] = config.voice_id
            if config.tts_speed is not None:
                tts_params["speed"] = config.tts_speed
        else:  # comfyui
            # ComfyUI mode: pass workflow, voice, speed, and ref_audio
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
    
    async def _step_generate_media(
        self,
        frame: StoryboardFrame,
        config: StoryboardConfig
    ):
        """Step 2: Generate media (image or video) using ComfyKit"""
        logger.debug(f"  2/4: Generating media for frame {frame.index}...")
        
        # Determine media type based on template first, then workflow name fallback.
        workflow_name = config.media_workflow or ""
        template_type = get_template_type(config.frame_template or "")
        is_video_workflow = template_type == "video" or "video_" in workflow_name.lower()
        media_type = "video" if is_video_workflow else "image"
        
        logger.debug(f"  → Media type: {media_type} (workflow: {workflow_name})")
        
        # Build media generation parameters
        media_params = {
            "prompt": frame.image_prompt,
            "workflow": config.media_workflow,  # Pass workflow from config (None = use default)
            "media_type": media_type,
            "width": config.media_width,
            "height": config.media_height,
            "index": frame.index + 1,  # 1-based index for workflow
        }
        if config.media_negative_prompt:
            media_params["negative_prompt"] = config.media_negative_prompt
        
        # For video workflows: pass audio duration as target video duration
        # This ensures video length matches audio length from the source
        if is_video_workflow and frame.duration:
            media_params["duration"] = frame.duration
            logger.info(f"  → Generating video with target duration: {frame.duration:.2f}s (from TTS audio)")
        
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
            logger.debug(f"  ✓ Image generated: {local_path}")
        
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
                logger.debug(f"  ✓ Video generated: {local_path} (duration: {frame.duration:.2f}s)")
            else:
                # Get video duration from file
                frame.duration = await self._get_video_duration(local_path)
                logger.debug(f"  ✓ Video generated: {local_path} (duration: {frame.duration:.2f}s)")
        
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
        
        logger.debug(f"  ✓ Frame composed: {composed_path}")
    
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
        from pixelle_video.services.template_visual_materializer import TemplateVisualMaterializer
        from pixelle_video.utils.template_util import resolve_template_path
        
        # Resolve template path (handles various input formats)
        template_path = resolve_template_path(config.frame_template)
        text_policy = getattr(config, "template_text_policy", "caption_renderer")
        if template_body_text is not None:
            text_policy = "template_body" if template_body_text else "caption_renderer"
        body_text = _format_template_body_text(
            frame.narration,
            template_body_text,
            punctuation_mode=config.caption_punctuation_mode,
        )
        
        # Use video_path for video media, image_path for images
        media_path = frame.video_path if frame.media_type == "video" else frame.image_path
        logger.debug(f"Generating frame with media: '{media_path}' (type: {frame.media_type})")
        
        asset = await TemplateVisualMaterializer().materialize_frame(
            title=storyboard.title,
            template_body_text=body_text,
            media_path=media_path,
            frame_index=frame.index,
            template_path=template_path,
            template_id=Path(template_path).stem,
            output_path=output_path,
            text_policy=text_policy,
            template_params=config.template_params or {},
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
            logger.debug("  → Using video-based composition with HTML overlay")
            
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
            logger.debug("  → Using image-based composition")
            
            segment_path = video_service.create_video_from_image(
                image=frame.composed_image_path,
                audio=frame.audio_path,
                output=output_path,
                fps=_get_image_segment_fps(config.video_fps)
            )
        
        else:
            raise ValueError(f"Unknown media type: {frame.media_type}")
        
        frame.video_segment_path = segment_path
        
        logger.debug(f"  ✓ Video segment created: {segment_path}")
    
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
        
        timeout = httpx.Timeout(connect=10.0, read=60, write=60, pool=60)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
        
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
