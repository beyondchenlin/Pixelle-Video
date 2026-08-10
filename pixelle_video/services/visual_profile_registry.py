from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from pixelle_video.models.visual_profile import VisualProfile

BUILTIN_VISUAL_PROFILES: dict[str, dict[str, Any]] = {
    "article_cognitive_illustration": {
        "id": "article_cognitive_illustration",
        "name": "Article Cognitive Illustration",
        "description": "Generic article-to-illustration profile for explanatory, metaphor-first visuals.",
        "canvas_width": 1920,
        "canvas_height": 1080,
        "media_width": 1920,
        "media_height": 1080,
        "frame_template": "1920x1080/image_white_canvas_illustration.html",
        "template_text_policy": "none",
        "template_display": {"show_title": False, "show_signature": False},
        "planning_defaults": {
            "content_mode": "concept_explainer",
            "role_strategy": "stable_explainer_cast",
            "role_locking_strength": "strong",
            "shot_strategy": "cognitive_anchor",
        },
        "positive_prompt_rules": [
            "16:9 horizontal editorial illustration for a Chinese article",
            "one clear cognitive anchor per frame: judgment, process, state, or metaphor",
            "single visual idea, strong negative space, readable at thumbnail size",
            "avoid decorative characters; every visible subject must serve the idea",
        ],
        "composition_rules": [
            "main subject occupies roughly 40%-60% of the canvas",
            "clean foreground/midground/background separation",
            "large uncluttered white or very light background area",
        ],
        "visible_text_rules": [
            "visible text is optional and must be sparse, short, and intentionally placed",
            "prefer rendering exact Chinese text in the template layer when precision matters",
        ],
        "negative_prompt_rules": [
            "PPT slide", "infographic", "formal flowchart", "commercial vector art",
            "UI screenshot", "dense text", "top-left big title", "gradient background",
            "heavy shadow", "paper texture", "crowded composition",
        ],
        "required_prompt_terms": ["16:9", "cognitive anchor"],
        "forbidden_prompt_terms": ["PPT", "infographic", "flowchart", "UI screenshot"],
        "repair_prompt_clauses": [
            "Repair: simplify to one visual metaphor and remove slide-like layout.",
            "Repair: keep the background plain and leave large negative space.",
        ],
    },
    "xiaohei_article_illustration": {
        "id": "xiaohei_article_illustration",
        "name": "Xiaohei Article Illustration",
        "description": "Xiaohei-style low-tech absurd hand-drawn article illustration profile.",
        "canvas_width": 1920,
        "canvas_height": 1080,
        "media_width": 1920,
        "media_height": 1080,
        "frame_template": "1920x1080/image_white_canvas_illustration.html",
        "template_text_policy": "none",
        "template_display": {"show_title": False, "show_signature": False},
        "planning_defaults": {
            "content_mode": "concept_explainer",
            "role_strategy": "stable_explainer_cast",
            "role_locking_strength": "strong",
            "shot_strategy": "cognitive_anchor",
        },
        "positive_prompt_rules": [
            "16:9 horizontal Chinese article body illustration",
            "pure white background, black hand-drawn wobbly line art, minimal low-tech absurd metaphor",
            "Xiaohei is a small solid black creature with white dot eyes and tiny thin legs",
            "Xiaohei must perform the core action of the scene, never stand aside as decoration",
            "one cognitive anchor only: judgment, process, state, or metaphor",
        ],
        "composition_rules": [
            "large empty white space, one central action, no complex environment",
            "main subject occupies roughly 40%-60% of the frame",
            "use only sparse red, orange, or blue handwritten Chinese labels when labels are necessary",
        ],
        "visible_text_rules": [
            "no big title in the top-left corner",
            "at most 3-5 short Chinese labels; avoid full sentences inside the image",
        ],
        "negative_prompt_rules": [
            "PPT", "infographic", "formal flowchart", "business vector illustration",
            "cute mascot", "children book style", "realistic photo", "complex background",
            "gradient", "shadow", "paper texture", "dense Chinese text", "top-left big title",
        ],
        "required_prompt_terms": ["Xiaohei", "white background", "core action"],
        "forbidden_prompt_terms": ["PPT", "infographic", "flowchart", "cute mascot", "children book"],
        "repair_prompt_clauses": [
            "Repair: Xiaohei must be visibly doing the core action in the metaphor.",
            "Repair: remove PPT layout, big title, dense labels, gradient, shadow, and decorative background.",
        ],
    },
}


def resolve_visual_profile(
    *,
    profile_id: str | None = None,
    inline_profile: Mapping[str, Any] | None = None,
    repo_root: str | Path | None = None,
) -> VisualProfile | None:
    """Resolve a profile from inline data, built-ins, or resources/visual_profiles."""

    if inline_profile:
        return VisualProfile.from_mapping(inline_profile)
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return None
    if normalized_id in BUILTIN_VISUAL_PROFILES:
        return VisualProfile.from_mapping(BUILTIN_VISUAL_PROFILES[normalized_id])
    payload = _load_profile_payload(normalized_id, repo_root=repo_root)
    if payload is None:
        raise ValueError(f"unknown visual_profile_id: {normalized_id}")
    return VisualProfile.from_mapping(payload)


def _load_profile_payload(
    profile_id: str,
    *,
    repo_root: str | Path | None = None,
) -> Mapping[str, Any] | None:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    candidates = [
        root / "resources" / "visual_profiles" / f"{profile_id}.yaml",
        root / "resources" / "visual_profiles" / f"{profile_id}.yml",
        root / "resources" / "visual_profiles" / f"{profile_id}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix.lower() == ".json":
            import json
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            with path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, Mapping):
            raise ValueError(f"visual profile file must contain a mapping: {path}")
        return payload
    return None


__all__ = ["BUILTIN_VISUAL_PROFILES", "resolve_visual_profile"]
