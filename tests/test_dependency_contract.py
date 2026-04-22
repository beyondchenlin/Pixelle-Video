from pathlib import Path
import tomllib

from pixelle_video.models.storyboard import StoryboardConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_hyperframes_alignment_dependency_is_not_optional():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    base_dependencies = pyproject["project"]["dependencies"]

    default_alignment_engine = StoryboardConfig(
        media_width=1080,
        media_height=1920,
    ).subtitle_alignment_engine

    assert default_alignment_engine == "qwen_forced_aligner"
    assert "qwen-asr" in base_dependencies
