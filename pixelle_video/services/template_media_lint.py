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

    return TemplateMediaLintResult(path=template_path, errors=errors)
