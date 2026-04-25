from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

FONT_FILE_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
DEFAULT_FONT_SEARCH_DIRS = (
    Path("fonts"),
    Path("font"),
    Path("resource/fonts"),
)


@dataclass(frozen=True)
class FontOption:
    family: str
    path: Path


def font_path_for_payload(path: str | Path) -> str:
    font_path = Path(path)
    return font_path.as_posix()


def resolve_font_file(font_file: str | Path | None) -> Path | None:
    if font_file is None:
        return None
    font_path = Path(font_file)
    if font_path.is_file():
        return font_path
    resolved = font_path.resolve()
    if resolved.is_file():
        return resolved
    return None


def discover_font_options(
    candidate_dirs: Iterable[str | Path] | None = None,
) -> list[FontOption]:
    font_dirs = tuple(Path(candidate) for candidate in (candidate_dirs or DEFAULT_FONT_SEARCH_DIRS))
    options_by_family: dict[str, FontOption] = {}
    for font_dir in font_dirs:
        if not font_dir.is_dir():
            continue
        for font_file in sorted(font_dir.rglob("*"), key=lambda path: path.as_posix().casefold()):
            if not font_file.is_file() or font_file.suffix.lower() not in FONT_FILE_EXTENSIONS:
                continue
            family = font_family_from_file(font_file)
            if not family:
                continue
            options_by_family.setdefault(
                family.casefold(),
                FontOption(family=family, path=font_file),
            )

    return sorted(options_by_family.values(), key=lambda option: option.family.casefold())


def discover_font_families(
    candidate_dirs: Iterable[str | Path] | None = None,
) -> list[str]:
    return [option.family for option in discover_font_options(candidate_dirs)]


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
