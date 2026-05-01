from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pixelle_video.models.artifact import ArtifactVersion
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast

TRANSIENT_KEYS = {
    "created_at",
    "updated_at",
    "generated_at",
    "last_saved_by",
    "last_saved_at",
}


class DependencyVersionService:
    def version_for_asset_bible(self, asset_bible: AssetBible) -> str:
        return _version_token("asset_bible", asset_bible.to_dict())

    def version_for_scene_cast(self, scene_cast: SceneCast) -> str:
        return _version_token("scene_cast", scene_cast.to_dict())

    def version_for_prompt_plan(self, prompt_plan: PromptPlan) -> str:
        return _version_token("prompt_plan", prompt_plan.to_dict())

    def version_for_artifact_version(self, version: ArtifactVersion) -> str:
        payload = {
            "artifact_id": version.artifact_id,
            "version_id": version.version_id,
            "workspace_id": version.workspace_id,
            "frame_id": version.frame_id,
            "source_prompt_plan_id": version.source_prompt_plan_id,
            "status": version.status.value,
            "provider": version.provider,
            "width": version.width,
            "height": version.height,
            "trace_event_id": version.trace_event_id,
            "metadata": version.metadata,
        }
        return _version_token("image_artifact", payload)


def _version_token(prefix: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _strip_transient(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_rev_{digest}"


def _strip_transient(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_transient(item)
            for key, item in value.items()
            if str(key) not in TRANSIENT_KEYS
        }
    if isinstance(value, list | tuple):
        return [_strip_transient(item) for item in value]
    return deepcopy(value)
