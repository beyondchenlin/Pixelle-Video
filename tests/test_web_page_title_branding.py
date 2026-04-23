import ast
from pathlib import Path


EXPECTED_BROWSER_TITLES = {
    "web/app.py": "懒人同城 - AI Video Generator",
    "web/pages/1_🎬_Home.py": "Home - 懒人同城",
    "web/pages/2_📚_History.py": "History - 懒人同城",
}


def _extract_page_title(path: Path) -> str | None:
    module = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "set_page_config":
            continue

        for keyword in node.keywords:
            if keyword.arg == "page_title" and isinstance(keyword.value, ast.Constant):
                return keyword.value.value

    return None


def test_streamlit_pages_replace_only_brand_name_in_browser_title():
    project_root = Path(__file__).resolve().parent.parent
    offenders = {}
    for relative_path, expected_title in EXPECTED_BROWSER_TITLES.items():
        path = project_root / relative_path
        page_title = _extract_page_title(path)
        if page_title != expected_title:
            offenders[relative_path] = page_title

    assert offenders == {}
