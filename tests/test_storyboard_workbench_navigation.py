import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _PageSpec:
    path: str
    title: str
    icon: str
    default: bool = False


def _load_web_app():
    module_path = Path(__file__).resolve().parents[1] / "web" / "app.py"
    spec = importlib.util.spec_from_file_location("web_app_navigation_test_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["web_app_navigation_test_module"] = module
    return module


def test_navigation_registers_storyboard_workbench_page():
    web_app = _load_web_app()

    pages = web_app.build_navigation_pages(
        page_factory=lambda path, **kwargs: _PageSpec(
            path=path,
            title=kwargs["title"],
            icon=kwargs["icon"],
            default=kwargs.get("default", False),
        )
    )

    assert pages == [
        _PageSpec("pages/1_🎬_Home.py", title="Home", icon="🎬", default=True),
        _PageSpec("pages/2_📚_History.py", title="History", icon="📚"),
        _PageSpec("pages/3_IP_Design_Workbench.py", title="Visual Signature", icon="🎭"),
        _PageSpec("pages/4_🧭_Storyboard_Workbench.py", title="Workbench", icon="🧭"),
    ]
