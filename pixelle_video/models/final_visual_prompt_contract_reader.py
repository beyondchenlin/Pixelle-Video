from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.final_visual_prompt_contract_v45 import (
    FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION,
    FinalVisualPromptContractV45,
)
from pixelle_video.models.final_visual_prompt_contract_v46 import (
    FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION,
    FinalVisualPromptContractV46,
)

ReadableFinalVisualPromptContract = (
    FinalVisualPromptContractV45 | FinalVisualPromptContractV46
)


def read_final_visual_prompt_contract(
    source: Mapping[str, Any] | ReadableFinalVisualPromptContract,
    *,
    resume_generation: bool = False,
) -> ReadableFinalVisualPromptContract:
    if isinstance(source, FinalVisualPromptContractV46):
        return source
    if isinstance(source, FinalVisualPromptContractV45):
        if resume_generation:
            raise ValueError(
                "V4.5 final visual prompt contracts are read-only and require V4.6 replanning before generation"
            )
        return source
    if not isinstance(source, Mapping):
        raise ValueError("final visual prompt contract must be a mapping")
    version = str(source.get("contract_version") or "").strip()
    if version == FINAL_VISUAL_PROMPT_CONTRACT_V46_VERSION:
        return FinalVisualPromptContractV46.from_mapping(source)
    if version == FINAL_VISUAL_PROMPT_CONTRACT_V45_VERSION:
        contract = FinalVisualPromptContractV45.from_mapping(source)
        if resume_generation:
            raise ValueError(
                "V4.5 final visual prompt contracts are read-only and require V4.6 replanning before generation"
            )
        return contract
    raise ValueError("unsupported final visual prompt contract version")


__all__ = [
    "ReadableFinalVisualPromptContract",
    "read_final_visual_prompt_contract",
]
