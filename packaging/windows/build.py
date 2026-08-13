#!/usr/bin/env python3
"""
Windows Package Builder for Pixelle-Video

This script automates the creation of a Windows portable package:
1. Downloads Python embedded distribution
2. Downloads FFmpeg portable
3. Downloads the pinned Node.js portable distribution
4. Prepares Python and installs project dependencies
5. Copies project files and installs the locked HyperFrames runtime
6. Generates launcher scripts
7. Creates final ZIP package

Usage:
    python build.py [--config CONFIG] [--output OUTPUT] [--cn-mirror]
"""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional
from urllib.parse import urlparse
from urllib.request import urlretrieve

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install it with: pip install pyyaml")
    sys.exit(1)

_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class Color:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class WindowsPackageBuilder:
    """Build Windows portable package for Pixelle-Video"""
    
    def __init__(self, config_path: str, output_dir: Optional[str] = None, use_cn_mirror: bool = False):
        self.config_path = Path(config_path)
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent.parent
        
        # Load configuration
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # Override mirror setting if specified
        if use_cn_mirror:
            self.config['mirrors']['use_cn_mirror'] = True
        
        # Setup paths
        configured_output_dir = (
            Path(output_dir)
            if output_dir
            else self.project_root / self.config['build']['output_dir']
        )
        self.output_dir = configured_output_dir.resolve()
        self.cache_dir = self.project_root / self.config['cache']['cache_dir']
        self.templates_dir = self.script_dir / 'templates'
        
        # Get version from pyproject.toml
        self.version = self._read_version()
        self.package_name = f"{self.config['package']['name']}-v{self.version}-{self.config['package']['architecture']}"
        self.build_dir = self.output_dir / self.package_name
        
    def _read_version(self) -> str:
        """Read the package's single version source without importing runtime services."""

        import runpy

        version_path = self.project_root / "pixelle_video" / "_version.py"
        version = runpy.run_path(str(version_path)).get("__version__")
        if not isinstance(version, str) or not version.strip():
            raise RuntimeError(f"Invalid project version source: {version_path}")
        return version.strip()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        """Hash large build artifacts without loading them into memory."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
        """Extract a ZIP without allowing traversal, drive paths, or symlinks."""
        resolved_target = target_dir.resolve()
        resolved_target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                member_path = PurePosixPath(member.filename.replace("\\", "/"))
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or any(":" in part for part in member_path.parts)
                    or any(part.endswith((" ", ".")) for part in member_path.parts)
                    or any(
                        part.split(".", 1)[0].upper()
                        in _WINDOWS_RESERVED_NAMES
                        for part in member_path.parts
                    )
                ):
                    raise RuntimeError(
                        f"Unsafe ZIP member path in {zip_path}: {member.filename}"
                    )
                unix_mode = member.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise RuntimeError(
                        f"ZIP symlinks are not allowed in build inputs: {member.filename}"
                    )

                output_path = resolved_target.joinpath(*member_path.parts).resolve()
                try:
                    output_path.relative_to(resolved_target)
                except ValueError as exc:
                    raise RuntimeError(
                        f"ZIP member escapes extraction root: {member.filename}"
                    ) from exc
                if member.is_dir():
                    output_path.mkdir(parents=True, exist_ok=True)
                    continue
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, output_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

    def _install_uv_wheel(self, wheel_path: Path, python_dir: Path) -> None:
        """Install the authenticated uv wheel using the standard wheel path mapping."""
        expected_version = str(self.config["uv"]["version"])
        with tempfile.TemporaryDirectory(prefix="pixelle-uv-wheel-") as temporary_dir:
            extraction_root = Path(temporary_dir)
            self._safe_extract_zip(wheel_path, extraction_root)
            package_dir = extraction_root / "uv"
            dist_info_dir = extraction_root / f"uv-{expected_version}.dist-info"
            scripts_dir = (
                extraction_root
                / f"uv-{expected_version}.data"
                / "scripts"
            )
            for required_path in (package_dir, dist_info_dir, scripts_dir):
                if not required_path.is_dir():
                    raise RuntimeError(f"uv wheel payload is incomplete: {required_path}")

            site_packages = python_dir / "Lib" / "site-packages"
            target_scripts = python_dir / "Scripts"
            site_packages.mkdir(parents=True, exist_ok=True)
            target_scripts.mkdir(parents=True, exist_ok=True)
            shutil.copytree(package_dir, site_packages / package_dir.name)
            shutil.copytree(dist_info_dir, site_packages / dist_info_dir.name)
            for executable_name in ("uv.exe", "uvw.exe", "uvx.exe"):
                source = scripts_dir / executable_name
                if not source.is_file():
                    raise RuntimeError(f"uv wheel executable is missing: {source}")
                shutil.copy2(source, target_scripts / executable_name)

    @staticmethod
    def _extended_length_path(path: Path) -> Path:
        """Return a Windows path that remains addressable beyond MAX_PATH."""
        resolved_path = path.resolve()
        if os.name != "nt":
            return resolved_path

        raw_path = str(resolved_path)
        if raw_path.startswith("\\\\?\\"):
            return resolved_path
        if raw_path.startswith("\\\\"):
            return Path(f"\\\\?\\UNC\\{raw_path[2:]}")
        return Path(f"\\\\?\\{raw_path}")

    def _remove_existing_build_directory(self) -> None:
        """Remove only this package's resolved output directory."""
        resolved_build_dir = self.build_dir.resolve()
        resolved_output_dir = self.output_dir.resolve()
        if resolved_build_dir.parent != resolved_output_dir:
            raise RuntimeError(
                f"Refusing to clean build directory outside output root: {resolved_build_dir}"
            )
        def retry_windows_removal(function, path, exception_info):
            os.chmod(path, stat.S_IWRITE)
            last_error = exception_info[1]
            for retry_delay in (0.1, 0.25, 0.5):
                try:
                    function(path)
                    return
                except PermissionError as error:
                    last_error = error
                    time.sleep(retry_delay)
            raise last_error

        shutil.rmtree(
            self._extended_length_path(resolved_build_dir),
            onerror=retry_windows_removal,
        )
    
    def log(self, message: str, level: str = "INFO"):
        """Print colored log message"""
        colors = {
            "INFO": Color.BLUE,
            "SUCCESS": Color.GREEN,
            "WARNING": Color.YELLOW,
            "ERROR": Color.RED,
            "HEADER": Color.HEADER,
        }
        color = colors.get(level, Color.RESET)
        print(f"{color}[{level}]{Color.RESET} {message}")
    
    def download_file(self, url: str, output_path: Path, description: str = "", max_retries: int = 3) -> bool:
        """Download file with progress indication and retry support"""
        if urlparse(url).scheme.lower() != "https":
            raise RuntimeError(f"Refusing non-HTTPS build input: {url}")
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self.log(f"Retry {attempt}/{max_retries}...")
                
                self.log(f"Downloading {description or url}...")
                
                def report_progress(block_num, block_size, total_size):
                    downloaded = block_num * block_size
                    percent = min(downloaded / total_size * 100, 100) if total_size > 0 else 0
                    print(f"\r  Progress: {percent:.1f}%", end='', flush=True)
                
                # Try with urllib first
                urlretrieve(url, output_path, reporthook=report_progress)
                print()  # New line after progress
                self.log(f"Downloaded to {output_path}", "SUCCESS")
                return True
                
            except Exception as e:
                self.log(f"Download attempt {attempt + 1} failed: {e}", "WARNING")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)  # Wait before retry
                else:
                    self.log("All download attempts failed", "ERROR")
                    # Try with curl as fallback
                    return self._download_with_curl(url, output_path, description)
        
        return False

    def _download_verified_artifact(
        self,
        *,
        cache_file: Path,
        expected_digest: str,
        download_url: str,
        description: str,
    ) -> Path:
        """Return an authenticated artifact or fail closed on any drift."""
        normalized_digest = expected_digest.strip().lower()
        if (
            len(normalized_digest) != 64
            or any(character not in "0123456789abcdef" for character in normalized_digest)
        ):
            raise RuntimeError(f"Invalid SHA-256 for {description}: {expected_digest}")

        if cache_file.exists():
            actual_digest = self._sha256_file(cache_file)
            if actual_digest == normalized_digest:
                self.log(f"Using verified cached {description}: {cache_file}")
                return cache_file
            cache_file.unlink()

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if not self.download_file(download_url, cache_file, description):
            cache_file.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download {description}")

        actual_digest = self._sha256_file(cache_file)
        if actual_digest != normalized_digest:
            cache_file.unlink(missing_ok=True)
            raise RuntimeError(
                f"{description} SHA-256 mismatch: "
                f"expected {normalized_digest}, got {actual_digest}"
            )
        return cache_file
    
    def _download_with_curl(self, url: str, output_path: Path, description: str = "") -> bool:
        """Fallback download method using curl"""
        try:
            self.log(f"Trying curl fallback for {description}...")
            result = subprocess.run(
                [
                    'curl', '--fail', '--show-error', '--location',
                    '--proto', '=https', '--proto-redir', '=https',
                    '--output', str(output_path), url, '--progress-bar',
                ],
                check=True,
                capture_output=False
            )
            if result.returncode == 0 and output_path.exists():
                self.log(f"Downloaded with curl to {output_path}", "SUCCESS")
                return True
        except Exception as e:
            self.log(f"Curl download also failed: {e}", "ERROR")
        return False
    
    def download_python(self) -> Path:
        """Download and authenticate the Python embedded distribution."""
        python_config = self.config['python']
        cache_file = self.cache_dir / f"python-{python_config['version']}-embed-amd64.zip"
        url = python_config['mirror_url'] if self.config['mirrors']['use_cn_mirror'] else python_config['download_url']
        return self._download_verified_artifact(
            cache_file=cache_file,
            expected_digest=python_config['sha256'],
            download_url=url,
            description=f"Python {python_config['version']}",
        )
    
    def download_ffmpeg(self) -> Path:
        """Download and authenticate the pinned FFmpeg portable build."""
        ffmpeg_config = self.config['ffmpeg']
        cache_file = self.cache_dir / f"ffmpeg-{ffmpeg_config['version']}-win64.zip"
        url = ffmpeg_config['mirror_url'] if self.config['mirrors']['use_cn_mirror'] else ffmpeg_config['download_url']
        return self._download_verified_artifact(
            cache_file=cache_file,
            expected_digest=ffmpeg_config['sha256'],
            download_url=url,
            description=f"FFmpeg {ffmpeg_config['version']}",
        )

    def download_node(self) -> Path:
        """Download and authenticate the pinned Node.js portable distribution."""
        node_config = self.config['node']
        cache_file = self.cache_dir / f"node-v{node_config['version']}-win-x64.zip"
        url = (
            node_config['mirror_url']
            if self.config['mirrors']['use_cn_mirror']
            else node_config['download_url']
        )
        return self._download_verified_artifact(
            cache_file=cache_file,
            expected_digest=node_config['sha256'],
            download_url=url,
            description=f"Node.js {node_config['version']}",
        )
    
    def extract_python(self, zip_path: Path, target_dir: Path):
        """Extract Python embedded distribution"""
        self.log(f"Extracting Python to {target_dir}...")
        target_dir.mkdir(parents=True, exist_ok=True)
        
        self._safe_extract_zip(zip_path, target_dir)
        
        # Add execute permissions to .exe files (needed on Unix systems)
        if os.name != 'nt':  # Not on Windows
            for exe_file in target_dir.glob('*.exe'):
                os.chmod(exe_file, 0o755)
            for exe_file in target_dir.glob('**/*.exe'):
                os.chmod(exe_file, 0o755)
        
        self.log("Python extracted successfully", "SUCCESS")
    
    def extract_ffmpeg(self, zip_path: Path, target_dir: Path):
        """Extract FFmpeg portable"""
        self.log(f"Extracting FFmpeg to {target_dir}...")
        temp_extract = target_dir.parent / "ffmpeg_temp"
        temp_extract.mkdir(parents=True, exist_ok=True)
        
        self._safe_extract_zip(zip_path, temp_extract)
        
        # Find the bin directory (FFmpeg archive has nested structure)
        bin_dir = None
        for root, dirs, files in os.walk(temp_extract):
            if 'bin' in dirs:
                bin_dir = Path(root) / 'bin'
                break
        
        if bin_dir and bin_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(bin_dir, target_dir, dirs_exist_ok=True)
            shutil.rmtree(temp_extract)
            self._verify_ffmpeg_runtime(target_dir)
            self.log("FFmpeg extracted successfully", "SUCCESS")
        else:
            raise RuntimeError("FFmpeg bin directory not found in archive")

    def _verify_ffmpeg_runtime(self, target_dir: Path) -> None:
        """Verify the pinned build identity and one renderer-critical option."""
        ffmpeg_executable = target_dir / "ffmpeg.exe"
        ffprobe_executable = target_dir / "ffprobe.exe"
        for executable in (ffmpeg_executable, ffprobe_executable):
            if not executable.is_file():
                raise RuntimeError(f"FFmpeg runtime executable is missing: {executable}")

        version_result = subprocess.run(
            [str(ffmpeg_executable), "-version"],
            check=True,
            capture_output=True,
            text=True,
        )
        expected_version = str(self.config["ffmpeg"]["version"]).lower()
        version_line = version_result.stdout.splitlines()[0].lower()
        if expected_version not in version_line:
            raise RuntimeError(
                "FFmpeg runtime version mismatch: "
                f"expected {expected_version}, got {version_line}"
            )

        compatibility_result = subprocess.run(
            [
                str(ffmpeg_executable),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=size=16x16:rate=1:duration=0.1",
                "-frames:v",
                "1",
                "-vsync",
                "0",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        if compatibility_result.returncode != 0:
            detail = compatibility_result.stderr.strip() or "no diagnostic output"
            raise RuntimeError(
                "FFmpeg runtime is incompatible with the current render graph: "
                f"{detail}"
            )

    def extract_node(
        self,
        zip_path: Path,
        target_dir: Path,
        temporary_dir: Path,
    ) -> Path:
        """Extract build tooling on a short path and copy only the runtime payload."""
        self.log(f"Extracting Node.js to {target_dir}...")
        temp_extract = temporary_dir / "node"
        temp_extract.mkdir(parents=True, exist_ok=True)

        self._safe_extract_zip(zip_path, temp_extract)

        node_executable = next(temp_extract.rglob("node.exe"), None)
        if node_executable is None:
            raise RuntimeError("Node.js executable not found in archive")
        npm_cli = node_executable.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        license_file = node_executable.parent / "LICENSE"
        for required_path in (npm_cli, license_file):
            if not required_path.is_file():
                raise RuntimeError(f"Node.js build input is missing: {required_path}")

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(node_executable, target_dir / "node.exe")
        shutil.copy2(license_file, target_dir / "LICENSE")
        self.log("Node.js extracted successfully", "SUCCESS")
        return npm_cli

    def install_hyperframes_dependencies(
        self,
        node_dir: Path,
        npm_cli: Path,
        project_dir: Path,
    ):
        """Install and verify the bridge lock graph and pinned browser in the package."""
        bridge_dir = project_dir / "tools" / "hyperframes_bridge"
        node_executable = node_dir / "node.exe"
        for required_path in (
            node_executable,
            npm_cli,
            bridge_dir / "package-lock.json",
            bridge_dir / "src" / "render.mjs",
            bridge_dir / "src" / "verify-runtime.mjs",
        ):
            if not required_path.is_file():
                raise RuntimeError(f"Portable HyperFrames input is missing: {required_path}")

        bridge_manifest = json.loads(
            (bridge_dir / "package.json").read_text(encoding="utf-8")
        )
        puppeteer_version = bridge_manifest.get("dependencies", {}).get("puppeteer")
        if not isinstance(puppeteer_version, str) or not puppeteer_version:
            raise RuntimeError("Portable HyperFrames manifest must pin Puppeteer")
        build_browser_cache = self.cache_dir / f"puppeteer-{puppeteer_version}"
        target_browser_cache = node_dir.parent / "puppeteer"
        source_browser_cache = (
            self.project_root
            / "tools"
            / "hyperframes_bridge"
            / ".cache"
            / "puppeteer"
        )
        if not build_browser_cache.exists() and source_browser_cache.is_dir():
            self.log("Seeding the reusable browser cache from the verified source runtime...")
            shutil.copytree(source_browser_cache, build_browser_cache)

        environment = os.environ.copy()
        environment["PATH"] = f"{node_dir}{os.pathsep}{environment.get('PATH', '')}"
        environment["PUPPETEER_CACHE_DIR"] = str(build_browser_cache)
        environment["PUPPETEER_SKIP_DOWNLOAD"] = "true"
        environment["PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD"] = "true"
        environment["PIXELLE_REQUIRE_PINNED_BROWSER"] = "true"
        removed_environment_names = {
            name.lower()
            for name in (
                "PUPPETEER_SKIP_CHROME_DOWNLOAD",
                "npm_config_ignore_scripts",
                "PUPPETEER_EXECUTABLE_PATH",
                "PRODUCER_HEADLESS_SHELL_PATH",
            )
        }
        for variable_name in tuple(environment):
            if variable_name.lower() in removed_environment_names:
                environment.pop(variable_name, None)

        self.log("Installing locked HyperFrames dependencies...")
        subprocess.run(
            [
                str(node_executable),
                str(npm_cli),
                "ci",
                "--omit=dev",
            ],
            cwd=bridge_dir,
            env=environment,
            check=True,
        )
        subprocess.run(
            [
                str(node_executable),
                str(npm_cli),
                "run",
                "browser:install",
            ],
            cwd=bridge_dir,
            env=environment,
            check=True,
        )
        subprocess.run(
            [
                str(node_executable),
                str(npm_cli),
                "run",
                "runtime:verify",
            ],
            cwd=bridge_dir,
            env=environment,
            check=True,
        )
        build_chrome_cache = build_browser_cache / "chrome"
        if not build_chrome_cache.is_dir():
            raise RuntimeError(
                f"Verified Puppeteer cache does not contain Chrome: {build_chrome_cache}"
            )
        shutil.copytree(build_chrome_cache, target_browser_cache / "chrome")
        environment["PUPPETEER_CACHE_DIR"] = str(target_browser_cache)
        subprocess.run(
            [
                str(node_executable),
                str(npm_cli),
                "run",
                "runtime:verify",
            ],
            cwd=bridge_dir,
            env=environment,
            check=True,
        )
        self.log("HyperFrames runtime installed and verified in the final package", "SUCCESS")
    
    def prepare_python_environment(self, python_dir: Path):
        """Enable the embedded Python import path used by the portable runtime."""
        self.log("Preparing Python environment...")
        pth_file = python_dir / "python311._pth"
        if not pth_file.is_file():
            raise RuntimeError(f"Embedded Python path contract is missing: {pth_file}")
        lines = pth_file.read_text(encoding="utf-8").splitlines(keepends=True)
        modified = False
        for index, line in enumerate(lines):
            if line.strip().startswith("#import site"):
                lines[index] = "import site\n"
                modified = True
                break
        if not modified and "import site" not in {line.strip() for line in lines}:
            lines.append("import site\n")

        portable_project_path = r"..\..\Pixelle-Video"
        if portable_project_path not in {line.strip() for line in lines}:
            site_import_index = next(
                index
                for index, line in enumerate(lines)
                if line.strip() == "import site"
            )
            lines.insert(site_import_index, f"{portable_project_path}\n")
        pth_file.write_text("".join(lines), encoding="utf-8")
        self.log("Enabled site-packages and portable project imports", "SUCCESS")
    
    def install_dependencies(self, python_dir: Path):
        """Install the exact Python graph exported from uv.lock with hashes."""
        self.log("Installing locked project dependencies...")
        python_exe = python_dir / "python.exe"
        uv_config = self.config["uv"]
        uv_wheel = self._download_verified_artifact(
            cache_file=self.cache_dir / f"uv-{uv_config['version']}-win-amd64.whl",
            expected_digest=uv_config["sha256"],
            download_url=uv_config["download_url"],
            description=f"uv {uv_config['version']} Windows wheel",
        )
        self._install_uv_wheel(uv_wheel, python_dir)
        subprocess.run(
            [
                str(python_exe),
                "-m",
                "uv",
                "--version",
            ],
            check=True,
        )

        clean_environment = os.environ.copy()
        for variable_name in tuple(clean_environment):
            if variable_name.upper().startswith(("PIP_", "UV_")):
                clean_environment.pop(variable_name, None)
        clean_environment["UV_NO_CONFIG"] = "1"

        with tempfile.TemporaryDirectory(prefix="pixelle-python-lock-") as temporary_dir:
            requirements_path = Path(temporary_dir) / "requirements.txt"
            subprocess.run(
                [
                    str(python_exe),
                    "-m",
                    "uv",
                    "--no-config",
                    "--quiet",
                    "export",
                    "--frozen",
                    "--no-dev",
                    "--no-emit-project",
                    "--format",
                    "requirements-txt",
                    "--output-file",
                    str(requirements_path),
                ],
                cwd=self.project_root,
                env=clean_environment,
                check=True,
            )
            install_command = [
                str(python_exe),
                "-m",
                "uv",
                "--no-config",
                "pip",
                "install",
                "--python",
                str(python_exe),
                "--link-mode",
                "copy",
                "--require-hashes",
                "--no-deps",
                "--requirements",
                str(requirements_path),
                "--default-index",
                (
                    self.config["mirrors"]["pypi_mirror"]
                    if self.config["mirrors"]["use_cn_mirror"]
                    else "https://pypi.org/simple"
                ),
            ]
            subprocess.run(
                install_command,
                cwd=self.project_root,
                env=clean_environment,
                check=True,
            )
        self.log("Locked dependencies installed successfully", "SUCCESS")
    
    def copy_project_files(self, target_dir: Path):
        """Copy project files to build directory"""
        self.log(f"Copying project files to {target_dir}...")
        
        exclude_patterns = self.config['build']['exclude_patterns']
        
        def should_exclude(path: Path) -> bool:
            path_str = path.relative_to(self.project_root).as_posix()
            for pattern in exclude_patterns:
                if pattern.endswith('/*'):
                    # Directory content exclusion - must match exact directory name or start with "dirname/"
                    dir_name = pattern[:-2]
                    if path_str == dir_name or path_str.startswith(f"{dir_name}/"):
                        return True
                elif pattern.endswith('*'):
                    # Wildcard pattern
                    if path_str.startswith(pattern[:-1]):
                        return True
                elif '*' in pattern:
                    # Glob pattern (simple check)
                    import fnmatch
                    if fnmatch.fnmatch(path_str, pattern):
                        return True
                else:
                    # Exact match or directory
                    if path_str == pattern or path_str.startswith(f"{pattern}/"):
                        return True
            return False
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy files
        copied_count = 0
        for item in self.project_root.iterdir():
            if item.name in ['.git', 'packaging', 'dist', '.venv', 'venv']:
                continue
            
            if should_exclude(item):
                continue
            
            target_path = target_dir / item.name
            
            if item.is_file():
                shutil.copy2(item, target_path)
                copied_count += 1
            elif item.is_dir():
                shutil.copytree(item, target_path, ignore=lambda d, names: [
                    n for n in names if should_exclude(Path(d) / n)
                ])
                # Count files in copied directory
                copied_count += sum(1 for _ in target_path.rglob('*') if _.is_file())

        runtime_docs_dir = target_dir / "docs"
        runtime_docs_dir.mkdir(parents=True, exist_ok=True)
        for faq_name in ("FAQ.md", "FAQ_CN.md"):
            faq_source = self.project_root / "docs" / faq_name
            if not faq_source.is_file():
                raise RuntimeError(f"Required runtime FAQ is missing: {faq_source}")
            shutil.copy2(faq_source, runtime_docs_dir / faq_name)
            copied_count += 1

        launcher_source = self.project_root / "scripts" / "launch_web.py"
        if not launcher_source.is_file():
            raise RuntimeError(f"Required runtime launcher is missing: {launcher_source}")
        runtime_scripts_dir = target_dir / "scripts"
        runtime_scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(launcher_source, runtime_scripts_dir / launcher_source.name)
        copied_count += 1
        
        self.log(f"Copied {copied_count} files", "SUCCESS")
    
    def generate_launcher_scripts(self):
        """Generate launcher scripts from templates"""
        self.log("Generating launcher scripts...")
        
        replacements = {
            '{VERSION}': self.version,
            '{BUILD_DATE}': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        # Copy and process templates
        for template_file in self.templates_dir.glob('*'):
            if template_file.is_file():
                target_file = self.build_dir / template_file.name
                
                with open(template_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Replace placeholders
                for key, value in replacements.items():
                    content = content.replace(key, value)
                
                with open(target_file, 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write(content)
                
                self.log(f"Generated: {template_file.name}")
        
        self.log("Launcher scripts generated", "SUCCESS")
    
    def create_empty_directories(self):
        """Create empty directories specified in config"""
        self.log("Creating empty directories...")
        
        for dir_name in self.config['build'].get('create_empty_dirs', []):
            dir_path = self.build_dir / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            # Create .gitkeep to preserve directory in git
            (dir_path / '.gitkeep').touch()
        
        self.log("Empty directories created", "SUCCESS")
    
    def create_zip_package(self):
        """Create final ZIP package"""
        if not self.config['build'].get('create_zip', True):
            return
        
        zip_path = self.output_dir / f"{self.package_name}.zip"
        self.log(f"Creating ZIP package: {zip_path}...")
        
        compression_map = {
            'deflate': zipfile.ZIP_DEFLATED,
            'bzip2': zipfile.ZIP_BZIP2,
            'lzma': zipfile.ZIP_LZMA,
        }
        compression = compression_map.get(
            self.config['build'].get('zip_compression', 'deflate'),
            zipfile.ZIP_DEFLATED
        )
        
        walk_root = self._extended_length_path(self.build_dir)
        with zipfile.ZipFile(zip_path, 'w', compression) as zipf:
            for root, dirs, files in os.walk(walk_root):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(walk_root.parent)
                    zipf.write(file_path, arcname)
        
        # Calculate file size and hash
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        
        file_hash = self._sha256_file(zip_path)
        
        self.log(f"ZIP package created: {zip_path}", "SUCCESS")
        self.log(f"Size: {size_mb:.2f} MB")
        self.log(f"SHA256: {file_hash}")
        
        # Write hash to file
        hash_file = zip_path.with_suffix('.zip.sha256')
        with open(hash_file, 'w') as f:
            f.write(f"{file_hash}  {zip_path.name}\n")
    
    def build(self):
        """Main build process"""
        if os.name != "nt":
            raise RuntimeError(
                "Windows portable packages must be built on Windows so compiled wheels "
                "match the bundled interpreter"
            )
        self.log("=" * 60, "HEADER")
        self.log(f"Building {self.package_name}", "HEADER")
        self.log("=" * 60, "HEADER")
        
        try:
            # Clean build directory
            if self.build_dir.exists():
                self.log(f"Cleaning existing build directory: {self.build_dir}")
                self._remove_existing_build_directory()
            
            self.build_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Download dependencies
            python_zip = self.download_python()
            ffmpeg_zip = self.download_ffmpeg()
            node_zip = self.download_node()
            
            # Extract Python
            python_dir = self.build_dir / "python" / "python311"
            self.extract_python(python_zip, python_dir)
            
            # Extract FFmpeg
            ffmpeg_dir = self.build_dir / "tools" / "ffmpeg" / "bin"
            self.extract_ffmpeg(ffmpeg_zip, ffmpeg_dir)

            node_dir = self.build_dir / "tools" / "node"
            with tempfile.TemporaryDirectory(prefix="pixelle-node-") as temporary_dir:
                npm_cli = self.extract_node(node_zip, node_dir, Path(temporary_dir))

                # Prepare Python environment
                self.prepare_python_environment(python_dir)

                # Install the exact Python dependency graph from uv.lock.
                self.install_dependencies(python_dir)

                # Copy project files
                project_target = self.build_dir / "Pixelle-Video"
                self.copy_project_files(project_target)
                self.install_hyperframes_dependencies(
                    node_dir,
                    npm_cli,
                    project_target,
                )
            
            # Generate launcher scripts
            self.generate_launcher_scripts()
            
            # Create empty directories
            self.create_empty_directories()
            
            # Create ZIP package
            self.create_zip_package()
            
            self.log("=" * 60, "HEADER")
            self.log("Build completed successfully!", "SUCCESS")
            self.log(f"Package location: {self.build_dir}", "SUCCESS")
            self.log("=" * 60, "HEADER")
            
        except Exception as e:
            self.log(f"Build failed: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Build Windows portable package for Pixelle-Video")
    parser.add_argument(
        '--config',
        default='packaging/windows/config/build_config.yaml',
        help='Path to build configuration file'
    )
    parser.add_argument(
        '--output',
        help='Output directory (default: dist/windows)'
    )
    parser.add_argument(
        '--cn-mirror',
        action='store_true',
        help='Use China mirrors for faster downloads'
    )
    
    args = parser.parse_args()
    
    builder = WindowsPackageBuilder(
        config_path=args.config,
        output_dir=args.output,
        use_cn_mirror=args.cn_mirror
    )
    builder.build()


if __name__ == '__main__':
    main()

