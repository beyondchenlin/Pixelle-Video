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
ComfyUI Base Service - Common logic for ComfyUI-based services
"""

import inspect
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from loguru import logger

from pixelle_video.config.workflow_defaults import (
    filter_workflow_keys_for_domain,
    get_configured_default_workflow,
    is_workflow_compatible,
    resolve_default_workflow,
)
from pixelle_video.runninghub_workflow_contracts import (
    ANALYSIS_WORKFLOW_DOMAINS,
    MEDIA_WORKFLOW_DOMAINS,
    RUNNINGHUB_SOURCE,
    runninghub_registry_root,
    validate_runninghub_descriptor_contract,
)
from pixelle_video.utils.os_util import get_resource_path, list_resource_dirs, list_resource_files
from pixelle_video.workflow_content_contracts import (
    build_workflow_file_trace,
    workflow_content_contract,
)

_WORKFLOW_METADATA_DOMAIN_KEYS = ("media_type", "workflow_domain", "service_domain")


def _callable_accepts_keyword(callable_obj, keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        or parameter.name == keyword
        for parameter in signature.parameters.values()
    )


def _workflow_info_declared_domains(workflow_info: Dict[str, Any]) -> set[str]:
    media_type = str(workflow_info.get("media_type") or "").strip().lower()
    if media_type in MEDIA_WORKFLOW_DOMAINS:
        return {media_type}
    return {
        str(workflow_info.get(key) or "").strip().lower()
        for key in _WORKFLOW_METADATA_DOMAIN_KEYS
        if str(workflow_info.get(key) or "").strip()
    }


def _workflow_info_is_compatible(
    workflow_info: Dict[str, Any],
    workflow_domain: Optional[str],
) -> bool:
    domain = str(workflow_domain or "").strip().lower()
    if not domain:
        return True
    media_type = str(workflow_info.get("media_type") or "").strip().lower()
    if domain in MEDIA_WORKFLOW_DOMAINS and media_type in MEDIA_WORKFLOW_DOMAINS:
        return domain == media_type
    declared_domains = _workflow_info_declared_domains(workflow_info)
    if domain in declared_domains:
        return True
    return is_workflow_compatible(str(workflow_info.get("key") or ""), domain)


def _filter_workflow_infos_for_domain(
    workflow_domain: Optional[str],
    workflow_infos: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        workflow_info
        for workflow_info in workflow_infos
        if _workflow_info_is_compatible(workflow_info, workflow_domain)
    ]


class ComfyBaseService:
    """
    Base service for ComfyUI workflow-based capabilities
    
    Provides common functionality for TTS, Image, and other ComfyUI-based services.
    
    Subclasses should define:
    - WORKFLOW_PREFIX: Prefix for workflow files (e.g., "image_", "tts_")
    - DEFAULT_WORKFLOW: Default workflow filename (e.g., "image_flux.json")
    - WORKFLOWS_DIR: Directory containing workflows (default: "workflows")
    """
    
    WORKFLOW_PREFIX: str = ""  # Must be overridden by subclass
    DEFAULT_WORKFLOW: str = ""  # Must be overridden by subclass
    WORKFLOWS_DIR: str = "workflows"
    
    def __init__(self, config: dict, service_name: str, core=None):
        """
        Initialize ComfyUI base service
        
        Args:
            config: Full application config dict
            service_name: Service name in config (e.g., "tts", "image")
            core: PixelleVideoCore instance (for accessing shared ComfyKit)
        """
        # Service-specific config (e.g., config["comfyui"]["tts"])
        comfyui_config = config.get("comfyui", {})
        self.config = comfyui_config.get(service_name, {})
        
        # Global ComfyUI config (for comfyui_url and runninghub_api_key)
        self.global_config = comfyui_config
        
        self.service_name = service_name
        self._workflows_cache: Optional[List[str]] = None
        
        # Reference to core (for accessing shared ComfyKit)
        self.core = core
    
    def _scan_workflows(self) -> List[Dict[str, Any]]:
        """
        Scan workflows/source/*.json files from all source directories (merged from workflows/ and data/workflows/)
        
        Returns:
            List of workflow info dicts
            Example: [
                {
                    "name": "image_flux.json",
                    "display_name": "image_flux.json - Selfhost",
                    "source": "selfhost",
                    "path": "workflows/selfhost/image_flux.json",
                    "key": "selfhost/image_flux.json"
                },
                {
                    "name": "image_flux.json",
                    "display_name": "image_flux.json - Runninghub", 
                    "source": "runninghub",
                    "path": "workflows/runninghub/image_flux.json",
                    "key": "runninghub/image_flux.json",
                    "workflow_id": "123456"
                }
            ]
        """
        workflows = []
        
        # Get all workflow source directories (merged from workflows/ and data/workflows/)
        source_dirs = list_resource_dirs("workflows")
        
        if not source_dirs:
            logger.warning("No workflow source directories found")
            return workflows
        
        # Scan each source directory for workflow files
        for source_name in source_dirs:
            workflow_paths = self._workflow_file_paths_for_source(source_name)

            for file_path in workflow_paths:
                filename = file_path.name
                if not filename.endswith('.json'):
                    continue
                matches_prefix = filename.startswith(self.WORKFLOW_PREFIX)
                try:
                    workflow_info = self._parse_workflow_file(file_path, source_name)
                    if source_name == RUNNINGHUB_SOURCE and self.service_name == "tts":
                        if "tts" not in _workflow_info_declared_domains(workflow_info):
                            continue
                    elif (
                        source_name == RUNNINGHUB_SOURCE
                        and self.service_name.endswith("_analysis")
                    ):
                        if workflow_info.get("service_domain") != self.service_name:
                            continue
                    elif not matches_prefix:
                        continue
                    workflows.append(workflow_info)
                    logger.debug(f"Found workflow: {workflow_info['key']}")
                except Exception as e:
                    logger.error(f"Failed to parse workflow {source_name}/{filename}: {e}")
        
        # Sort by key (source/name)
        return sorted(workflows, key=lambda w: w["key"])

    def _workflow_file_paths_for_source(self, source_name: str) -> list[Path]:
        if str(source_name).strip().lower() == RUNNINGHUB_SOURCE:
            registry_root = runninghub_registry_root()
            if not registry_root.is_dir():
                return []
            return sorted(
                path
                for path in registry_root.iterdir()
                if path.is_file() and path.suffix.lower() == ".json"
            )

        return [
            Path(get_resource_path("workflows", source_name, filename))
            for filename in list_resource_files("workflows", source_name)
        ]
    
    def _parse_workflow_file(self, file_path: Path, source: str) -> Dict[str, Any]:
        """
        Parse workflow file and extract metadata
        
        Args:
            file_path: Path to workflow JSON file
            source: Source directory name (e.g., "selfhost", "runninghub")
        
        Returns:
            Workflow info dict with structure:
            {
                "name": "image_flux.json",
                "display_name": "image_flux.json - Runninghub",
                "source": "runninghub",
                "path": "workflows/runninghub/image_flux.json",
                "key": "runninghub/image_flux.json",
                "workflow_id": "123456"  # Only for RunningHub
            }
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # Build base info
        workflow_info = {
            "name": file_path.name,
            "display_name": f"{file_path.name} - {source.title()}",
            "source": source,
            "path": str(file_path),
            "key": f"{source}/{file_path.name}",
            "service_domain": self.service_name,
        }
        
        # Check if it's a wrapper format (RunningHub, etc.)
        if "source" in content:
            # Wrapper format: {"source": "runninghub", "workflow_id": "xxx", ...}
            if str(content.get("source") or source).strip().lower() == RUNNINGHUB_SOURCE:
                content = validate_runninghub_descriptor_contract(file_path, content)
                workflow_info.pop("service_domain", None)
            if "workflow_id" in content:
                workflow_info["workflow_id"] = content["workflow_id"]
            for metadata_key in ("media_type", "workflow_domain", "service_domain"):
                value = content.get(metadata_key)
                if isinstance(value, str) and value.strip():
                    workflow_info[metadata_key] = value.strip().lower()
            declared_domains = _workflow_info_declared_domains(workflow_info)
            if declared_domains.intersection(ANALYSIS_WORKFLOW_DOMAINS):
                if workflow_info.get("workflow_domain") not in {
                    "image_analysis",
                    "video_analysis",
                }:
                    raise ValueError(
                        f"RunningHub analysis workflow requires explicit workflow_domain: {file_path}"
                    )
                if workflow_info.get("service_domain") not in {
                    "image_analysis",
                    "video_analysis",
                }:
                    raise ValueError(
                        f"RunningHub analysis workflow requires explicit service_domain: {file_path}"
                    )
                if workflow_info.get("workflow_domain") != workflow_info.get(
                    "service_domain"
                ):
                    raise ValueError(
                        f"RunningHub analysis workflow domain metadata does not match: {file_path}"
                    )
        elif source == "selfhost":
            workflow_info["workflow_content_contract"] = workflow_content_contract(content)
        
        return workflow_info
    
    def _get_default_workflow(
        self,
        workflow_domain: Optional[str] = None,
        available_keys: Optional[List[str]] = None,
        available_workflows: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Get the effective default workflow for a domain.
        
        Returns:
            Default workflow key (e.g., "selfhost/image_z_image_turbo_gguf.json")
        
        Raises:
            ValueError: If no compatible workflow can be resolved
        """
        domain = workflow_domain or self.service_name
        available_workflows = available_workflows or self._scan_workflows()
        available_keys = available_keys or [wf["key"] for wf in available_workflows]
        configured_workflow = get_configured_default_workflow(self.global_config, domain)
        compatible_workflows = _filter_workflow_infos_for_domain(
            domain,
            available_workflows,
        )
        compatible_keys = [workflow_info["key"] for workflow_info in compatible_workflows]
        default_workflow = None
        if configured_workflow and configured_workflow in compatible_keys:
            default_workflow = configured_workflow
        else:
            default_workflow = resolve_default_workflow(
                domain=domain,
                available_keys=compatible_keys or available_keys,
                configured_workflow=configured_workflow,
            )
        
        if not default_workflow:
            raise ValueError(
                f"No compatible workflows available for {domain}. "
                f"Available workflows: {', '.join(available_keys) if available_keys else 'none'}"
            )
        
        return default_workflow
    
    def _resolve_workflow(
        self,
        workflow: Optional[str] = None,
        workflow_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve workflow key to workflow info
        
        Args:
            workflow: Workflow key (e.g., "selfhost/image_z_image_turbo_gguf.json")
                     If None, uses the effective default workflow
        
        Returns:
            Workflow info dict with structure:
            {
                "name": "image_flux.json",
                "display_name": "image_flux.json - Runninghub",
                "source": "runninghub",
                "path": "workflows/selfhost/image_z_image_turbo_gguf.json",
                "key": "selfhost/image_z_image_turbo_gguf.json",
                "workflow_id": "123456"  # Only for RunningHub
            }
        
        Raises:
            ValueError: If workflow not found
        """
        # 1. Scan available workflows
        available_workflows = self._scan_workflows()
        available_keys = [wf["key"] for wf in available_workflows]

        # 2. If not specified, resolve the effective default workflow
        if workflow is None:
            workflow = self._get_default_workflow(
                workflow_domain=workflow_domain,
                available_keys=available_keys,
                available_workflows=available_workflows,
            )
        else:
            workflow = workflow.strip()
            matching_workflow = next(
                (wf_info for wf_info in available_workflows if wf_info["key"] == workflow),
                None,
            )
            if (
                workflow_domain
                and matching_workflow is not None
                and not _workflow_info_is_compatible(matching_workflow, workflow_domain)
            ):
                compatible_keys = [
                    workflow_info["key"]
                    for workflow_info in _filter_workflow_infos_for_domain(
                        workflow_domain,
                        available_workflows,
                    )
                ]
                if not compatible_keys:
                    compatible_keys = filter_workflow_keys_for_domain(
                        workflow_domain,
                        available_keys,
                    )
                compatible_str = ", ".join(compatible_keys) if compatible_keys else "none"
                raise ValueError(
                    f"Workflow '{workflow}' is not compatible with domain '{workflow_domain}'. "
                    f"Available {workflow_domain} workflows: {compatible_str}"
                )
        
        # 3. Find matching workflow by key
        for wf_info in available_workflows:
            if wf_info["key"] == workflow:
                logger.info(f"🎬 Using {self.service_name} workflow: {workflow}")
                return wf_info
        
        # 4. Not found - generate error message
        available_str = ", ".join(available_keys) if available_keys else "none"
        raise ValueError(
            f"Workflow '{workflow}' not found. "
            f"Available workflows: {available_str}"
        )
    
    def _prepare_comfykit_config(
        self,
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        runninghub_instance_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare ComfyKit configuration
        
        Args:
            comfyui_url: ComfyUI URL (optional, overrides config)
            runninghub_api_key: RunningHub API key (optional, overrides config)
            runninghub_instance_type: RunningHub instance type (optional, overrides config)
        
        Returns:
            ComfyKit configuration dict
        """
        kit_config = {}
        
        # ComfyUI URL (priority: param > global config > env > default)
        final_comfyui_url = (
            comfyui_url 
            or self.global_config.get("comfyui_url")
            or os.getenv("COMFYUI_BASE_URL")
            or "http://127.0.0.1:8188"
        )
        kit_config["comfyui_url"] = final_comfyui_url
        
        # RunningHub API key (priority: param > global config > env)
        final_rh_key = (
            runninghub_api_key
            or self.global_config.get("runninghub_api_key")
            or os.getenv("RUNNINGHUB_API_KEY")
        )
        if final_rh_key:
            kit_config["runninghub_api_key"] = final_rh_key
        
        # RunningHub instance type (priority: param > global config > env)
        # Only pass if non-empty value
        final_instance_type = (
            runninghub_instance_type
            or self.global_config.get("runninghub_instance_type")
            or os.getenv("RUNNINGHUB_INSTANCE_TYPE")
        )
        if final_instance_type and final_instance_type.strip():
            kit_config["runninghub_instance_type"] = final_instance_type
        
        logger.debug(f"ComfyKit config: {kit_config}")
        return kit_config

    def _get_backend_registry(self):
        core = self.core
        if core is None:
            return None
        get_registry = getattr(core, "_get_comfyui_backend_registry", None)
        if not callable(get_registry):
            return None
        return get_registry()

    def _build_resolved_workflow_file_trace(
        self,
        workflow_info: Mapping[str, Any],
        workflow_input: Any,
    ) -> dict[str, Any]:
        return build_workflow_file_trace(
            str(workflow_info.get("path") or ""),
            str(workflow_info.get("key") or ""),
            workflow_input,
        )

    async def _execute_workflow(
        self,
        workflow_input: Any,
        workflow_params: Dict[str, Any],
        workflow_info: Dict[str, Any],
        *,
        backend_role: str = "default",
        media_prompt_trace_context: Optional[Dict[str, Any]] = None,
        tts_workflow_trace_context: Optional[Dict[str, Any]] = None,
        analysis_workflow_trace_context: Optional[Dict[str, Any]] = None,
        media_type: Optional[str] = None,
        workflow_domain: Optional[str] = None,
    ):
        """Execute a workflow through the core so local ComfyUI lifecycle is centralized."""
        execute_workflow = getattr(self.core, "execute_comfykit_workflow", None)
        if not callable(execute_workflow):
            raise RuntimeError(
                "A provenance-capable core.execute_comfykit_workflow is required "
                "before workflow execution"
            )

        execute_kwargs = {
            "workflow_source": workflow_info.get("source", "selfhost"),
            "backend_role": backend_role,
        }
        analysis_service_domain = None
        media_service_domain = None
        tts_service_domain = None
        effective_media_type = media_type
        if str(workflow_domain or "").strip().lower() in {
            "analysis",
            "image_analysis",
            "video_analysis",
        }:
            execute_workflow = getattr(
                self.core,
                "_execute_analysis_comfykit_workflow",
                None,
            )
            if not callable(execute_workflow):
                raise RuntimeError(
                    "A provenance-capable core._execute_analysis_comfykit_workflow "
                    "is required before analysis workflow execution"
                )
            analysis_service_domain = workflow_info.get("service_domain")
            if analysis_service_domain not in {"image_analysis", "video_analysis"}:
                raise ValueError(
                    "analysis workflow execution requires explicit service_domain metadata"
                )
            if (
                self.service_name.endswith("_analysis")
                and analysis_service_domain != self.service_name
            ):
                raise ValueError(
                    "analysis workflow service_domain does not match calling service"
                )
        elif self.service_name == "tts" or tts_workflow_trace_context is not None:
            tts_execute_workflow = getattr(
                self.core,
                "_execute_tts_comfykit_workflow",
                None,
            )
            if callable(tts_execute_workflow):
                execute_workflow = tts_execute_workflow
                tts_service_domain = "tts"
            elif workflow_info.get("source") == "runninghub":
                raise RuntimeError(
                    "A provenance-capable core._execute_tts_comfykit_workflow is "
                    "required before RunningHub TTS workflow execution"
                )
        else:
            descriptor_media_domain = str(workflow_info.get("media_type") or "").strip().lower()
            requested_media_domain = str(media_type or workflow_domain or "").strip().lower()
            if descriptor_media_domain in MEDIA_WORKFLOW_DOMAINS:
                if (
                    requested_media_domain in MEDIA_WORKFLOW_DOMAINS
                    and requested_media_domain != descriptor_media_domain
                ):
                    raise ValueError(
                        "media_type does not match resolved media workflow contract"
                    )
                requested_media_domain = descriptor_media_domain
            if requested_media_domain in {"image", "video"}:
                media_execute_workflow = getattr(
                    self.core,
                    "_execute_media_comfykit_workflow",
                    None,
                )
                if callable(media_execute_workflow):
                    execute_workflow = media_execute_workflow
                    media_service_domain = requested_media_domain
                    effective_media_type = requested_media_domain
        optional_kwargs = {
            "media_prompt_trace_context": media_prompt_trace_context,
            "tts_workflow_trace_context": tts_workflow_trace_context,
            "analysis_workflow_trace_context": analysis_workflow_trace_context,
            "media_type": effective_media_type,
            "workflow_domain": workflow_domain,
            "analysis_service_domain": analysis_service_domain,
            "media_service_domain": media_service_domain,
            "tts_service_domain": tts_service_domain,
            "resolved_workflow": workflow_info.get("key"),
        }
        workflow_file_trace = self._build_resolved_workflow_file_trace(
            workflow_info,
            workflow_input,
        )
        if workflow_file_trace:
            optional_kwargs["workflow_file_trace"] = workflow_file_trace
        for key, value in optional_kwargs.items():
            if value is None:
                continue
            if not _callable_accepts_keyword(execute_workflow, key):
                raise RuntimeError(
                    "A provenance-capable core.execute_comfykit_workflow is required "
                    f"to accept {key}"
                )
            execute_kwargs[key] = value
        return await execute_workflow(
            workflow_input,
            workflow_params,
            **execute_kwargs,
        )
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """
        List all available workflows with full metadata
        
        Returns:
            List of workflow info dicts (sorted by key)
        
        Example:
            workflows = service.list_workflows()
            # [
            #     {
            #         "name": "image_flux.json",
            #         "display_name": "image_flux.json - Runninghub",
            #         "source": "runninghub",
            #         "path": "workflows/selfhost/image_z_image_turbo_gguf.json",
            #         "key": "selfhost/image_z_image_turbo_gguf.json",
            #         "workflow_id": "123456"
            #     },
            #     ...
            # ]
        """
        return self._scan_workflows()
    
    @property
    def available(self) -> List[str]:
        """
        List available workflow keys
        
        Returns:
            List of available workflow keys (e.g., ["selfhost/image_z_image_turbo_gguf.json", ...])
        
        Example:
            print(f"Available workflows: {service.available}")
        """
        workflows = self.list_workflows()
        return [wf["key"] for wf in workflows]
    
    def __repr__(self) -> str:
        """String representation"""
        default = self._get_default_workflow()
        available = ", ".join(self.available) if self.available else "none"
        return (
            f"<{self.__class__.__name__} "
            f"default={default!r} "
            f"available=[{available}]>"
        )
