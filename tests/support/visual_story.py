from __future__ import annotations

import json
from typing import Any


class DeterministicFrameVisualPlanLLM:
    """Test double that implements the production frame-planning call contract."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
        self.calls.append(dict(kwargs))
        prompt = str(kwargs.get("prompt") or "")
        marker = "Current batch payload:\n"
        terminator = "\n\nTask:"
        if marker not in prompt or terminator not in prompt:
            raise RuntimeError("test double only supports frame visual planning")
        payload_text = prompt.split(marker, 1)[1].split(terminator, 1)[0]
        frame_contexts = json.loads(payload_text)["frame_contexts"]
        return {
            "frame_visual_plans": [
                {
                    "frame_id": frame["frame_id"],
                    "frame_index": frame["frame_index"],
                    "source_text": frame.get("source_text") or "source",
                    "local_claim": frame.get("visual_goal") or "claim",
                    "visual_task": "show the local claim",
                    "visual_logic": "apply the selected content route",
                    "required_subjects": [frame.get("visual_goal") or "subject"],
                }
                for frame in frame_contexts
            ]
        }
