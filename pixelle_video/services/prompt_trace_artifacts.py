from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def write_final_prompt_artifact(
    output_dir: Path,
    task_id: str,
    frames: Sequence[Mapping[str, Any]],
) -> Path:
    artifact_dir = Path(output_dir) / "prompt_traces"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "final_visual_prompts.md"

    lines = [
        "# Final Visual Prompts",
        "",
        f"Task ID: {task_id}",
        f"Frame count: {len(frames)}",
        "",
    ]
    for index, frame in enumerate(frames, start=1):
        frame_number = frame.get("index") if frame.get("index") is not None else index
        frame_id = str(frame.get("frame_id") or frame_number)
        positive_prompt = str(
            frame.get("prompt")
            if frame.get("prompt") is not None
            else frame.get("positive_prompt")
            if frame.get("positive_prompt") is not None
            else frame.get("image_prompt")
            if frame.get("image_prompt") is not None
            else ""
        )
        negative_prompt = str(frame.get("negative_prompt") or "")
        lines.extend(
            [
                f"## Frame {index}",
                "",
                f"Frame ID: {frame_id}",
                "",
                "Positive prompt:",
                "",
                "```text",
                positive_prompt,
                "```",
                "",
                "Negative prompt:",
                "",
                "```text",
                negative_prompt,
                "```",
                "",
            ]
        )

    artifact_path.write_text("\n".join(lines), encoding="utf-8")
    return artifact_path


__all__ = ["write_final_prompt_artifact"]
