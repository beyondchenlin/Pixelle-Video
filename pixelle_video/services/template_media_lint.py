from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_STANDARD_MEDIA_PLACEHOLDER_PATTERN = re.compile(
    r"\{\{\s*pixelle_media_layer\s*\}\}"
)
_RAW_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*image\s*\}\}", re.IGNORECASE)
_BARE_MEDIA_ELEMENT_PATTERN = re.compile(
    r"<(?:img|image|video)\b[^>]*(?:src|href)\s*=\s*['\"]?\s*\{\{\s*image\s*\}\}",
    re.IGNORECASE,
)
_BACKGROUND_IMAGE_PATTERN = re.compile(
    r"background(?:-image)?\s*:[^;{}]*\{\{\s*image\s*\}\}",
    re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_PROTECTED_MEDIA_RULE_PATTERN = re.compile(
    r"([^{}]*(?:\.pixelle-media-layer|\.pixelle-media-box|\.pixelle-media)[^{}]*)"
    r"\{([^{}]*)\}",
    re.IGNORECASE | re.DOTALL,
)
_PROTECTED_GEOMETRY_DECLARATION_PATTERN = re.compile(
    r"(?:^|;)\s*(?:position|inset|left|right|top|bottom|width|height|"
    r"min-width|min-height|max-width|max-height|object-fit)\s*:",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TemplateMediaLintResult:
    path: Path
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_media_template(path: str | Path) -> TemplateMediaLintResult:
    template_path = Path(path)
    html = template_path.read_text(encoding="utf-8")
    lint_source = _HTML_COMMENT_PATTERN.sub("", html)
    errors: list[str] = []

    if not _STANDARD_MEDIA_PLACEHOLDER_PATTERN.search(lint_source):
        errors.append("missing {{pixelle_media_layer}} standard media placeholder")

    if _BARE_MEDIA_ELEMENT_PATTERN.search(lint_source):
        errors.append("bare {{image}} media element bypasses standard media layer")

    if _BACKGROUND_IMAGE_PATTERN.search(lint_source):
        errors.append("background-image using {{image}} bypasses standard media layer")

    if _RAW_IMAGE_PLACEHOLDER_PATTERN.search(lint_source):
        errors.append("raw {{image}} bypasses standard media layer")

    for selector, declarations in _PROTECTED_MEDIA_RULE_PATTERN.findall(lint_source):
        if _PROTECTED_GEOMETRY_DECLARATION_PATTERN.search(declarations):
            compact_selector = " ".join(selector.split())
            errors.append(
                "template overrides protected standard media geometry: "
                f"{compact_selector}"
            )

    return TemplateMediaLintResult(path=template_path, errors=errors)
