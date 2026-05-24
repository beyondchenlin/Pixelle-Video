import ast
from pathlib import Path

GENERATION_LLM_CALL_FILES = [
    Path("pixelle_video/utils/content_generators.py"),
    Path("pixelle_video/utils/style_resolution.py"),
    Path("pixelle_video/services/content_world_planner.py"),
    Path("pixelle_video/services/script_generation.py"),
    Path("pixelle_video/services/storyboard_generation.py"),
    Path("pixelle_video/services/storyboard_planner.py"),
    Path("pixelle_video/services/ip_usage_planner.py"),
    Path("pixelle_video/pipelines/asset_based.py"),
    Path("api/routers/llm.py"),
    Path("web/components/style_config.py"),
]

API_GENERATION_LLM_CALL_FILES = [
    Path("api/routers/content.py"),
    Path("web/components/style_config.py"),
]

API_GENERATION_FUNCTIONS = {
    "generate_narrations_from_topic",
    "generate_styled_image_prompt_batch",
    "generate_title",
}


def _is_generation_llm_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id == "llm_service"
    if isinstance(node.func, ast.Attribute):
        if node.func.attr == "_llm":
            return True
        if node.func.attr != "llm":
            return False
        value = node.func.value
        if isinstance(value, ast.Name):
            return value.id == "pixelle_video"
        if not isinstance(value, ast.Attribute) or value.attr != "core":
            return False
        return isinstance(value.value, ast.Name) and value.value.id == "self"
    return False


def _is_constructor_method_call(node: ast.Call, *, class_name: str, method_name: str) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != method_name:
        return False
    receiver = node.func.value
    return (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == class_name
    )


def _is_api_generation_llm_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id in API_GENERATION_FUNCTIONS
    return _is_constructor_method_call(
        node,
        class_name="ContentWorldPlanner",
        method_name="plan",
    ) or _is_constructor_method_call(
        node,
        class_name="ImagePromptComposer",
        method_name="compose",
    )


def _generation_llm_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_generation_llm_call(node)
    ]


def _api_generation_llm_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_api_generation_llm_call(node)
    ]


def _keyword_names(call: ast.Call) -> set[str]:
    return {keyword.arg for keyword in call.keywords if keyword.arg is not None}


def test_generation_llm_calls_pass_trace_context_and_recorder():
    missing: list[str] = []
    for path in GENERATION_LLM_CALL_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for call in _generation_llm_calls(tree):
            keyword_names = _keyword_names(call)
            if {"trace_context", "trace_recorder"} <= keyword_names:
                continue
            missing.append(f"{path}:{call.lineno}")

    assert missing == []


def test_api_generation_llm_calls_pass_trace_context_and_recorder():
    missing: list[str] = []
    for path in API_GENERATION_LLM_CALL_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for call in _api_generation_llm_calls(tree):
            keyword_names = _keyword_names(call)
            if {"trace_context", "trace_recorder"} <= keyword_names:
                continue
            missing.append(f"{path}:{call.lineno}")

    assert missing == []


def test_web_prompt_prefix_generation_uses_rendered_template_metadata():
    path = Path("web/components/style_config.py")
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    prompt_builder_calls: list[str] = []
    rendered_template_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "build_prompt_prefix_generation_prompt":
            prompt_builder_calls.append(f"{path}:{node.lineno}")
        if node.func.id == "render_prompt_prefix_generation_prompt":
            rendered_template_calls += 1

    assert prompt_builder_calls == []
    assert rendered_template_calls >= 1


def test_untraced_llm_call_escape_hatch_does_not_exist_in_production_code():
    offenders: list[str] = []
    for root in (Path("pixelle_video"), Path("api"), Path("web")):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8-sig")
            if "allow_untraced_" + "llm_call" in text:
                offenders.append(str(path))

    assert offenders == []
