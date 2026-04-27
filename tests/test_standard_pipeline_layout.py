import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_module_ast(relative_path: str) -> ast.Module:
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    return ast.parse(source)


def test_bgm_component_lives_in_config_module_not_content_input():
    content_input_tree = _read_module_ast("web/components/content_input.py")
    standard_tree = _read_module_ast("web/pipelines/standard.py")

    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "render_bgm_section"
        for node in content_input_tree.body
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "web.components.bgm_config"
        and any(alias.name == "render_bgm_section" for alias in node.names)
        for node in standard_tree.body
    )


def test_quick_create_renders_bgm_before_style_config_in_middle_column():
    tree = _read_module_ast("web/pipelines/standard.py")
    render_method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "render"
    )
    middle_column_block = next(
        node
        for node in render_method.body
        if isinstance(node, ast.With)
        and isinstance(node.items[0].context_expr, ast.Name)
        and node.items[0].context_expr.id == "middle_col"
    )

    call_names = [
        call.func.id
        for call in ast.walk(ast.Module(body=middle_column_block.body, type_ignores=[]))
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    ]

    assert call_names.index("render_bgm_section") < call_names.index("render_style_config")


def test_quick_create_passes_storyboard_prompt_language_to_style_config():
    tree = _read_module_ast("web/pipelines/standard.py")
    render_style_call = next(
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "render_style_config"
    )

    assert any(keyword.arg == "storyboard_prompt_language" for keyword in render_style_call.keywords)


def test_collapsed_bgm_section_renders_without_nested_expanders():
    script = """
import pixelle_video.utils.os_util as os_util
from web.components import bgm_config

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

bgm_config.tr = lambda key, **kwargs: translations.get(key, key)
os_util.list_resource_files = lambda _kind: ["default.mp3"]

bgm_config.render_bgm_section(collapsible=True)
"""

    at = AppTest.from_string(script)
    at.run()

    assert len(at.exception) == 0
    assert len(at.expander) == 1
    assert at.expander[0].label == "BGM"
