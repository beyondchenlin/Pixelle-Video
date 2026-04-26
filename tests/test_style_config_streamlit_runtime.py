from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STYLE_CONFIG_RELATIVE_PATH = Path("web/components/style_config.py")


def _read_current_style_config_source() -> str:
    return (PROJECT_ROOT / STYLE_CONFIG_RELATIVE_PATH).read_text(encoding="utf-8")


def test_read_style_config_source_prefers_current_worktree_file(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    style_config_path = repo_root / STYLE_CONFIG_RELATIVE_PATH
    style_config_path.parent.mkdir(parents=True)
    style_config_path.write_text("tracked version\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.name", "Pixelle Test"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "pixelle-test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "add", STYLE_CONFIG_RELATIVE_PATH.as_posix()], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    style_config_path.write_text("current worktree version\n", encoding="utf-8")

    monkeypatch.setattr(sys.modules[__name__], "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(sys.modules[__name__], "STYLE_CONFIG_RELATIVE_PATH", STYLE_CONFIG_RELATIVE_PATH)

    assert _read_current_style_config_source() == "current worktree version\n"


def test_render_style_config_uses_real_streamlit_popovers():
    style_config_source = _read_current_style_config_source()

    with tempfile.TemporaryDirectory() as temp_dir:
        module_path = Path(temp_dir) / "style_config_snapshot.py"
        module_path.write_text(style_config_source, encoding="utf-8")

        script = """
import importlib.util
import sys
from pathlib import Path
import streamlit as st
import pixelle_video.utils.template_util as template_util
import pixelle_video.services.frame_html as frame_html

module_path = Path(r"__MODULE_PATH__")
spec = importlib.util.spec_from_file_location("style_config_snapshot", module_path)
style_config = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = style_config
spec.loader.exec_module(style_config)

st.session_state['template_type_selector'] = 'image'
st.session_state['template_media_type'] = 'image'
st.session_state['template_requires_media'] = True

style_config.tr = lambda key, **kwargs: key
style_config.get_language = lambda: 'en_US'
style_config.config_manager.get_comfyui_config = lambda: {
    'tts': {
        'inference_mode': 'local',
        'local': {'voice': 'zh-CN-YunjianNeural', 'speed': 1.2},
        'comfyui': {},
    },
    'image': {},
    'video': {},
}
style_config.render_render_backend_selector = lambda: 'render_backend'
style_config.render_tts_audio_strategy_selector = lambda: 'auto'
style_config.render_storyboard_planning_guide = lambda: None
style_config.render_storyboard_preview = lambda _snapshot: []
style_config._render_image_prompt_prefix_library = lambda **_kwargs: ''
style_config.config_manager.get_storyboard_world_preset_library = lambda: {
    'default_world_preset_id': 'neutral_knowledge_storyboard',
    'items': [{'preset_id': 'neutral_knowledge_storyboard', 'display_name': 'Neutral'}],
}
style_config.config_manager.get_storyboard_shot_preset_library = lambda: {
    'default_shot_preset_id': 'balanced_explainer',
    'items': [{'preset_id': 'balanced_explainer', 'display_name': 'Balanced'}],
}

template_util.get_template_type = lambda _template_name: 'image'
template_util.get_templates_grouped_by_size_and_type = lambda _template_type: {
    '1080x1920': [
        type('TemplateInfo', (), {
            'template_path': '1080x1920/image_default.html',
            'display_info': type('DisplayInfo', (), {
                'name': 'image_default',
                'orientation': 'portrait',
                'width': 1080,
                'height': 1920,
            })(),
        })()
    ]
}
template_util.parse_template_size = lambda _path: (1080, 1920)
template_util.resolve_template_path = lambda path: path

class _FakeFrameGenerator:
    def __init__(self, _template_path):
        self._template_path = _template_path
    def parse_template_parameters(self):
        return {}
    def get_media_size(self):
        return (1080, 1920)

frame_html.HTMLFrameGenerator = _FakeFrameGenerator

class _FakeMedia:
    @staticmethod
    def list_workflows():
        return [{'display_name': 'Image Default', 'key': 'selfhost/image_z_image_turbo.json'}]

class _FakeVideo:
    config = {'template': {}}
    media = _FakeMedia()

style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)
"""
        script = script.replace("__MODULE_PATH__", str(module_path))

        at = AppTest.from_string(script)
        at.run()

    assert len(at.exception) == 0

    popovers = [
        node for node in at.main if type(node).__name__ == "Block" and getattr(node, "type", None) == "popover"
    ]
    assert len(popovers) == 2
    assert [popover.proto.popover.label for popover in popovers] == [
        "help.feature_description",
        "help.feature_description",
    ]

    popover_markdown_groups = {
        tuple(markdown.value for markdown in popover.markdown)
        for popover in popovers
    }
    assert popover_markdown_groups == {
        ("**help.what**", "template.what", "**help.how**", "template.how"),
        ("**help.what**", "style.workflow_what", "**help.how**", "style.workflow_how"),
    }
