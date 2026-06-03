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
Persistence Service

Handles task metadata and storyboard persistence to filesystem.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger

from pixelle_video.config.tts_defaults import resolve_tts_inference_mode
from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_ORIENTATION,
    DEFAULT_MEDIA_RESOLUTION_PRESET,
    DEFAULT_VIDEO_ORIENTATION,
    DEFAULT_VIDEO_RESOLUTION_PRESET,
)
from pixelle_video.models.storyboard import (
    ContentMetadata,
    Storyboard,
    StoryboardConfig,
    StoryboardFrame,
)
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.render_backend import (
    DEFAULT_RENDER_BACKEND,
    HYPERFRAMES_COMPILED_RENDER_BACKEND,
)
from pixelle_video.utils.json_safety import to_json_compatible
from pixelle_video.utils.template_util import DEFAULT_IMAGE_TEMPLATE


class PersistenceService:
    """
    Task persistence service using filesystem (JSON)
    
    File structure:
        output/
        └── {task_id}/
            ├── metadata.json          # Task metadata (input, result, config)
            ├── storyboard.json        # Storyboard data (frames, prompts)
            ├── final.mp4
            └── frames/
                ├── 01_audio.mp3
                ├── 01_image.png
                └── ...
    
    Usage:
        persistence = PersistenceService()
        
        # Save metadata
        await persistence.save_task_metadata(task_id, metadata)
        
        # Save storyboard
        await persistence.save_storyboard(task_id, storyboard)
        
        # Load task
        metadata = await persistence.load_task_metadata(task_id)
        storyboard = await persistence.load_storyboard(task_id)
        
        # List all tasks
        tasks = await persistence.list_tasks(status="completed", limit=50)
    """
    
    def __init__(self, output_dir: str = "output"):
        """
        Initialize persistence service
        
        Args:
            output_dir: Base output directory (default: "output")
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Index file for fast listing
        self.index_file = self.output_dir / ".index.json"
        self._ensure_index()
    
    def get_task_dir(self, task_id: str) -> Path:
        """Get task directory path"""
        return self.output_dir / task_id
    
    def get_metadata_path(self, task_id: str) -> Path:
        """Get metadata.json path"""
        return self.get_task_dir(task_id) / "metadata.json"
    
    def get_storyboard_path(self, task_id: str) -> Path:
        """Get storyboard.json path"""
        return self.get_task_dir(task_id) / "storyboard.json"

    def get_task_logs_dir(self, task_id: str) -> Path:
        """Get task logs directory path"""
        return self.get_task_dir(task_id) / "logs"

    def get_task_runtime_log_path(self, task_id: str) -> Path:
        """Get task runtime log path"""
        return self.get_task_logs_dir(task_id) / "runtime.jsonl"

    def get_task_ai_creation_log_path(self, task_id: str) -> Path:
        """Get task AI creation log path"""
        return self.get_task_logs_dir(task_id) / "ai_creation.jsonl"
    
    # ========================================================================
    # Metadata Operations
    # ========================================================================
    
    async def save_task_metadata(
        self,
        task_id: str,
        metadata: Dict[str, Any]
    ):
        """
        Save task metadata to filesystem
        
        Args:
            task_id: Task ID
            metadata: Metadata dict with structure:
                {
                    "task_id": str,
                    "created_at": str,
                    "completed_at": str (optional),
                    "status": str,
                    "input": dict,
                    "result": dict (optional),
                    "config": dict
                }
        """
        try:
            task_dir = self.get_task_dir(task_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            
            metadata_path = self.get_metadata_path(task_id)
            
            # Ensure task_id is set
            metadata["task_id"] = task_id
            
            # Convert datetime objects to ISO format strings
            if "created_at" in metadata and isinstance(metadata["created_at"], datetime):
                metadata["created_at"] = metadata["created_at"].isoformat()
            if "completed_at" in metadata and isinstance(metadata["completed_at"], datetime):
                metadata["completed_at"] = metadata["completed_at"].isoformat()
            
            self._write_json_atomic(metadata_path, metadata)
            
            logger.debug(f"Saved task metadata: {task_id}")
            
            # Update index
            await self._update_index_for_task(task_id, metadata)
            
        except Exception as e:
            logger.error(f"Failed to save task metadata {task_id}: {e}")
            raise
    
    async def load_task_metadata(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Load task metadata from filesystem
        
        Args:
            task_id: Task ID
            
        Returns:
            Metadata dict or None if not found
        """
        try:
            metadata_path = self.get_metadata_path(task_id)
            
            if not metadata_path.exists():
                return None
            
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to load task metadata {task_id}: {e}")
            return None
    
    async def update_task_status(
        self,
        task_id: str,
        status: str,
        error: Optional[str] = None
    ):
        """
        Update task status in metadata
        
        Args:
            task_id: Task ID
            status: New status (pending, running, completed, failed, cancelled)
            error: Error message (optional, for failed status)
        """
        try:
            metadata = await self.load_task_metadata(task_id)
            if not metadata:
                logger.warning(f"Cannot update status: task {task_id} not found")
                return
            
            metadata["status"] = status
            
            if status in ["completed", "failed", "cancelled"]:
                metadata["completed_at"] = datetime.now().isoformat()
            
            if error:
                metadata["error"] = error
            
            await self.save_task_metadata(task_id, metadata)
            
        except Exception as e:
            logger.error(f"Failed to update task status {task_id}: {e}")
    
    # ========================================================================
    # Storyboard Operations
    # ========================================================================
    
    async def save_storyboard(
        self,
        task_id: str,
        storyboard: Storyboard
    ):
        """
        Save storyboard to filesystem
        
        Args:
            task_id: Task ID
            storyboard: Storyboard instance
        """
        try:
            task_dir = self.get_task_dir(task_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            
            storyboard_path = self.get_storyboard_path(task_id)
            
            # Convert storyboard to dict
            storyboard_dict = self._storyboard_to_dict(storyboard)
            
            self._write_json_atomic(storyboard_path, storyboard_dict)
            
            logger.debug(f"Saved storyboard: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to save storyboard {task_id}: {e}")
            raise
    
    async def load_storyboard(self, task_id: str) -> Optional[Storyboard]:
        """
        Load storyboard from filesystem
        
        Args:
            task_id: Task ID
            
        Returns:
            Storyboard instance or None if not found
        """
        try:
            storyboard_path = self.get_storyboard_path(task_id)
            
            if not storyboard_path.exists():
                return None
            
            with open(storyboard_path, "r", encoding="utf-8") as f:
                storyboard_dict = json.load(f)
            
            # Convert dict to storyboard
            storyboard = self._dict_to_storyboard(storyboard_dict)
            
            return storyboard
            
        except Exception as e:
            logger.error(f"Failed to load storyboard {task_id}: {e}")
            return None
    
    # ========================================================================
    # Task Listing & Querying
    # ========================================================================
    
    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List tasks with optional filtering
        
        Args:
            status: Filter by status (pending, running, completed, failed, cancelled)
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip
            
        Returns:
            List of metadata dicts, sorted by created_at descending
        """
        try:
            tasks = []
            
            # Scan all task directories
            for task_dir in self.output_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                
                metadata_path = task_dir / "metadata.json"
                if not metadata_path.exists():
                    continue
                
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    
                    # Filter by status
                    if status and metadata.get("status") != status:
                        continue
                    
                    tasks.append(metadata)
                    
                except Exception as e:
                    logger.warning(f"Failed to load metadata from {task_dir}: {e}")
                    continue
            
            # Sort by created_at descending
            tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
            
            # Apply pagination
            return tasks[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return []
    
    async def task_exists(self, task_id: str) -> bool:
        """Check if task exists"""
        return self.get_task_dir(task_id).exists()
    
    # ========================================================================
    # Serialization Helpers
    # ========================================================================
    
    def _storyboard_to_dict(self, storyboard: Storyboard) -> Dict[str, Any]:
        """Convert Storyboard to dict for JSON serialization"""
        return {
            "title": storyboard.title,
            "config": self._config_to_dict(storyboard.config),
            "frames": [self._frame_to_dict(frame) for frame in storyboard.frames],
            "content_metadata": self._content_metadata_to_dict(storyboard.content_metadata) if storyboard.content_metadata else None,
            "final_video_path": storyboard.final_video_path,
            "total_duration": storyboard.total_duration,
            "planning_snapshot": to_json_compatible(
                storyboard.planning_snapshot,
                field_name="storyboard.planning_snapshot",
            ),
            "created_at": storyboard.created_at.isoformat() if storyboard.created_at else None,
            "completed_at": storyboard.completed_at.isoformat() if storyboard.completed_at else None,
        }
    
    def _dict_to_storyboard(self, data: Dict[str, Any]) -> Storyboard:
        """Convert dict to Storyboard instance"""
        return Storyboard(
            title=data["title"],
            config=self._dict_to_config(data["config"]),
            frames=[self._dict_to_frame(frame_data) for frame_data in data["frames"]],
            content_metadata=self._dict_to_content_metadata(data["content_metadata"]) if data.get("content_metadata") else None,
            final_video_path=data.get("final_video_path"),
            total_duration=data.get("total_duration", 0.0),
            planning_snapshot=data.get("planning_snapshot"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )
    
    def _config_to_dict(self, config: StoryboardConfig) -> Dict[str, Any]:
        """Convert StoryboardConfig to dict"""
        data = {
            "task_id": config.task_id,
            "n_storyboard": config.n_storyboard,
            "min_narration_words": config.min_narration_words,
            "max_narration_words": config.max_narration_words,
            "min_image_prompt_words": config.min_image_prompt_words,
            "max_image_prompt_words": config.max_image_prompt_words,
            "video_fps": config.video_fps,
            "tts_inference_mode": config.tts_inference_mode,
            "voice_id": config.voice_id,
            "tts_workflow": config.tts_workflow,
            "tts_speed": config.tts_speed,
            "tts_duration": config.tts_duration,
            "ref_audio": config.ref_audio,
            "ref_audio_text": config.ref_audio_text,
            "tts_batching_mode": config.tts_batching_mode,
            "tts_audio_strategy": config.tts_audio_strategy,
            "tts_split_mode": config.tts_split_mode,
            "tts_batch_max_sentences": config.tts_batch_max_sentences,
            "tts_batch_max_chars": config.tts_batch_max_chars,
            "tts_sentence_joiner_mode": config.tts_sentence_joiner_mode,
            "caption_punctuation_mode": config.caption_punctuation_mode,
            "preserve_natural_punctuation": config.preserve_natural_punctuation,
            "max_chars_per_tts_segment": config.max_chars_per_tts_segment,
            "tts_split_overflow_policy": config.tts_split_overflow_policy,
            "tts_boundary_search_radius": config.tts_boundary_search_radius,
            "tts_soft_overflow_chars": config.tts_soft_overflow_chars,
            "tts_audio_boundary_fade_ms": config.tts_audio_boundary_fade_ms,
            "subtitle_alignment_engine": config.subtitle_alignment_engine,
            "silence_trim_tool": config.silence_trim_tool,
            "silence_trim_margin_ms": config.silence_trim_margin_ms,
            "render_backend": config.render_backend,
            "element_animation_enabled": config.element_animation_enabled,
            "element_animation_backend": config.element_animation_backend,
            "element_animation_subject_count": config.element_animation_subject_count,
            "element_animation_candidate_limit": config.element_animation_candidate_limit,
            "element_animation_prompt": config.element_animation_prompt,
            "element_animation_intensity": config.element_animation_intensity,
            "element_animation_workflow": config.element_animation_workflow,
            "canvas_width": config.canvas_width,
            "canvas_height": config.canvas_height,
            "media_width": config.media_width,
            "media_height": config.media_height,
            "video_orientation": config.video_orientation,
            "video_resolution_preset": config.video_resolution_preset,
            "media_orientation": config.media_orientation,
            "media_resolution_preset": config.media_resolution_preset,
            "sync_media_size_to_canvas": config.sync_media_size_to_canvas,
            "media_placement": config.media_placement.to_dict(),
            "media_workflow": config.media_workflow,
            "media_negative_prompt": config.media_negative_prompt,
            "frame_template": config.frame_template,
            "template_params": config.template_params,
            "template_display": config.template_display.to_dict(),
            "layered_template_spec": config.layered_template_spec,
            "selected_template_preset_id": config.selected_template_preset_id,
            "template_text_policy": config.template_text_policy,
            "world_preset_id": config.world_preset_id,
            "shot_preset_id": config.shot_preset_id,
            "storyboard_prompt_language": config.storyboard_prompt_language,
            "content_mode": config.content_mode,
            "consistency_strength": config.consistency_strength,
            "role_strategy": config.role_strategy,
            "role_locking_strength": config.role_locking_strength,
            "shot_strategy": config.shot_strategy,
        }
        if data["layered_template_spec"] is None:
            data.pop("layered_template_spec")
            data["selected_template_preset_id"] = None
        return data
    
    def _dict_to_config(self, data: Dict[str, Any]) -> StoryboardConfig:
        """Convert dict to StoryboardConfig"""
        return StoryboardConfig(
            task_id=data.get("task_id"),
            n_storyboard=data.get("n_storyboard", 5),
            min_narration_words=data.get("min_narration_words", 5),
            max_narration_words=data.get("max_narration_words", 20),
            min_image_prompt_words=data.get("min_image_prompt_words", 30),
            max_image_prompt_words=data.get("max_image_prompt_words", 60),
            video_fps=data.get("video_fps", 30),
            tts_inference_mode=resolve_tts_inference_mode(
                None,
                data.get("tts_inference_mode"),
            ),
            voice_id=data.get("voice_id"),
            tts_workflow=data.get("tts_workflow"),
            tts_speed=data.get("tts_speed"),
            tts_duration=data.get("tts_duration"),
            ref_audio=data.get("ref_audio"),
            ref_audio_text=data.get("ref_audio_text"),
            tts_batching_mode=data.get("tts_batching_mode", "paragraph"),
            tts_audio_strategy=data.get("tts_audio_strategy", "auto"),
            tts_split_mode=data.get("tts_split_mode", "internal_only"),
            tts_batch_max_sentences=data.get("tts_batch_max_sentences", 8),
            tts_batch_max_chars=data.get("tts_batch_max_chars", 220),
            tts_sentence_joiner_mode=data.get("tts_sentence_joiner_mode", "direct"),
            caption_punctuation_mode=data.get("caption_punctuation_mode", "strip_all"),
            preserve_natural_punctuation=data.get("preserve_natural_punctuation", True),
            max_chars_per_tts_segment=data.get("max_chars_per_tts_segment", 90),
            tts_split_overflow_policy=data.get("tts_split_overflow_policy", "hard_limit"),
            tts_boundary_search_radius=data.get("tts_boundary_search_radius", 20),
            tts_soft_overflow_chars=data.get("tts_soft_overflow_chars", 0),
            tts_audio_boundary_fade_ms=data.get("tts_audio_boundary_fade_ms", 8),
            subtitle_alignment_engine=data.get("subtitle_alignment_engine", "qwen_forced_aligner"),
            silence_trim_tool=data.get("silence_trim_tool"),
            silence_trim_margin_ms=data.get("silence_trim_margin_ms", 120),
            render_backend=self._normalize_persisted_render_backend(
                data.get("render_backend", DEFAULT_RENDER_BACKEND)
            ),
            element_animation_enabled=data.get("element_animation_enabled", False),
            element_animation_backend=data.get("element_animation_backend", "hyperframes_canvas"),
            element_animation_subject_count=data.get("element_animation_subject_count", 3),
            element_animation_candidate_limit=data.get("element_animation_candidate_limit", 3),
            element_animation_prompt=data.get("element_animation_prompt"),
            element_animation_intensity=data.get("element_animation_intensity", "medium"),
            element_animation_workflow=data.get("element_animation_workflow", "image_sam31_segment.json"),
            canvas_width=data.get("canvas_width"),
            canvas_height=data.get("canvas_height"),
            media_width=data.get("media_width", data.get("image_width", 1024)),  # Backward compatibility
            media_height=data.get("media_height", data.get("image_height", 1024)),  # Backward compatibility
            video_orientation=data.get("video_orientation", DEFAULT_VIDEO_ORIENTATION),
            video_resolution_preset=data.get(
                "video_resolution_preset",
                DEFAULT_VIDEO_RESOLUTION_PRESET,
            ),
            media_orientation=data.get("media_orientation", DEFAULT_MEDIA_ORIENTATION),
            media_resolution_preset=data.get(
                "media_resolution_preset",
                DEFAULT_MEDIA_RESOLUTION_PRESET,
            ),
            sync_media_size_to_canvas=data.get("sync_media_size_to_canvas", False),
            media_placement=data.get("media_placement"),
            media_workflow=data.get("media_workflow", data.get("image_workflow")),  # Backward compatibility
            media_negative_prompt=data.get("media_negative_prompt"),
            frame_template=data.get("frame_template", DEFAULT_IMAGE_TEMPLATE),
            template_params=data.get("template_params"),
            template_display=data.get("template_display"),
            layered_template_spec=data.get("layered_template_spec"),
            selected_template_preset_id=data.get("selected_template_preset_id"),
            template_text_policy=data.get("template_text_policy", "caption_renderer"),
            world_preset_id=data.get("world_preset_id"),
            shot_preset_id=data.get("shot_preset_id", data.get("effective_final_shot_preset")),
            storyboard_prompt_language=data.get("storyboard_prompt_language"),
            content_mode=data.get("content_mode", data.get("resolved_content_mode")),
            consistency_strength=data.get("consistency_strength", data.get("selected_consistency_strength")),
            role_strategy=data.get("role_strategy", data.get("resolved_role_strategy")),
            role_locking_strength=data.get("role_locking_strength", data.get("selected_role_locking_strength")),
            shot_strategy=data.get("shot_strategy", data.get("selected_shot_strategy")),
        )

    def _normalize_persisted_render_backend(self, render_backend: Any) -> str:
        """
        Keep historical storyboard.json files readable after backend enum tightening.

        This does not relax runtime config or API validation; it only handles already
        persisted task data written before `hyperframes_compiled` became the canonical
        name for the compiled HyperFrames path.
        """
        if render_backend == "hyperframes":
            return HYPERFRAMES_COMPILED_RENDER_BACKEND
        if not render_backend:
            return DEFAULT_RENDER_BACKEND
        return str(render_backend)
    
    def _frame_to_dict(self, frame: StoryboardFrame) -> Dict[str, Any]:
        """Convert StoryboardFrame to dict"""
        return {
            "index": frame.index,
            "narration": frame.narration,
            "image_prompt": frame.image_prompt,
            "audio_path": frame.audio_path,
            "media_type": frame.media_type,
            "image_path": frame.image_path,
            "video_path": frame.video_path,
            "composed_image_path": frame.composed_image_path,
            "template_visual_path": frame.template_visual_path,
            "element_animation_manifest_path": frame.element_animation_manifest_path,
            "element_motion_video_path": frame.element_motion_video_path,
            "video_segment_path": frame.video_segment_path,
            "duration": frame.duration,
            "shot_type": frame.shot_type,
            "shot_purpose": frame.shot_purpose,
            "frame_source": frame.frame_source,
            "workbench_state": frame.workbench_state.to_dict() if frame.workbench_state else None,
            "created_at": frame.created_at.isoformat() if frame.created_at else None,
        }
    
    def _dict_to_frame(self, data: Dict[str, Any]) -> StoryboardFrame:
        """Convert dict to StoryboardFrame"""
        return StoryboardFrame(
            index=data["index"],
            narration=data["narration"],
            image_prompt=data["image_prompt"],
            audio_path=data.get("audio_path"),
            media_type=data.get("media_type"),
            image_path=data.get("image_path"),
            video_path=data.get("video_path"),
            composed_image_path=data.get("composed_image_path"),
            template_visual_path=data.get("template_visual_path"),
            element_animation_manifest_path=data.get("element_animation_manifest_path"),
            element_motion_video_path=data.get("element_motion_video_path"),
            video_segment_path=data.get("video_segment_path"),
            duration=data.get("duration", 0.0),
            shot_type=data.get("shot_type"),
            shot_purpose=data.get("shot_purpose"),
            frame_source=data.get("frame_source"),
            workbench_state=(
                StoryboardFrameWorkbenchState.from_dict(data["workbench_state"])
                if data.get("workbench_state")
                else None
            ),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )
    
    def _content_metadata_to_dict(self, metadata: ContentMetadata) -> Dict[str, Any]:
        """Convert ContentMetadata to dict"""
        return {
            "title": metadata.title,
            "author": metadata.author,
            "subtitle": metadata.subtitle,
            "genre": metadata.genre,
            "summary": metadata.summary,
            "publication_year": metadata.publication_year,
            "cover_url": metadata.cover_url,
        }
    
    def _dict_to_content_metadata(self, data: Dict[str, Any]) -> ContentMetadata:
        """Convert dict to ContentMetadata"""
        return ContentMetadata(
            title=data["title"],
            author=data.get("author"),
            subtitle=data.get("subtitle"),
            genre=data.get("genre"),
            summary=data.get("summary"),
            publication_year=data.get("publication_year"),
            cover_url=data.get("cover_url"),
        )
    
    # ========================================================================
    # Index Management (for fast listing)
    # ========================================================================
    
    def _ensure_index(self):
        """Ensure index file exists, create if not"""
        if not self.index_file.exists():
            self._save_index({"version": "1.0", "tasks": []})

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        """Write JSON only after serialization succeeds, then atomically replace."""
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(path)
            self._fsync_directory(path.parent)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        try:
            dir_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            try:
                os.fsync(dir_fd)
            except OSError:
                return
        finally:
            os.close(dir_fd)
    
    def _load_index(self) -> Dict[str, Any]:
        """Load index from file"""
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return {"version": "1.0", "tasks": []}
    
    def _save_index(self, index_data: Dict[str, Any]):
        """Save index to file"""
        try:
            index_data["last_updated"] = datetime.now().isoformat()
            self._write_json_atomic(self.index_file, index_data)
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
    
    async def _update_index_for_task(self, task_id: str, metadata: Dict[str, Any]):
        """Update index entry for a specific task"""
        index = self._load_index()
        
        # Try to get title from multiple sources
        title = metadata.get("input", {}).get("title")
        if not title or title == "":
            # Try to get title from storyboard if input title is empty
            storyboard = await self.load_storyboard(task_id)
            if storyboard and storyboard.title:
                title = storyboard.title
            else:
                # Fall back to using input text preview
                input_text = metadata.get("input", {}).get("text", "")
                if input_text:
                    # Use first 30 characters of input text as title
                    title = input_text[:30] + ("..." if len(input_text) > 30 else "")
                else:
                    title = "Untitled"
        
        # Extract key info for index
        index_entry = {
            "task_id": task_id,
            "created_at": metadata.get("created_at"),
            "completed_at": metadata.get("completed_at"),
            "status": metadata.get("status", "unknown"),
            "title": title,
            "duration": metadata.get("result", {}).get("duration", 0),
            "n_frames": metadata.get("result", {}).get("n_frames", 0),
            "file_size": metadata.get("result", {}).get("file_size", 0),
            "video_path": metadata.get("result", {}).get("video_path"),
        }
        
        # Update or append
        tasks = index.get("tasks", [])
        existing_idx = next((i for i, t in enumerate(tasks) if t["task_id"] == task_id), None)
        
        if existing_idx is not None:
            tasks[existing_idx] = index_entry
        else:
            tasks.append(index_entry)
        
        index["tasks"] = tasks
        self._save_index(index)
    
    async def rebuild_index(self):
        """Rebuild index by scanning all task directories"""
        logger.info("Rebuilding task index...")
        index = {"version": "1.0", "tasks": []}
        
        # Scan all directories
        for task_dir in self.output_dir.iterdir():
            if not task_dir.is_dir() or task_dir.name.startswith("."):
                continue
            
            task_id = task_dir.name
            metadata = await self.load_task_metadata(task_id)
            
            if metadata:
                # Try to get title from multiple sources
                title = metadata.get("input", {}).get("title")
                if not title or title == "":
                    # Try to get title from storyboard if input title is empty
                    storyboard = await self.load_storyboard(task_id)
                    if storyboard and storyboard.title:
                        title = storyboard.title
                    else:
                        # Fall back to using input text preview
                        input_text = metadata.get("input", {}).get("text", "")
                        if input_text:
                            # Use first 30 characters of input text as title
                            title = input_text[:30] + ("..." if len(input_text) > 30 else "")
                        else:
                            title = "Untitled"
                
                # Add to index
                index["tasks"].append({
                    "task_id": task_id,
                    "created_at": metadata.get("created_at"),
                    "completed_at": metadata.get("completed_at"),
                    "status": metadata.get("status", "unknown"),
                    "title": title,
                    "duration": metadata.get("result", {}).get("duration", 0),
                    "n_frames": metadata.get("result", {}).get("n_frames", 0),
                    "file_size": metadata.get("result", {}).get("file_size", 0),
                    "video_path": metadata.get("result", {}).get("video_path"),
                })
        
        self._save_index(index)
        logger.info(f"Index rebuilt: {len(index['tasks'])} tasks")
    
    # ========================================================================
    # Paginated Listing
    # ========================================================================
    
    async def list_tasks_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        List tasks with pagination
        
        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            status: Filter by status (optional)
            sort_by: Sort field (created_at, completed_at, title, duration)
            sort_order: Sort order (asc, desc)
        
        Returns:
            {
                "tasks": [...],          # List of task summaries
                "total": 100,            # Total matching tasks
                "page": 1,               # Current page
                "page_size": 20,         # Items per page
                "total_pages": 5         # Total pages
            }
        """
        index = self._load_index()
        tasks = index.get("tasks", [])
        
        # Filter by status
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        
        # Sort
        reverse = (sort_order == "desc")
        if sort_by in ["created_at", "completed_at"]:
            tasks.sort(
                key=lambda t: datetime.fromisoformat(t.get(sort_by, "1970-01-01T00:00:00")),
                reverse=reverse
            )
        elif sort_by in ["title", "duration", "n_frames"]:
            tasks.sort(key=lambda t: t.get(sort_by, ""), reverse=reverse)
        
        # Paginate
        total = len(tasks)
        total_pages = (total + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_tasks = tasks[start_idx:end_idx]
        
        return {
            "tasks": page_tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    
    # ========================================================================
    # Statistics
    # ========================================================================
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about all tasks
        
        Returns:
            {
                "total_tasks": 100,
                "completed": 95,
                "failed": 5,
                "total_duration": 3600.5,  # seconds
                "total_size": 1024000000,  # bytes
            }
        """
        index = self._load_index()
        tasks = index.get("tasks", [])
        
        stats = {
            "total_tasks": len(tasks),
            "completed": len([t for t in tasks if t.get("status") == "completed"]),
            "failed": len([t for t in tasks if t.get("status") == "failed"]),
            "total_duration": sum(t.get("duration", 0) for t in tasks),
            "total_size": sum(t.get("file_size", 0) for t in tasks),
        }
        
        return stats
    
    # ========================================================================
    # Delete Task
    # ========================================================================
    
    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task and all its files
        
        Args:
            task_id: Task ID to delete
        
        Returns:
            True if successful, False otherwise
        """
        try:
            import shutil
            
            task_dir = self.get_task_dir(task_id)
            if task_dir.exists():
                shutil.rmtree(task_dir)
                logger.info(f"Deleted task directory: {task_dir}")
            
            # Update index
            index = self._load_index()
            tasks = index.get("tasks", [])
            tasks = [t for t in tasks if t["task_id"] != task_id]
            index["tasks"] = tasks
            self._save_index(index)
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return False
