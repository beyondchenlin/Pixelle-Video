import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STYLE_CONFIG_PATH = PROJECT_ROOT / "web" / "components" / "style_config.py"


def _find_radio_call(function_name: str, key_value: str) -> ast.Call:
    tree = ast.parse(STYLE_CONFIG_PATH.read_text(encoding="utf-8"))

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue

        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            if not isinstance(call.func, ast.Attribute) or call.func.attr != "radio":
                continue

            for keyword in call.keywords:
                if keyword.arg == "key" and ast.literal_eval(keyword.value) == key_value:
                    return call

    raise AssertionError(f"st.radio call with key={key_value!r} was not found")


def _keyword_literal(call: ast.Call, name: str):
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.literal_eval(keyword.value)
    raise AssertionError(f"keyword {name!r} was not found")


def test_tts_split_mode_radio_uses_same_horizontal_layout_as_audio_strategy():
    audio_strategy_radio = _find_radio_call(
        "render_tts_audio_strategy_selector",
        "tts_audio_strategy_select",
    )
    split_mode_radio = _find_radio_call(
        "render_tts_split_settings",
        "tts_split_mode_select",
    )

    assert _keyword_literal(audio_strategy_radio, "horizontal") is True
    assert _keyword_literal(split_mode_radio, "horizontal") is True
