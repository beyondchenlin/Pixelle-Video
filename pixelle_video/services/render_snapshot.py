from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pixelle_video.models.render_execution_plan import RenderExecutionPlan
from pixelle_video.models.render_package import RenderManifest
from pixelle_video.services.ffmpeg_manifest_renderer import FfmpegManifestRenderer
from pixelle_video.services.font_discovery import resolve_font_file
from pixelle_video.utils.filesystem import (
    ensure_directory,
    extended_length_path,
    open_file,
    read_text_file,
    write_text_file,
)


@dataclass(frozen=True)
class RenderSnapshotPaths:
    manifest: Path
    execution_plan: Path
    asset_inventory: Path


class RenderSnapshotService:
    """Persist and replay the resolved render stage without generating content."""

    MANIFEST_NAME = "render_manifest.json"
    EXECUTION_PLAN_NAME = "render_execution_plan.json"
    ASSET_INVENTORY_NAME = "render_asset_inventory.json"

    def write(
        self,
        *,
        output_dir: str | Path,
        manifest: RenderManifest,
        execution_plan: RenderExecutionPlan,
        supplemental_assets: Mapping[str, str | Path | None] | None = None,
        render_options: Mapping[str, object] | None = None,
    ) -> RenderSnapshotPaths:
        target = Path(output_dir).resolve()
        ensure_directory(target)
        paths = RenderSnapshotPaths(
            manifest=target / self.MANIFEST_NAME,
            execution_plan=target / self.EXECUTION_PLAN_NAME,
            asset_inventory=target / self.ASSET_INVENTORY_NAME,
        )
        asset_inventory = self._build_asset_inventory(
            manifest,
            supplemental_assets=supplemental_assets,
            render_options=render_options,
        )
        self._write_json_atomic(paths.manifest, manifest.to_dict())
        self._write_json_atomic(paths.execution_plan, execution_plan.to_dict())
        self._write_json_atomic(paths.asset_inventory, asset_inventory)
        return paths

    def load(self, manifest_path: str | Path) -> RenderManifest:
        path = Path(manifest_path).resolve()
        if not extended_length_path(path).is_file():
            raise ValueError(f"render manifest must be an existing file: {path}")
        try:
            payload = json.loads(read_text_file(path))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"render manifest is not valid UTF-8 JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("render manifest root must be a JSON object")
        return RenderManifest.from_dict(payload)

    def rerender_ffmpeg(
        self,
        *,
        manifest_path: str | Path,
        output_path: str | Path,
        ass_path: str | Path | None = None,
        bgm_path: str | Path | None = None,
        bgm_volume: float | None = None,
        bgm_mode: str | None = None,
        renderer: FfmpegManifestRenderer | None = None,
    ) -> str:
        manifest_path = Path(manifest_path).resolve()
        manifest = self.load(manifest_path)
        inventory = self.verify_assets(manifest_path)
        assets_by_role = {
            str(item["role"]): Path(str(item["path"])).resolve()
            for item in inventory["assets"]
        }
        ass_path = self._resolve_replay_asset(
            role="ass",
            requested=ass_path,
            assets_by_role=assets_by_role,
        )
        bgm_path = self._resolve_replay_asset(
            role="bgm",
            requested=bgm_path,
            assets_by_role=assets_by_role,
        )
        saved_options = dict(inventory.get("render_options") or {})
        effective_bgm_volume = (
            float(saved_options.get("bgm_volume", 0.2))
            if bgm_volume is None
            else float(bgm_volume)
        )
        effective_bgm_mode = (
            str(saved_options.get("bgm_mode", "loop"))
            if bgm_mode is None
            else str(bgm_mode)
        )
        plan = RenderExecutionPlan(
            requested_backend="ffmpeg_manifest",
            effective_backend="ffmpeg_manifest",
            fallback_reason=None,
            diagnostics={"source": "fixed_asset_rerender"},
        )
        return (renderer or FfmpegManifestRenderer()).render(
            manifest=manifest,
            execution_plan=plan,
            output_path=str(Path(output_path).resolve()),
            ass_path=str(ass_path) if ass_path is not None else None,
            bgm_path=str(bgm_path) if bgm_path is not None else None,
            bgm_volume=effective_bgm_volume,
            bgm_mode=effective_bgm_mode,
        )

    def verify_assets(self, manifest_path: str | Path) -> dict:
        manifest = Path(manifest_path).resolve()
        inventory_path = manifest.with_name(self.ASSET_INVENTORY_NAME)
        if not extended_length_path(inventory_path).is_file():
            raise ValueError(
                f"fixed-asset rerender requires an asset inventory: {inventory_path}"
            )
        try:
            payload = json.loads(read_text_file(inventory_path))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"render asset inventory is invalid: {inventory_path}") from exc
        if payload.get("version") != "render_asset_inventory.v1":
            raise ValueError("unsupported render asset inventory version")
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise ValueError("render asset inventory assets must be a list")
        for item in assets:
            if not isinstance(item, dict):
                raise ValueError("render asset inventory entry must be an object")
            path = Path(str(item.get("path") or "")).resolve()
            filesystem_path = extended_length_path(path)
            if not filesystem_path.is_file():
                raise ValueError(f"render snapshot asset is missing: {path}")
            if filesystem_path.stat().st_size != int(item.get("size") or -1):
                raise ValueError(f"render snapshot asset size changed: {path}")
            if self._sha256(path) != str(item.get("sha256") or ""):
                raise ValueError(f"render snapshot asset content changed: {path}")
        return payload

    @classmethod
    def _build_asset_inventory(
        cls,
        manifest: RenderManifest,
        *,
        supplemental_assets: Mapping[str, str | Path | None] | None,
        render_options: Mapping[str, object] | None,
    ) -> dict:
        assets: list[tuple[str, Path]] = []
        if manifest.master_audio_path:
            assets.append(("master_audio", Path(manifest.master_audio_path).resolve()))
        assets.extend(
            (f"visual_clip:{clip.id}", Path(clip.media_path).resolve())
            for clip in manifest.visual_clips
        )
        for profile in manifest.text_style_profiles:
            font_path = resolve_font_file(profile.font_file)
            if font_path is not None:
                assets.append((f"font:{profile.id}", font_path))
        for role, raw_path in (supplemental_assets or {}).items():
            if raw_path is not None:
                assets.append((str(role), Path(raw_path).resolve()))

        entries = []
        digests_by_path: dict[Path, str] = {}
        for role, path in assets:
            filesystem_path = extended_length_path(path)
            if not filesystem_path.is_file():
                raise ValueError(f"render snapshot asset must exist: {path}")
            digest = digests_by_path.get(path)
            if digest is None:
                digest = cls._sha256(path)
                digests_by_path[path] = digest
            entries.append(
                {
                    "role": role,
                    "path": str(path),
                    "size": filesystem_path.stat().st_size,
                    "sha256": digest,
                }
            )
        return {
            "version": "render_asset_inventory.v1",
            "assets": entries,
            "render_options": dict(render_options or {}),
        }

    @staticmethod
    def _resolve_replay_asset(
        *,
        role: str,
        requested: str | Path | None,
        assets_by_role: Mapping[str, Path],
    ) -> Path | None:
        saved = assets_by_role.get(role)
        if requested is None:
            return saved
        resolved = Path(requested).resolve()
        if saved is not None and resolved != saved:
            raise ValueError(
                f"fixed-asset rerender cannot replace the snapshotted {role} asset"
            )
        return resolved

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open_file(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary_filesystem_path = extended_length_path(temporary)
        try:
            write_text_file(
                temporary,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            os.replace(temporary_filesystem_path, extended_length_path(path))
        finally:
            if temporary_filesystem_path.exists():
                temporary_filesystem_path.unlink()


__all__ = ["RenderSnapshotPaths", "RenderSnapshotService"]
