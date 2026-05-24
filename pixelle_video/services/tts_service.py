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
TTS (Text-to-Speech) Service - Supports both local and ComfyUI inference
"""

import shutil
import uuid
from pathlib import Path
from typing import Optional

from loguru import logger

from pixelle_video.config.tts_defaults import resolve_tts_inference_mode
from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.tts_trace_artifacts import (
    write_tts_service_result_artifact,
    write_tts_workflow_result_artifact,
    write_tts_workflow_trace_context,
)
from pixelle_video.tts_voices import speed_to_rate
from pixelle_video.tts_workflow_contract import (
    build_ref_audio_text_params,
    get_missing_required_tts_workflow_params,
    get_tts_workflow_metadata,
)
from pixelle_video.tts_workflow_param_contract import (
    reject_case_variant_tts_workflow_params,
)
from pixelle_video.utils.os_util import get_output_path
from pixelle_video.utils.tts_util import edge_tts


def _tts_trace_output_dir(output_path: Optional[str]) -> Path:
    if output_path:
        return Path(output_path).parent
    return Path(get_output_path())


def _summarize_tts_workflow_result(result) -> dict[str, object]:
    return {
        "status": str(getattr(result, "status", "")),
        "msg": str(getattr(result, "msg", "") or ""),
        "audios": [str(value) for value in getattr(result, "audios", []) or []],
        "files": [str(value) for value in getattr(result, "files", []) or []],
        "outputs": {
            str(key): str(value)
            for key, value in (getattr(result, "outputs", {}) or {}).items()
        },
    }


class TTSService(ComfyBaseService):
    """
    TTS (Text-to-Speech) service - Workflow-based
    
    Uses ComfyKit to execute TTS workflows.
    
    Usage:
        # Use default workflow
        audio_path = await pixelle_video.tts(text="Hello, world!")
        
        # Use specific workflow
        audio_path = await pixelle_video.tts(
            text="你好，世界！",
            workflow="tts_edge.json"
        )
        
        # List available workflows
        workflows = pixelle_video.tts.list_workflows()
    """
    
    WORKFLOW_PREFIX = "tts_"
    DEFAULT_WORKFLOW = None  # No hardcoded default, must be configured
    WORKFLOWS_DIR = "workflows"
    
    def __init__(self, config: dict, core=None):
        """
        Initialize TTS service
        
        Args:
            config: Full application config dict
            core: PixelleVideoCore instance (for accessing shared ComfyKit)
        """
        super().__init__(config, service_name="tts", core=core)
    
    
    async def __call__(
        self,
        text: str,
        workflow: Optional[str] = None,
        # ComfyUI connection (optional overrides)
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        # TTS parameters
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        # Inference mode override
        inference_mode: Optional[str] = None,
        # Output path
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using local Edge TTS or ComfyUI workflow
        
        Args:
            text: Text to convert to speech
            workflow: Workflow filename (for ComfyUI mode, default: from config)
            comfyui_url: ComfyUI URL (optional, overrides config)
            runninghub_api_key: RunningHub API key (optional, overrides config)
            voice: Voice ID (for local mode: Edge TTS voice ID; for ComfyUI: workflow-specific)
            speed: Speech speed multiplier (1.0 = normal, >1.0 = faster, <1.0 = slower)
            inference_mode: Override inference mode ("local" or "comfyui", default: from config)
            output_path: Custom output path (auto-generated if None)
            **params: Additional workflow parameters
        
        Returns:
            Generated audio file path
        
        Examples:
            # Local inference (Edge TTS)
            audio_path = await pixelle_video.tts(
                text="Hello, world!",
                inference_mode="local",
                voice="zh-CN-YunjianNeural",
                speed=1.2
            )
            
            # ComfyUI inference
            audio_path = await pixelle_video.tts(
                text="你好，世界！",
                inference_mode="comfyui",
                workflow="runninghub/tts_edge.json"
            )
        """
        # Determine inference mode (param > config)
        mode = resolve_tts_inference_mode({"comfyui": {"tts": self.config}}, inference_mode)
        
        # Route to appropriate implementation
        if mode == "local":
            return await self._call_local_tts(
                text=text,
                voice=voice,
                speed=speed,
                output_path=output_path
            )
        else:  # comfyui
            # 1. Resolve workflow (returns structured info)
            workflow_info = self._resolve_workflow(workflow=workflow)
            backend_role = "default"
            registry = self._get_backend_registry()
            if workflow_info["source"] == "selfhost" and registry is not None:
                backend_role = registry.resolve_role_for_tts(
                    workflow_info["key"],
                )
            
            # 2. Execute ComfyUI workflow
            return await self._call_comfyui_workflow(
                workflow_info=workflow_info,
                text=text,
                backend_role=backend_role,
                comfyui_url=comfyui_url,
                runninghub_api_key=runninghub_api_key,
                voice=voice,
                speed=speed,
                output_path=output_path,
                **params
            )
    
    async def _call_local_tts(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate speech using local Edge TTS
        
        Args:
            text: Text to convert to speech
            voice: Edge TTS voice ID (default: from config)
            speed: Speech speed multiplier (default: from config)
            output_path: Custom output path (auto-generated if None)
        
        Returns:
            Generated audio file path
        """
        # Get config defaults
        local_config = self.config.get("local", {})
        
        # Determine voice and speed (param > config)
        final_voice = voice or local_config.get("voice", "zh-CN-YunjianNeural")
        final_speed = speed if speed is not None else local_config.get("speed", 1.2)
        
        # Convert speed to rate parameter
        rate = speed_to_rate(final_speed)
        
        logger.info(f"🎙️  Using local Edge TTS: voice={final_voice}, speed={final_speed}x (rate={rate})")
        
        # Generate output path if not provided
        if not output_path:
            # Generate unique filename
            unique_id = uuid.uuid4().hex
            output_path = get_output_path(f"{unique_id}.mp3")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        workflow_params = {
            "text": text,
            "voice": final_voice,
            "speed": final_speed,
            "rate": rate,
            "output_path": output_path,
        }
        trace_context = write_tts_workflow_trace_context(
            Path(output_path).parent,
            task_id=None,
            text=text,
            workflow="local_edge_tts",
            workflow_input="local_edge_tts",
            source="tts.local_edge_tts",
            workflow_params=workflow_params,
        )
        
        # Call Edge TTS
        try:
            await edge_tts(
                text=text,
                voice=final_voice,
                rate=rate,
                output_path=output_path
            )
            
            logger.info(f"✅ Generated audio (local Edge TTS): {output_path}")
            write_tts_workflow_result_artifact(
                trace_context,
                status="completed",
                result={"output_path": output_path},
            )
            return output_path
        
        except Exception as e:
            write_tts_workflow_result_artifact(
                trace_context,
                status="error",
                result={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "output_path": output_path,
                },
            )
            logger.error(f"Local TTS generation error: {e}")
            raise
    
    async def _call_comfyui_workflow(
        self,
        workflow_info: dict,
        text: str,
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
        output_path: Optional[str] = None,
        backend_role: str = "default",
        **params
    ) -> str:
        """
        Generate speech using ComfyUI workflow
        
        Args:
            workflow_info: Workflow info dict from _resolve_workflow()
            text: Text to convert to speech
            comfyui_url: ComfyUI URL
            runninghub_api_key: RunningHub API key
            voice: Voice ID (workflow-specific)
            speed: Speech speed multiplier (workflow-specific)
            output_path: Custom output path (downloads if URL returned)
            **params: Additional workflow parameters
        
        Returns:
            Generated audio file path (local if output_path provided, otherwise URL)
        """
        logger.info(f"🎙️  Using workflow: {workflow_info['key']}")
        
        # 1. Build workflow parameters (ComfyKit config is now managed by core)
        reject_case_variant_tts_workflow_params(params)
        workflow_params = {"text": text}
        ref_audio_text = params.pop("reference_audio_text", None)
        if ref_audio_text is None:
            ref_audio_text = params.pop("ref_audio_text", None)
        if ref_audio_text is None:
            ref_audio_text = params.pop("prompt_text", None)
        else:
            params.pop("ref_audio_text", None)
            params.pop("prompt_text", None)
        
        # Add optional TTS parameters (only if explicitly provided and not None)
        if voice is not None:
            workflow_params["voice"] = voice
        if speed is not None and speed != 1.0:
            workflow_params["speed"] = speed
        
        # Add any additional parameters
        workflow_params.update(params)
        for key, value in build_ref_audio_text_params(
            ref_audio_text,
            self._get_workflow_param_names(workflow_info),
        ).items():
            workflow_params.setdefault(key, value)

        self._validate_required_workflow_params(workflow_info, workflow_params)
        
        logger.debug(f"Workflow parameters: {workflow_params}")
        if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
            # RunningHub: pass workflow_id
            workflow_input = workflow_info["workflow_id"]
            logger.info(f"Executing RunningHub TTS workflow: {workflow_input}")
        else:
            # Selfhost: pass file path
            workflow_input = workflow_info["path"]
            logger.info(f"Executing selfhost TTS workflow: {workflow_input}")
        trace_context = write_tts_workflow_trace_context(
            _tts_trace_output_dir(output_path),
            task_id=None,
            text=text,
            workflow=str(workflow_info["key"]),
            workflow_input=str(workflow_input),
            source=f"tts.{workflow_info['source']}",
            workflow_params=workflow_params,
        )
        result = None
        audio_path = None
        
        # 3. Execute workflow using shared ComfyKit instance from core
        try:
            result = await self._execute_workflow(
                workflow_input,
                workflow_params,
                workflow_info,
                backend_role=backend_role,
                tts_workflow_trace_context=trace_context,
            )
            
            # 4. Handle result
            if result.status != "completed":
                error_msg = result.msg or "Unknown error"
                logger.error(f"TTS generation failed: {error_msg}")
                raise Exception(
                    f"TTS workflow '{workflow_info['key']}' failed: {error_msg}"
                )
            
            # ComfyKit result can have audio files in different output types
            # Try to get audio file path from result
            # Check for audio files in result.audios (if available)
            if hasattr(result, 'audios') and result.audios:
                audio_path = result.audios[0]
                logger.debug(f"✅ Found audio in result.audios: {audio_path}")
            # Check for files in result.files
            elif hasattr(result, 'files') and result.files:
                audio_path = result.files[0]
                logger.debug(f"✅ Found audio in result.files: {audio_path}")
            # Check in outputs dictionary
            elif hasattr(result, 'outputs') and result.outputs:
                logger.debug(f"Searching for audio file in result.outputs: {result.outputs}")
                # Try to find audio file in outputs
                for key, value in result.outputs.items():
                    if isinstance(value, str) and any(
                        value.endswith(ext) for ext in [".mp3", ".wav", ".flac", ".opus"]
                    ):
                        audio_path = value
                        logger.debug(f"✅ Found audio in result.outputs[{key}]: {audio_path}")
                        break
            
            if not audio_path:
                logger.error("No audio file generated")
                logger.error("❌ Result analysis:")
                logger.error(f"   - result.audios: {getattr(result, 'audios', 'NOT_FOUND')}")
                logger.error(f"   - result.files: {getattr(result, 'files', 'NOT_FOUND')}")
                logger.error(f"   - result.outputs: {getattr(result, 'outputs', 'NOT_FOUND')}")
                logger.error(f"   - Full __dict__: {result.__dict__}")
                raise Exception("No audio file generated by workflow")
            
            materialized_path = await self._materialize_audio_result(
                audio_path=str(audio_path),
                output_path=output_path,
            )
            logger.info(f"✅ Generated audio (ComfyUI): {materialized_path}")
            result_summary = _summarize_tts_workflow_result(result)
            result_summary["audio_path"] = str(audio_path)
            result_summary["materialized_path"] = str(materialized_path)
            write_tts_service_result_artifact(
                trace_context,
                status="completed",
                result=result_summary,
            )
            return materialized_path
        
        except Exception as e:
            if result is not None:
                service_result = _summarize_tts_workflow_result(result)
                if audio_path is not None:
                    service_result["audio_path"] = str(audio_path)
                service_result.update(
                    {
                        "error_type": type(e).__name__,
                        "error": str(e),
                    }
                )
                write_tts_service_result_artifact(
                    trace_context,
                    status=(
                        "error"
                        if str(getattr(result, "status", "")) == "completed"
                        else "failed"
                    ),
                    result=service_result,
                )
            logger.error(f"TTS generation error: {e}")
            raise

    async def _materialize_audio_result(
        self,
        *,
        audio_path: str,
        output_path: Optional[str],
    ) -> str:
        if not output_path:
            return audio_path

        target_path = Path(output_path)
        if audio_path.startswith(("http://", "https://")):
            import httpx

            target_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Downloading audio from {audio_path} to {target_path}")
            async with httpx.AsyncClient() as client:
                response = await client.get(audio_path)
                response.raise_for_status()
                target_path.write_bytes(response.content)
            return str(target_path)

        source_path = Path(audio_path)
        if source_path.resolve() == target_path.resolve():
            return str(target_path)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        return str(target_path)

    def _get_workflow_metadata(self, workflow_info: dict):
        return get_tts_workflow_metadata(workflow_info.get("path"))

    def _validate_required_workflow_params(
        self,
        workflow_info: dict,
        workflow_params: dict[str, object],
    ) -> None:
        missing_required_params = get_missing_required_tts_workflow_params(
            workflow_info.get("path"),
            workflow_params,
        )
        if missing_required_params:
            missing_params = ", ".join(missing_required_params)
            raise ValueError(
                f"TTS workflow '{workflow_info['key']}' missing required params: {missing_params}"
            )

    def _get_workflow_param_names(self, workflow_info: dict) -> set[str]:
        metadata = self._get_workflow_metadata(workflow_info)
        if metadata is None:
            return set()
        return set(metadata.params.keys())
