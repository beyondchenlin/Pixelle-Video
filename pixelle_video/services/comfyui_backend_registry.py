from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from pixelle_video.config.schema import ComfyUIBackendProfile, ComfyUIConfig
from pixelle_video.services.comfyui_backend_manager import ComfyUIBackendController
from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient


class ComfyUIBackendRegistry:
    """Resolves ComfyUI backend roles and creates role-specific helpers."""

    def __init__(self, config: ComfyUIConfig, *, repo_root: str | Path) -> None:
        self.config = config
        self.repo_root = Path(repo_root)

    def profile(self, role: str) -> ComfyUIBackendProfile:
        normalized_role = self._normalize_role(role)
        profile = self.config.backends.get(normalized_role)
        if profile is None:
            raise ValueError(f"Unknown ComfyUI backend profile role: {normalized_role}")
        return profile

    def resolve_role_for_media(self, workflow_key: Any, media_type: str) -> str:
        if (
            self._is_selfhost_image_workflow(workflow_key)
            and str(media_type or "").strip().lower() == "image"
        ):
            return self.config.workflow_routing.image
        return self.resolve_role_for_workflow(workflow_key)

    def resolve_role_for_tts(self, workflow_key: Any) -> str:
        if self._is_selfhost_tts_workflow(workflow_key):
            return self.config.workflow_routing.tts
        return "default"

    def resolve_role_for_workflow(self, workflow_key: Any) -> str:
        if not self._is_selfhost_workflow(workflow_key):
            return "default"
        if self._is_selfhost_image_workflow(workflow_key):
            return self.config.workflow_routing.image
        if self._is_selfhost_tts_workflow(workflow_key):
            return self.config.workflow_routing.tts
        return self.config.workflow_routing.default

    def is_dedicated_backend(self, role: str) -> bool:
        normalized_role = self._normalize_role(role)
        return normalized_role != "default" and normalized_role in self.config.backends

    def get_comfykit_config(self, role: str) -> dict[str, Any]:
        profile = self.profile(role)
        kit_config: dict[str, Any] = {}

        if profile.url:
            kit_config["comfyui_url"] = profile.url
        kit_config["executor_type"] = self.config.executor_type or "http"
        if self.config.comfyui_api_key:
            kit_config["api_key"] = self.config.comfyui_api_key
        if self.config.runninghub_api_key:
            kit_config["runninghub_api_key"] = self.config.runninghub_api_key
        instance_type = self.config.runninghub_instance_type
        if instance_type and instance_type.strip():
            kit_config["runninghub_instance_type"] = instance_type

        return kit_config

    def maintenance_client(self, role: str) -> ComfyUIMaintenanceClient:
        profile = self.profile(role)
        return ComfyUIMaintenanceClient(
            profile.url or "",
            api_key=self.config.comfyui_api_key,
            idle_wait_timeout=20.0,
        )

    def backend_controller(self, role: str) -> ComfyUIBackendController | None:
        normalized_role = self._normalize_role(role)
        profile = self.profile(role)
        if not profile.url:
            return None
        return ComfyUIBackendController(
            repo_root=self.repo_root,
            profile_name=normalized_role,
            profile=profile,
            management_mode=self.config.backend_management_mode,
            maintenance_client=self.maintenance_client(normalized_role),
            lifetime_owner_pid=os.getpid(),
        )

    def managed_backend(self, role: str) -> ComfyUIBackendController | None:
        """Backward-compatible alias; ownership is determined from runtime state."""
        return self.backend_controller(role)

    def _is_selfhost_image_workflow(self, workflow_key: Any) -> bool:
        return self._is_selfhost_workflow(workflow_key) and self._workflow_filename(
            workflow_key
        ).startswith(("image_", "image."))

    def _is_selfhost_tts_workflow(self, workflow_key: Any) -> bool:
        return self._is_selfhost_workflow(workflow_key) and self._workflow_filename(
            workflow_key
        ).startswith(("tts_", "tts."))

    def _is_selfhost_workflow(self, workflow_key: Any) -> bool:
        source = self._workflow_source(workflow_key)
        if source:
            return source == "selfhost"
        return "selfhost" in self._workflow_parts(workflow_key)

    def _workflow_source(self, workflow_key: Any) -> str | None:
        if not isinstance(workflow_key, Mapping):
            return None
        source = workflow_key.get("source")
        if source is None:
            return None
        return str(source).strip().lower()

    def _workflow_filename(self, workflow_key: Any) -> str:
        if isinstance(workflow_key, Mapping):
            for key in ("key", "path", "workflow", "name"):
                value = workflow_key.get(key)
                if value:
                    return self._workflow_filename(value)
            return ""
        normalized = self._normalize_workflow_key(workflow_key)
        return normalized.rsplit("/", 1)[-1]

    def _workflow_parts(self, workflow_key: Any) -> tuple[str, ...]:
        return tuple(
            part
            for part in self._normalize_workflow_key(workflow_key).split("/")
            if part
        )

    def _normalize_workflow_key(self, workflow_key: Any) -> str:
        return str(workflow_key or "").strip().replace("\\", "/").lower()

    def _normalize_role(self, role: str) -> str:
        return str(role or "").strip()
