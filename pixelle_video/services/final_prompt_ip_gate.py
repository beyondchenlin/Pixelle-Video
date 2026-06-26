from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_anchor_policy import anchor_identity_from_profile


class FinalPromptIPGateError(ValueError):
    """Raised when mandatory IP participation is missing from the final prompt."""


@dataclass(frozen=True)
class FinalPromptIPGateResult:
    passed: bool
    identity_kernel: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "identity_kernel": self.identity_kernel,
            "reason": self.reason,
        }


def assert_mandatory_ip_final_prompt(
    *,
    prompt: str,
    anchor_clause: str,
    visual_anchor_plan: VisualAnchorPlacementPlan | None,
    policy: VisualSignaturePolicy,
    anchor_profile: IPProfile | None = None,
) -> FinalPromptIPGateResult:
    """Validate the last boundary before a provider sees the prompt.

    Mandatory V1 is not allowed to silently render anchor-free images. The
    upstream plan can be correct while the clause is filtered later, so the final
    provider-facing string is checked again here.
    """

    if not policy.requires_every_frame_signature:
        return FinalPromptIPGateResult(passed=True, identity_kernel="", reason="not_mandatory")
    if not policy.requires_repair_or_fail and not anchor_clause:
        return FinalPromptIPGateResult(passed=True, identity_kernel="", reason="anchor_free_allowed")
    if visual_anchor_plan is None or not visual_anchor_plan.visible:
        raise FinalPromptIPGateError("mandatory IP prompt gate failed: visible anchor plan missing")
    if not anchor_clause or anchor_clause not in prompt:
        raise FinalPromptIPGateError("mandatory IP prompt gate failed: final prompt lost the anchor clause")
    if policy.contains_forbidden_overlay_text(prompt):
        raise FinalPromptIPGateError("mandatory IP prompt gate failed: final prompt contains overlay/corner language")
    if policy.contains_forbidden_final_prompt_text(anchor_clause):
        raise FinalPromptIPGateError("mandatory IP prompt gate failed: anchor clause contains content-free IP carrier language")

    identity_kernel = _identity_kernel(anchor_profile, visual_anchor_plan)
    if policy.require_concrete_identity and not identity_kernel:
        raise FinalPromptIPGateError("mandatory IP prompt gate failed: concrete identity kernel missing")
    if identity_kernel and not _identity_appears(identity_kernel, anchor_clause):
        raise FinalPromptIPGateError("mandatory IP prompt gate failed: anchor clause does not preserve identity kernel")
    return FinalPromptIPGateResult(passed=True, identity_kernel=identity_kernel, reason="passed")


def _identity_kernel(anchor_profile: IPProfile | None, visual_anchor_plan: VisualAnchorPlacementPlan) -> str:
    if anchor_profile is not None:
        try:
            return anchor_identity_from_profile(anchor_profile)
        except ValueError:
            return ""
    metadata = dict(visual_anchor_plan.metadata or {})
    for key in ("visual_identity_kernel", "identity_kernel", "identity_phrase"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (list, tuple)):
            text = "，".join(str(item).strip() for item in value if str(item).strip())
            if text:
                return text
    return _identity_from_plan_clause(visual_anchor_plan.image_prompt_clause)


def _identity_from_plan_clause(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[:160]


def _identity_appears(identity_kernel: str, anchor_clause: str) -> bool:
    identity = str(identity_kernel or "").strip()
    clause = str(anchor_clause or "")
    if not identity:
        return False
    if identity in clause:
        return True
    tokens = [token for token in identity.replace("，", " ").replace(",", " ").split() if len(token) >= 2]
    return bool(tokens) and any(token in clause for token in tokens)


__all__ = [
    "FinalPromptIPGateError",
    "FinalPromptIPGateResult",
    "assert_mandatory_ip_final_prompt",
]
