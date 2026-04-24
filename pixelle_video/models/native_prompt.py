from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativePromptHint:
    prompt_fragment: str
    role: str = "model_native_hint"
    source_candidate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_candidate_ids",
            tuple(str(candidate_id) for candidate_id in self.source_candidate_ids),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "prompt_fragment": self.prompt_fragment,
            "role": self.role,
            "source_candidate_ids": list(self.source_candidate_ids),
        }
