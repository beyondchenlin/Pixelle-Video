from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_story_execution import ContinuityLedger


@dataclass(frozen=True)
class VisualStoryContinuityLedgerService:
    """Summary-only continuity memory between batches."""

    max_digest_chars: int = 480
    max_symbols: int = 8

    def initial(self, *, selected_visual_route: Mapping[str, Any] | None = None, ip_profile: Any = None, style_plan: Mapping[str, Any] | None = None) -> ContinuityLedger:
        return ContinuityLedger(
            route_digest=_join([selected_visual_route.get(k) for k in ("route_id", "route_name", "visual_premise", "recommended_ip_role")] if isinstance(selected_visual_route, Mapping) else [], limit=480),
            ip_identity_digest=_ip_digest(ip_profile),
            style_digest=_join([style_plan.get(k) for k in ("mode", "ip_style_policy", "scene_style_policy", "boundary_rule")] if isinstance(style_plan, Mapping) else [], limit=420),
            recurring_symbols=_symbols_from_ip(ip_profile)[: self.max_symbols],
        )

    def update_after_batch(self, *, ledger: ContinuityLedger | Mapping[str, Any], batch_id: str, frame_visual_plans: Sequence[Mapping[str, Any]], frame_ip_fusion_plans: Sequence[Mapping[str, Any]]) -> ContinuityLedger:
        current = ledger if isinstance(ledger, ContinuityLedger) else ContinuityLedger.from_mapping(ledger)
        digest = _join(
            [
                batch_id,
                *[f"{p.get('frame_id')}: {p.get('visual_task') or p.get('visual_logic') or p.get('local_claim')}" for p in frame_visual_plans],
                *[f"{p.get('frame_id')}: {p.get('ip_role') or p.get('role')} / {p.get('action_or_function') or p.get('scene_function')}" for p in frame_ip_fusion_plans],
            ],
            limit=self.max_digest_chars,
        )
        return ContinuityLedger(
            route_digest=current.route_digest,
            ip_identity_digest=current.ip_identity_digest,
            style_digest=current.style_digest,
            previous_batch_digest=digest,
            recurring_symbols=current.recurring_symbols,
            warnings=current.warnings,
        )


def _ip_digest(ip_profile: Any) -> str:
    if ip_profile is None:
        return ""
    if hasattr(ip_profile, "to_dict"):
        try:
            ip_profile = ip_profile.to_dict()
        except Exception:
            pass
    if isinstance(ip_profile, Mapping):
        parts = [ip_profile.get("name"), ip_profile.get("visual_summary"), ip_profile.get("style_hint")]
        identity = ip_profile.get("identity_lock")
        if isinstance(identity, Sequence) and not isinstance(identity, str):
            parts.append(", ".join(str(x) for x in list(identity)[:6]))
        else:
            parts.append(identity)
        return _join(parts, limit=420)
    return _join([getattr(ip_profile, "name", ""), getattr(ip_profile, "visual_summary", ""), getattr(ip_profile, "style_hint", "")], limit=420)


def _symbols_from_ip(ip_profile: Any) -> tuple[str, ...]:
    if ip_profile is None:
        return ()
    if hasattr(ip_profile, "to_dict"):
        try:
            ip_profile = ip_profile.to_dict()
        except Exception:
            pass
    values = ip_profile.get("identity_lock", ()) if isinstance(ip_profile, Mapping) else getattr(ip_profile, "identity_lock", ())
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, Sequence):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


def _join(values: Sequence[Any], *, limit: int) -> str:
    text = " | ".join(str(v).strip() for v in values if str(v or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


__all__ = ["VisualStoryContinuityLedgerService"]
