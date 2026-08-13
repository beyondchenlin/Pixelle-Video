import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_package_does_not_publish_missing_console_entry_points() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "scripts" not in project["project"]


def test_docker_installs_browser_inside_project_environment() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "uv run playwright install --with-deps chromium" in dockerfile
    assert "    playwright install --with-deps chromium" not in dockerfile


def test_source_installers_install_and_verify_both_locked_runtimes() -> None:
    for relative_path in (
        "scripts/install-runtime-dependencies.ps1",
        "scripts/install-runtime-dependencies.sh",
    ):
        script = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

        assert "uv sync --frozen" in script
        assert "npm ci --omit=dev" in script
        assert "PUPPETEER_CACHE_DIR" in script
        assert "PUPPETEER_SKIP_DOWNLOAD" in script
        assert "PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD" in script
        assert "browsers install chrome" in script
        assert "resolveBrowserExecutable()" in script
        assert script.index("npm ci") < script.index("browsers install chrome")
        assert script.index("browsers install chrome") < script.index(
            "resolveBrowserExecutable()"
        )
        assert "git rev-parse" not in script
        assert "22.12.0" in script


def test_docker_bundles_locked_hyperframes_runtime_and_runs_as_non_root() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM node:24.12.0-bookworm-slim AS hyperframes-runtime" in dockerfile
    assert "COPY tools/hyperframes_bridge/package.json" in dockerfile
    assert "npm ci --omit=dev" in dockerfile
    assert "PUPPETEER_CACHE_DIR" in dockerfile
    assert "PUPPETEER_SKIP_DOWNLOAD" in dockerfile
    assert "PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD" in dockerfile
    assert "for attempt in 1 2 3" in dockerfile
    assert "browsers install chrome" in dockerfile
    assert dockerfile.index("npm ci --omit=dev") < dockerfile.index(
        "browsers install chrome"
    )
    assert "resolveBrowserExecutable()" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER pixelle" in dockerfile
    assert 'Acquire::Retries "5"' in dockerfile
    assert "apt-get install -y --no-install-recommends" in dockerfile
    assert dockerfile.index("USER pixelle") < dockerfile.rindex(
        "resolveBrowserExecutable()"
    )


def test_windows_portable_package_bundles_and_verifies_hyperframes_runtime() -> None:
    builder = (PROJECT_ROOT / "packaging/windows/build.py").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "packaging/windows/config/build_config.yaml").read_text(
        encoding="utf-8"
    )
    launcher = (PROJECT_ROOT / "packaging/windows/templates/start.bat").read_text(
        encoding="utf-8"
    )

    assert "def download_node" in builder
    assert "def extract_node" in builder
    assert "def install_hyperframes_dependencies" in builder
    assert 'tempfile.TemporaryDirectory(prefix="pixelle-node-")' in builder
    assert 'shutil.copy2(node_executable, target_dir / "node.exe")' in builder
    assert 'shutil.copy2(license_file, target_dir / "LICENSE")' in builder
    assert "configured_output_dir.resolve()" in builder
    assert '"install", "-e"' not in builder
    assert '"--link-mode"' in builder
    assert '"copy"' in builder
    assert 'portable_project_path = r"..\\..\\Pixelle-Video"' in builder
    assert "def _extended_length_path" in builder
    assert "def _remove_existing_build_directory" in builder
    assert "resolved_build_dir.parent != resolved_output_dir" in builder
    assert "onerror=retry_windows_removal" in builder
    assert "walk_root = self._extended_length_path(self.build_dir)" in builder
    assert '"ci",' in builder
    assert "PUPPETEER_CACHE_DIR" in builder
    assert "resolveBrowserExecutable()" in builder
    assert "node-v24.12.0-win-x64.zip" in config
    assert "9c125f61ae947b52e779095830f9cac267846a043ef7192183c84016aaad2812" in config
    assert "tools\\node" in launcher
    assert "PUPPETEER_CACHE_DIR" in launcher
    assert ".as_posix()" in builder
    assert '"tools/hyperframes_bridge/.cache"' in config


def test_hyperframes_lock_uses_audited_zip_extractor_graph() -> None:
    import json

    lock = json.loads(
        (PROJECT_ROOT / "tools/hyperframes_bridge/package-lock.json").read_text(
            encoding="utf-8"
        )
    )

    assert lock["packages"][""]["dependencies"] == {
        "@hyperframes/producer": "0.7.107",
        "puppeteer": "25.6.0",
        "yauzl": "3.4.0",
    }
    assert "node_modules/extract-zip" not in lock["packages"]
