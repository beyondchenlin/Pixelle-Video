from pathlib import Path
from typing import Iterable


class FontResolver:
    DEFAULT_CANDIDATE_DIRS = (
        Path("fonts"),
        Path("font"),
        Path("resource/fonts"),
    )

    def __init__(self, candidate_dirs: Iterable[str | Path] | None = None) -> None:
        self.candidate_dirs = tuple(
            Path(candidate_dir)
            for candidate_dir in (
                candidate_dirs
                if candidate_dirs is not None
                else self.DEFAULT_CANDIDATE_DIRS
            )
        )

    def resolve_fontsdir(self, font_file: str | Path | None = None) -> Path | None:
        if font_file is not None:
            font_path = Path(font_file)
            if font_path.is_file():
                return font_path.parent

        for candidate_dir in self.candidate_dirs:
            if candidate_dir.is_dir():
                return candidate_dir

        return None
