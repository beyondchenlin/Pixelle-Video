import re
from pathlib import Path

PROMPT_MODULE_DIR = Path("pixelle_video/prompts")
PROMPT_TEMPLATE_DIR = PROMPT_MODULE_DIR / "templates"
INLINE_PROMPT_CONSTANT_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*PROMPT[A-Z0-9_]*\s*=\s*(?:f|r|fr|rf)?[\"']{3}",
    re.MULTILINE,
)
LONG_FORM_MARKDOWN_PROMPT_RE = re.compile(
    r"(you are|return json|output format|requirements|instructions|不要|输出|生成|文案)",
    re.IGNORECASE,
)


def test_prompt_modules_do_not_own_long_form_prompt_bodies():
    offenders = []
    for path in sorted(PROMPT_MODULE_DIR.glob("*.py")):
        if path.name in {"__init__.py", "template_loader.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if INLINE_PROMPT_CONSTANT_RE.search(text):
            offenders.append(str(path))

    assert offenders == []


def test_long_form_markdown_prompt_bodies_live_only_in_template_registry():
    offenders = []
    for path in sorted(PROMPT_MODULE_DIR.rglob("*.md")):
        if PROMPT_TEMPLATE_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        if len(text.strip()) > 500 and LONG_FORM_MARKDOWN_PROMPT_RE.search(text):
            offenders.append(str(path))

    assert offenders == []
