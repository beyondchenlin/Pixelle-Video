from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

FONT_FILE_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
DEFAULT_FONT_SEARCH_DIRS = (
    Path("resources/hyperframes/runtime/fonts/assets"),
    Path("fonts"),
    Path("font"),
    Path("resource/fonts"),
)
APPLICATION_ROOT = Path(__file__).resolve().parents[2]
FONT_FAMILY_ALIASES = {
    "noto sans cjk sc": "Noto Sans SC",
}


@dataclass(frozen=True)
class FontOption:
    family: str
    path: Path


def canonical_font_family_name(family: str) -> str:
    cleaned = str(family or "").strip()
    return FONT_FAMILY_ALIASES.get(cleaned.casefold(), cleaned)


def font_path_for_payload(path: str | Path) -> str:
    font_path = Path(path)
    return font_path.as_posix()


def resolve_font_file(font_file: str | Path | None) -> Path | None:
    if font_file is None:
        return None
    font_path = Path(font_file)
    if not font_path.is_absolute():
        font_path = APPLICATION_ROOT / font_path
    if font_path.is_file():
        return font_path.resolve()
    return None


def discover_font_options(
    candidate_dirs: Iterable[str | Path] | None = None,
) -> list[FontOption]:
    font_dirs = tuple(
        Path(candidate)
        for candidate in (
            candidate_dirs
            if candidate_dirs is not None
            else (APPLICATION_ROOT / item for item in DEFAULT_FONT_SEARCH_DIRS)
        )
    )
    options_by_path: dict[str, FontOption] = {}
    for font_dir in font_dirs:
        if not font_dir.is_dir():
            continue
        for font_file in sorted(font_dir.rglob("*"), key=lambda path: path.as_posix().casefold()):
            if not font_file.is_file() or font_file.suffix.lower() not in FONT_FILE_EXTENSIONS:
                continue
            family = font_family_from_file(font_file)
            if not family:
                continue
            options_by_path.setdefault(
                str(font_file.resolve()).casefold(),
                FontOption(family=family, path=font_file),
            )

    return sorted(
        options_by_path.values(),
        key=lambda option: (option.family.casefold(), option.path.as_posix().casefold()),
    )


def discover_font_families(
    candidate_dirs: Iterable[str | Path] | None = None,
) -> list[str]:
    families_by_key: dict[str, str] = {}
    for option in discover_font_options(candidate_dirs):
        families_by_key.setdefault(option.family.casefold(), option.family)
    return sorted(families_by_key.values(), key=str.casefold)


def font_family_from_file(path: Path) -> str:
    try:
        from PIL import ImageFont

        family, _style = ImageFont.truetype(str(path), size=12).getname()
        cleaned = str(family).strip()
        if cleaned:
            return cleaned
    except Exception:
        pass

    return path.stem.strip()


def missing_font_characters(path: Path, text: str) -> tuple[str, ...]:
    """Return printable characters that resolve to the font's missing-glyph box."""

    try:
        from PIL import ImageFont

        font = ImageFont.truetype(str(path), size=64)
    except (OSError, ValueError):
        return tuple(sorted({character for character in text if character.isprintable()}))

    sentinel_signatures = {
        _glyph_signature(font, "\u0378"),
        _glyph_signature(font, "\U0010ffff"),
    }
    missing = {
        character
        for character in text
        if character.isprintable()
        and not character.isspace()
        and _glyph_signature(font, character) in sentinel_signatures
    }
    return tuple(sorted(missing))


def _glyph_signature(font, character: str) -> tuple[tuple[int, int], bytes]:
    mask = font.getmask(character, mode="L")
    return mask.size, bytes(mask)


def build_font_face_css(font_path_str: str) -> str | None:
    """Build a ``@font-face`` rule with base64-embedded font data.

    Returns ``None`` when the font file cannot be read (missing / empty).
    """
    font_path = resolve_font_file(font_path_str)
    if font_path is None:
        return None

    try:
        raw = font_path.read_bytes()
        if not raw:
            return None
    except OSError:
        return None

    b64 = base64.b64encode(raw).decode("ascii")
    suffix = font_path.suffix.lower()
    fmt_map = {
        ".ttf": "truetype",
        ".otf": "opentype",
        ".woff": "woff",
        ".woff2": "woff2",
    }
    font_format = fmt_map.get(suffix, "truetype")
    family = font_family_from_file(font_path)

    return (
        "@font-face {\n"
        f'  font-family: "{family}";\n'
        f'  src: url(data:font/{font_format};base64,{b64}) format("{font_format}");\n'
        "  font-weight: normal;\n"
        "  font-style: normal;\n"
        "}"
    )
