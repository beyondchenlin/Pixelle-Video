from pathlib import Path
from typing import Iterable


class FontResolver:
    APPLICATION_ROOT = Path(__file__).resolve().parents[2]
    DEFAULT_CANDIDATE_DIRS = (
        Path("fonts"),
        Path("font"),
        Path("resource/fonts"),
        Path("resources/hyperframes/runtime/fonts/assets"),
    )

    def __init__(self, candidate_dirs: Iterable[str | Path] | None = None) -> None:
        if candidate_dirs is None:
            self.candidate_dirs = tuple(
                self.APPLICATION_ROOT / candidate_dir
                for candidate_dir in self.DEFAULT_CANDIDATE_DIRS
            )
        else:
            self.candidate_dirs = tuple(Path(candidate_dir) for candidate_dir in candidate_dirs)

    def resolve_fontsdir(self, font_file: str | Path | None = None) -> Path | None:
        if font_file is not None:
            font_path = Path(font_file)
            if not font_path.is_absolute():
                font_path = self.APPLICATION_ROOT / font_path
            if font_path.is_file():
                return font_path.resolve().parent

        for candidate_dir in self.candidate_dirs:
            if candidate_dir.is_dir():
                return candidate_dir.resolve()

        return None
