from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from pixelle_video.models.visual_profile import VisualProfile


@dataclass(frozen=True)
class VisualQualityIssue:
    frame_index: int
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True)
class VisualQualityReport:
    passed: bool
    issues: tuple[VisualQualityIssue, ...] = ()
    repair_clauses_by_frame: Mapping[int, tuple[str, ...]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [issue.to_dict() for issue in self.issues],
            "repair_clauses_by_frame": {
                str(index): list(clauses)
                for index, clauses in self.repair_clauses_by_frame.items()
            },
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VisualQualityGate:
    """Prompt-level preflight quality gate.

    The gate intentionally runs before media generation.  It cannot replace
    image understanding QA, but it prevents the common upstream failure mode:
    prompt contracts losing the requested visual profile before the image
    provider ever sees them.
    """

    enabled: bool = True
    strict: bool = False

    def evaluate_prompts(
        self,
        prompts: Sequence[str],
        *,
        profile: VisualProfile,
        frame_contexts: Sequence[Mapping[str, Any]] = (),
    ) -> VisualQualityReport:
        if not self.enabled:
            return VisualQualityReport(
                passed=True,
                metadata={"enabled": False, "profile_id": profile.profile_id},
            )

        issues: list[VisualQualityIssue] = []
        repair_by_frame: dict[int, tuple[str, ...]] = {}
        for index, prompt in enumerate(prompts):
            text = str(prompt or "")
            lowered = text.lower()
            missing_terms = [
                term
                for term in profile.required_prompt_terms
                if str(term).lower() not in lowered
            ]
            for term in missing_terms:
                issues.append(
                    VisualQualityIssue(
                        frame_index=index,
                        code="missing_required_visual_term",
                        severity="error" if self.strict else "warning",
                        message=f"prompt is missing required visual term: {term}",
                    )
                )

            forbidden_terms = [
                term
                for term in profile.forbidden_prompt_terms
                if _contains_unnegated_forbidden_term(lowered, str(term).lower())
            ]
            for term in forbidden_terms:
                issues.append(
                    VisualQualityIssue(
                        frame_index=index,
                        code="forbidden_visual_term",
                        severity="error" if self.strict else "warning",
                        message=f"prompt contains forbidden visual term: {term}",
                    )
                )

            if missing_terms or forbidden_terms:
                repair_by_frame[index] = tuple(profile.repair_prompt_clauses)

        passed = not any(issue.severity == "error" for issue in issues)
        report = VisualQualityReport(
            passed=passed,
            issues=tuple(issues),
            repair_clauses_by_frame=repair_by_frame,
            metadata={
                "enabled": True,
                "strict": self.strict,
                "profile_id": profile.profile_id,
                "frame_count": len(prompts),
                "context_count": len(frame_contexts),
            },
        )
        if self.strict and not report.passed:
            messages = "; ".join(issue.message for issue in report.issues[:5])
            raise ValueError(f"visual quality gate failed: {messages}")
        return report


def _contains_unnegated_forbidden_term(text: str, term: str) -> bool:
    if not term or term not in text:
        return False
    # Do not fail on explicit negative constraints such as "no PPT" or
    # "禁止 PPT".  These are expected in positive-only provider prompts.
    negation_markers = (
        "no ", "not ", "without ", "avoid ", "禁止", "不要", "避免", "不能",
    )
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return False
        prefix = text[max(0, index - 16):index]
        if not any(marker in prefix for marker in negation_markers):
            return True
        start = index + len(term)


__all__ = ["VisualQualityGate", "VisualQualityIssue", "VisualQualityReport"]
