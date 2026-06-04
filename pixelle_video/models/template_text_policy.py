from __future__ import annotations

from enum import Enum
from typing import Any, Final


class TemplateTextPolicy(str, Enum):
    """Single source of truth for template body/caption text routing.

    The old code kept the same policy set in both storyboard models and the
    visual materializer.  That made renderer branches drift from one
    another.  Keep the public string values stable, but centralize validation
    and routing here.
    """

    CAPTION_RENDERER = "caption_renderer"
    TEMPLATE_BODY = "template_body"
    NONE = "none"
    EXPLICIT_BOTH = "explicit_both"


DEFAULT_TEMPLATE_TEXT_POLICY: Final[str] = TemplateTextPolicy.CAPTION_RENDERER.value
VALID_TEMPLATE_TEXT_POLICIES: Final[frozenset[str]] = frozenset(
    item.value for item in TemplateTextPolicy
)


def normalize_template_text_policy(
    value: Any,
    *,
    default: str = DEFAULT_TEMPLATE_TEXT_POLICY,
) -> str:
    """Return a validated public template text policy string."""

    if value is None:
        value = default
    normalized = str(value).strip()
    if not normalized:
        normalized = default
    if normalized not in VALID_TEMPLATE_TEXT_POLICIES:
        raise ValueError(
            "template_text_policy must be one of "
            f"{sorted(VALID_TEMPLATE_TEXT_POLICIES)}"
        )
    return normalized


def resolve_template_body_text(template_body_text: Any, text_policy: Any) -> str:
    """Return text that should be rendered inside the HTML/template body."""

    policy = normalize_template_text_policy(text_policy)
    if policy in {
        TemplateTextPolicy.TEMPLATE_BODY.value,
        TemplateTextPolicy.EXPLICIT_BOTH.value,
    }:
        return str(template_body_text or "")
    return ""


def resolve_caption_renderer_text(caption_text: Any, text_policy: Any) -> str:
    """Return text that should be owned by the external caption renderer.

    This fixes a subtle layered-template bug where `template_text_policy="none"`
    could still render captions because `caption_text` was passed explicitly.
    """

    policy = normalize_template_text_policy(text_policy)
    if policy in {
        TemplateTextPolicy.CAPTION_RENDERER.value,
        TemplateTextPolicy.EXPLICIT_BOTH.value,
    }:
        return str(caption_text or "")
    return ""


def resolve_template_text_policy_for_body_override(
    configured_policy: Any,
    template_body_text_override: Any,
) -> str:
    """Resolve legacy per-call body override without losing explicit policy intent.

    Historical staged rendering passes an explicit empty string to mean
    "render a shell and let captions be handled elsewhere".  A non-empty
    override means the caller is explicitly asking for body text.  Normal
    calls keep the configured policy.
    """

    if template_body_text_override is None:
        return normalize_template_text_policy(configured_policy)
    if str(template_body_text_override or ""):
        return TemplateTextPolicy.TEMPLATE_BODY.value
    return TemplateTextPolicy.CAPTION_RENDERER.value


__all__ = [
    "DEFAULT_TEMPLATE_TEXT_POLICY",
    "TemplateTextPolicy",
    "VALID_TEMPLATE_TEXT_POLICIES",
    "normalize_template_text_policy",
    "resolve_caption_renderer_text",
    "resolve_template_body_text",
    "resolve_template_text_policy_for_body_override",
]
