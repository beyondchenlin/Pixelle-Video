from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_quick_create_bgm_is_collapsed_before_middle_style_config():
    source = (PROJECT_ROOT / "web" / "pipelines" / "standard.py").read_text(encoding="utf-8")

    left_column_source = source.split("with left_col:", 1)[1].split("with middle_col:", 1)[0]
    middle_column_source = source.split("with middle_col:", 1)[1].split("with right_col:", 1)[0]

    assert "render_bgm_section(" not in left_column_source
    assert "bgm_params = render_bgm_section(collapsible=True)" in middle_column_source
    assert middle_column_source.index("render_bgm_section") < middle_column_source.index(
        "render_style_config"
    )


def test_collapsed_bgm_section_renders_without_nested_expanders():
    script = """
import pixelle_video.utils.os_util as os_util
from web.components import content_input

translations = {
    "section.bgm": "BGM",
    "help.feature_description": "Help",
    "help.what": "What",
    "help.how": "How",
    "bgm.what": "Adds music.",
    "bgm.how": "Choose a file.",
    "bgm.none": "None",
    "bgm.volume": "Volume",
    "bgm.volume_help": "Adjust volume.",
    "bgm.preview": "Preview",
}

content_input.tr = lambda key, **kwargs: translations.get(key, key)
os_util.list_resource_files = lambda _kind: ["default.mp3"]

content_input.render_bgm_section(collapsible=True)
"""

    at = AppTest.from_string(script)
    at.run()

    assert len(at.exception) == 0
    assert len(at.expander) == 1
    assert at.expander[0].label == "BGM"
