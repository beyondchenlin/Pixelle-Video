import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class _PageSpec:
    path: str
    title: str
    icon: str
    default: bool = False


class _FakeUI:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.infos: list[str] = []

    def markdown(self, message, **_kwargs):
        self.markdowns.append(message)

    def caption(self, message):
        self.captions.append(message)

    def info(self, message):
        self.infos.append(message)


def _load_web_app():
    module_path = Path(__file__).resolve().parents[1] / "web" / "app.py"
    spec = importlib.util.spec_from_file_location("web_app_ip_design_test_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["web_app_ip_design_test_module"] = module
    return module


def _load_ip_design_page():
    pages_dir = Path(__file__).resolve().parents[1] / "web" / "pages"
    module_path = pages_dir / "3_IP_Design_Workbench.py"
    spec = importlib.util.spec_from_file_location("ip_design_workbench_page_test_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["ip_design_workbench_page_test_module"] = module
    return module


def test_navigation_registers_ip_design_before_storyboard_workbench():
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
        _PageSpec("pages/3_IP_Design_Workbench.py", title="IP Design", icon="🎭"),
        _PageSpec("pages/4_🧭_Storyboard_Workbench.py", title="Workbench", icon="🧭"),
    ]


def test_ip_design_page_renders_standalone_workbench(monkeypatch):
    page = _load_ip_design_page()
    fake_ui = _FakeUI()
    client = object()
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        page,
        "resolve_ip_design_client",
        lambda _session_state, pixelle_video=None: client,
    )
    monkeypatch.setattr(page, "resolve_workbench_client_mode", lambda _session_state: "http")

    def fake_renderer(*, ip_design_client=None, ui=None, translate=None):
        calls.append(
            {
                "ip_design_client": ip_design_client,
                "ui": ui,
                "translate": translate,
            }
        )

    page.render_ip_design_workbench_page(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_renderer=fake_renderer,
    )

    rendered = "\n".join(fake_ui.markdowns + fake_ui.captions + fake_ui.infos)
    assert "ip_design.page.title" in rendered
    assert "ip_design.page.caption" in rendered
    assert calls == [
        {
            "ip_design_client": client,
            "ui": fake_ui,
            "translate": page.tr,
        }
    ]


def test_formal_ip_design_ui_sources_do_not_import_transport_helpers():
    project_root = Path(__file__).resolve().parents[1]
    forbidden_tokens = (
        "web.utils.asset_bible_api",
        "httpx",
        "DEFAULT_API_BASE_URL",
        "localhost:8001",
    )
    source_paths = [
        project_root / "web" / "pages" / "3_IP_Design_Workbench.py",
        project_root / "web" / "components" / "ip_design_workbench.py",
    ]

    offenders: dict[str, list[str]] = {}
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        matches = [token for token in forbidden_tokens if token in source]
        if matches:
            offenders[str(path.relative_to(project_root))] = matches

    assert offenders == {}
