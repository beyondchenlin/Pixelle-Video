import hashlib
import importlib.util
import tomllib
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_windows_builder_module():
    module_path = PROJECT_ROOT / "packaging/windows/build.py"
    spec = importlib.util.spec_from_file_location("pixelle_windows_builder", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        assert "PIXELLE_REQUIRE_PINNED_BROWSER" in script
        assert "PUPPETEER_EXECUTABLE_PATH" in script
        assert "PRODUCER_HEADLESS_SHELL_PATH" in script
        assert "npm run browser:install" in script
        assert "npm run runtime:verify" in script
        assert script.index("npm ci") < script.index("npm run browser:install")
        assert script.index("npm run browser:install") < script.index(
            "npm run runtime:verify"
        )
        assert "git rev-parse" not in script
        assert "22.12.0" in script


def test_docker_bundles_locked_hyperframes_runtime_and_runs_as_non_root() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert (
        "FROM node:24.12.0-bookworm-slim@sha256:"
        "7326fb2dbdce998edd72140946851be64ef4a643e8715e138ca467e8e9d92c99 "
        "AS hyperframes-runtime"
    ) in dockerfile
    assert (
        "FROM ghcr.io/astral-sh/uv:0.10.7@sha256:"
        "edd1fd89f3e5b005814cc8f777610445d7b7e3ed05361f9ddfae67bebfe8456a"
    ) in dockerfile
    assert (
        "FROM python:3.11.15-slim-bookworm@sha256:"
        "d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3"
    ) in dockerfile
    assert "COPY tools/hyperframes_bridge/package.json" in dockerfile
    assert "npm ci --omit=dev" in dockerfile
    assert "PUPPETEER_CACHE_DIR" in dockerfile
    assert "PUPPETEER_SKIP_DOWNLOAD" in dockerfile
    assert "PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD" in dockerfile
    assert "for attempt in 1 2 3" in dockerfile
    assert "npm run browser:install" in dockerfile
    assert dockerfile.index("npm ci --omit=dev") < dockerfile.index(
        "npm run browser:install"
    )
    assert "npm run runtime:verify" in dockerfile
    assert "node src/verify-runtime.mjs" in dockerfile
    assert "PIXELLE_REQUIRE_PINNED_BROWSER" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER pixelle" in dockerfile
    assert 'Acquire::Retries "5"' in dockerfile
    assert "apt-get install -y --no-install-recommends" in dockerfile
    assert dockerfile.index("USER pixelle") < dockerfile.rindex(
        "node src/verify-runtime.mjs"
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
    assert '"export"' in builder
    assert '"--frozen"' in builder
    assert '"--require-hashes"' in builder
    assert '"--no-deps"' in builder
    assert '"--no-emit-project"' in builder
    assert "Windows portable packages must be built on Windows" in builder
    assert "_find_suitable_python" not in builder
    assert 'portable_project_path = r"..\\..\\Pixelle-Video"' in builder
    assert "def _extended_length_path" in builder
    assert "def _remove_existing_build_directory" in builder
    assert "def _sha256_file" in builder
    assert "def _safe_extract_zip" in builder
    assert "def _install_uv_wheel" in builder
    assert "def _verify_ffmpeg_runtime" in builder
    assert '"-vsync"' in builder
    assert "FFmpeg runtime is incompatible with the current render graph" in builder
    assert ".read_bytes()" not in builder
    assert "extractall" not in builder
    assert "resolved_build_dir.parent != resolved_output_dir" in builder
    assert "onerror=retry_windows_removal" in builder
    assert "walk_root = self._extended_length_path(self.build_dir)" in builder
    assert '"ci",' in builder
    assert "PUPPETEER_CACHE_DIR" in builder
    assert 'build_browser_cache = self.cache_dir / f"puppeteer-{puppeteer_version}"' in builder
    assert 'build_chrome_cache = build_browser_cache / "chrome"' in builder
    assert "shutil.copytree(build_chrome_cache, target_browser_cache / \"chrome\")" in builder
    assert '"browser:install"' in builder
    assert '"runtime:verify"' in builder
    assert "PIXELLE_REQUIRE_PINNED_BROWSER" in builder
    assert "PUPPETEER_EXECUTABLE_PATH" in builder
    assert "PRODUCER_HEADLESS_SHELL_PATH" in builder
    assert "node-v24.12.0-win-x64.zip" in config
    assert "9c125f61ae947b52e779095830f9cac267846a043ef7192183c84016aaad2812" in config
    assert "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b" in config
    assert 'version: "8.1.2-34-g9b6c8969e0"' in config
    assert "autobuild-2026-08-12-13-15" in config
    assert "ffmpeg-n8.1.2-34-g9b6c8969e0-win64-gpl-8.1.zip" in config
    assert "0bfebe51fced76c6cd5a42420fc2fc6e4646f95a556c59b0d7d298fcc24c6849" in config
    assert "ffmpeg-master-latest" not in config
    assert "ad0d0ddd9f5407ad8699e3b20fe6c18406cd606336743e246b16914801cfd8b0" in config
    assert "get-pip.py" not in builder
    assert "pip_bootstrap:" not in config
    assert "tools\\node" in launcher
    assert r"PUPPETEER_CACHE_DIR=%~dp0tools\puppeteer" in launcher
    assert "PIXELLE_REQUIRE_PINNED_BROWSER" in launcher
    assert ".as_posix()" in builder
    assert '"tools/hyperframes_bridge/.cache"' in config
    assert '"docs/*"' in config
    assert '"tests"' in config
    assert '"HyperFrames"' in config
    assert '"scripts/*"' in config
    assert '("FAQ.md", "FAQ_CN.md")' in builder
    assert "Required runtime FAQ is missing" in builder
    assert '"scripts" / "launch_web.py"' in builder
    assert "Required runtime launcher is missing" in builder
    assert 'version: "0.10.7"' in config
    assert "playwright:" not in config


def test_windows_portable_extractor_rejects_zip_path_traversal(tmp_path: Path) -> None:
    module = _load_windows_builder_module()
    archive_path = tmp_path / "malicious.zip"
    extraction_root = tmp_path / "extract"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escaped.txt", "escaped")

    with pytest.raises(RuntimeError, match="Unsafe ZIP member path"):
        module.WindowsPackageBuilder._safe_extract_zip(archive_path, extraction_root)

    assert not (tmp_path / "escaped.txt").exists()


@pytest.mark.parametrize(
    "member_name",
    ["safe/file.txt:stream", "safe/NUL.txt", "safe/trailing. /file.txt"],
)
def test_windows_portable_extractor_rejects_windows_path_ambiguities(
    tmp_path: Path,
    member_name: str,
) -> None:
    module = _load_windows_builder_module()
    archive_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member_name, "unsafe")

    with pytest.raises(RuntimeError, match="Unsafe ZIP member path"):
        module.WindowsPackageBuilder._safe_extract_zip(
            archive_path,
            tmp_path / "extract",
        )


def test_windows_portable_hashes_large_files_incrementally(tmp_path: Path) -> None:
    module = _load_windows_builder_module()
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"pixelle" * 200_000)

    assert (
        module.WindowsPackageBuilder._sha256_file(artifact)
        == hashlib.sha256(artifact.read_bytes()).hexdigest()
    )


def test_golden_workflow_uses_the_locked_browser_instead_of_runner_chrome() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/render-golden-ci.yml").read_text(
        encoding="utf-8"
    )

    assert 'node-version: "24.12.0"' in workflow
    assert "PUPPETEER_CACHE_DIR" in workflow
    assert "PIXELLE_REQUIRE_PINNED_BROWSER" in workflow
    assert "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830" in workflow
    assert "hashFiles('tools/hyperframes_bridge/package-lock.json')" in workflow
    assert "npm run browser:install" in workflow
    assert "npm run runtime:verify" in workflow
    assert "/usr/bin/google-chrome" not in workflow
    assert "PUPPETEER_EXECUTABLE_PATH" not in workflow


def test_golden_workflow_covers_the_complete_hyperframes_render_chain() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/render-golden-ci.yml").read_text(
        encoding="utf-8"
    )

    for guarded_path in (
        "pixelle_video/services/hyperframes_*.py",
        "pixelle_video/services/layered_template_adapters/**",
        "pixelle_video/services/render_*.py",
        "pixelle_video/utils/filesystem.py",
        "tests/test_hyperframes_*.py",
        "tests/test_render_*.py",
    ):
        assert workflow.count(f'- "{guarded_path}"') == 2


def test_changed_runtime_workflows_pin_third_party_actions_by_commit() -> None:
    for workflow_name in ("render-golden-ci.yml", "video-encoding-ci.yml"):
        workflow = (PROJECT_ROOT / ".github/workflows" / workflow_name).read_text(
            encoding="utf-8"
        )
        assert "actions/checkout@v" not in workflow
        assert "actions/setup-python@v" not in workflow
        assert "actions/setup-node@v" not in workflow
        assert "actions/cache@v" not in workflow


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
