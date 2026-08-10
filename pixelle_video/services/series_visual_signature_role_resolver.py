from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRole

_PROCESS_GRAMMARS = frozenset({"process_flow", "decision_tree", "state_machine"})
_GUIDE_GRAMMARS = frozenset({"structure_map", "relationship_map", "evidence_map"})
_PROCESS_ANCHORS = frozenset(
    {"causal_mechanism", "process", "decision_path", "state_machine"}
)
_GUIDE_ANCHORS = frozenset({"structure", "relationship", "evidence"})
_WITNESS_ANCHORS = frozenset({"judgment", "state", "metaphor", "contrast"})
_PROCESS_TASKS = frozenset({"process_walkthrough"})
_GUIDE_TASKS = frozenset({"structure_explanation", "relationship_mapping"})
_WITNESS_TASKS = frozenset({"contrast_argument", "cognitive_explanation"})


def resolve_series_visual_signature_role(
    requested_role: SeriesVisualSignatureRole | str | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> SeriesVisualSignatureRole:
    """Resolve one concrete role from request plus frame/planning context.

    Explicit concrete roles always win. ``auto`` and compatibility ``none`` use
    deterministic scene semantics instead of collapsing to one hard-coded role.
    When no useful context exists, the conservative fallback is a silent witness,
    which participates without taking over the source subject.
    """

    role = _role_value(requested_role)
    if role not in {SeriesVisualSignatureRole.NONE, SeriesVisualSignatureRole.AUTO}:
        return role

    facts = _context_facts(context)
    grammar = facts["grammar"]
    anchor = facts["anchor"]
    task = facts["task"]

    if grammar in _PROCESS_GRAMMARS or anchor in _PROCESS_ANCHORS or task in _PROCESS_TASKS:
        return SeriesVisualSignatureRole.OPERATOR
    if grammar in _GUIDE_GRAMMARS or anchor in _GUIDE_ANCHORS or task in _GUIDE_TASKS:
        return SeriesVisualSignatureRole.GUIDE
    if anchor in _WITNESS_ANCHORS or task in _WITNESS_TASKS:
        return SeriesVisualSignatureRole.SILENT_WITNESS
    return SeriesVisualSignatureRole.SILENT_WITNESS


def _role_value(value: SeriesVisualSignatureRole | str | None) -> SeriesVisualSignatureRole:
    if isinstance(value, SeriesVisualSignatureRole):
        return value
    text = str(value or "").strip()
    if not text:
        return SeriesVisualSignatureRole.AUTO
    for item in SeriesVisualSignatureRole:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError("series_visual_signature_role must be a supported role")


def _context_facts(context: Mapping[str, Any] | None) -> dict[str, str]:
    source = dict(context or {})
    article = source.get("article_concretization")
    if isinstance(article, Mapping):
        source = {**source, **dict(article)}
    return {
        "grammar": _first_text(
            source.get("effective_diagram_grammar"),
            source.get("explanation_diagram_grammar"),
            source.get("grammar"),
        ),
        "anchor": _first_text(
            source.get("effective_anchor_kind"),
            source.get("cognitive_anchor_kind"),
            source.get("anchor_kind"),
        ),
        "task": _first_text(
            source.get("primary_visual_task"),
            source.get("visual_task"),
        ),
    }


def _first_text(*values: Any) -> str:
    for value in values:
        raw = getattr(value, "value", value)
        text = str(raw or "").strip().lower()
        if text and text != "auto":
            return text
    return ""


__all__ = ["resolve_series_visual_signature_role"]
