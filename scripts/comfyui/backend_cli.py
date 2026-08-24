from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.services.comfyui_backend_manager import ManagedComfyUIBackend

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_project_config(config_path: Path) -> PixelleVideoConfig:
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Pixelle configuration file does not exist: {config_path}. "
            "Copy config.example.yaml to config.yaml and configure the default ComfyUI backend."
        )
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML configuration in {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Pixelle configuration root must be a mapping: {config_path}")
    return PixelleVideoConfig.model_validate(payload)


async def _run_action(
    action: str, config_path: Path, profile_name: str | None
) -> dict:
    config = _load_project_config(config_path)
    profile_name = profile_name or config.comfyui.workflow_routing.default
    profile = config.comfyui.backends.get(profile_name)
    if profile is None:
        available = ", ".join(sorted(config.comfyui.backends))
        raise ValueError(
            f"Unknown ComfyUI backend profile '{profile_name}'. Available profiles: {available}"
        )
    if not profile.managed:
        raise RuntimeError(
            f"ComfyUI backend profile '{profile_name}' has managed=false; "
            "Pixelle will not start or stop an externally managed process."
        )
    if config.comfyui.backend_management_mode == "disabled":
        raise RuntimeError(
            "ComfyUI backend management is disabled in config.yaml. "
            "Set comfyui.backend_management_mode to auto or required."
        )

    backend = ManagedComfyUIBackend(
        repo_root=REPO_ROOT,
        working_directory=config_path.parent,
        profile_name=profile_name,
        profile=profile,
        management_mode="required",
    )
    if not backend.can_manage():
        raise RuntimeError(
            "This backend cannot be managed by the bundled lifecycle scripts. "
            "Use a local HTTP URL on Windows PowerShell, or set managed=false and manage ComfyUI externally."
        )

    if action == "start":
        ready = await backend.ensure_ready(reason="manual-start")
        result_payload = {
            "started": ready.started,
            "already_running": ready.reused_existing,
            "ownership": ready.ownership,
            "health": ready.health,
        }
        return {
            "action": "start",
            "returncode": 0,
            "profile": profile_name,
            "config_path": str(config_path),
            "result": result_payload,
        }

    operation = getattr(backend, action)
    result = await operation(reason=f"manual-{action}")
    return {
        "action": result.action,
        "returncode": result.returncode,
        "profile": profile_name,
        "config_path": str(config_path),
        "result": result.payload,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage a Pixelle ComfyUI backend profile from config.yaml."
    )
    parser.add_argument("action", choices=("start", "check", "stop"))
    parser.add_argument("--config", default="config.yaml", help="Pixelle YAML configuration path")
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "ComfyUI backend profile name; defaults to workflow_routing.default"
        ),
    )
    return parser.parse_args(argv)


async def _main_async(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    try:
        payload = await _run_action(args.action, config_path, args.profile)
    except Exception as exc:
        print(f"[Pixelle] ComfyUI backend {args.action} failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
