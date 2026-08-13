import base64
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts" / "comfyui"
POWERSHELL = "powershell"


def ps_single_quote(value: object) -> str:
    return str(value).replace("'", "''")


def run_powershell(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *map(str, args),
    ]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def write_fake_backend_ownership(
    *,
    comfyui_root: Path,
    data_root: Path,
    extra_models_config: Path,
    runtime_dir: Path,
    port: int,
    backend_pid: int,
    launcher_pid: int,
) -> None:
    common_script = SCRIPT_DIR / "backend_common.ps1"
    command = "\n".join(
        [
            f". '{ps_single_quote(common_script)}'",
            "$config = Resolve-PixelleComfyUIBackendConfig "
            f"-PythonExe '{ps_single_quote(sys.executable)}' "
            f"-ComfyUIRoot '{ps_single_quote(comfyui_root)}' "
            f"-DataRoot '{ps_single_quote(data_root)}' "
            f"-SharedBasePath '{ps_single_quote(data_root)}' "
            f"-ExtraModelsConfig '{ps_single_quote(extra_models_config)}' "
            f"-RuntimeDir '{ps_single_quote(runtime_dir)}' "
            "-HostAddress '127.0.0.1' "
            f"-Port {port}",
            f"Write-BackendOwnershipRecord $config {backend_pid} {launcher_pid}",
        ]
    )
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def make_fake_comfyui(tmp_path: Path) -> tuple[Path, Path, Path]:
    comfyui_root = tmp_path / "ComfyUI"
    data_root = tmp_path / "ComfyUIData"
    comfyui_root.mkdir()
    (comfyui_root / "comfy").mkdir()
    (comfyui_root / "comfy" / "__init__.py").write_text("", encoding="utf-8")
    (comfyui_root / "comfy" / "options.py").write_text(
        "args_parsing = False\n"
        "def enable_args_parsing(enable=True):\n"
        "    global args_parsing\n"
        "    args_parsing = enable\n",
        encoding="utf-8",
    )
    write_fake_comfyui_cli_args(comfyui_root)
    (comfyui_root / "folder_paths.py").write_text(
        "import os\n"
        "from comfy.cli_args import args\n"
        "base_path = os.path.abspath(args.base_directory)\n"
        "folder_names_and_paths = {\n"
        "    'custom_nodes': ([os.path.join(base_path, 'custom_nodes')], set())\n"
        "}\n"
        "def add_model_folder_path(folder_name, full_folder_path, is_default=False):\n"
        "    paths, _ = folder_names_and_paths.setdefault(folder_name, ([], set()))\n"
        "    if full_folder_path in paths:\n"
        "        if is_default and paths[0] != full_folder_path:\n"
        "            paths.remove(full_folder_path)\n"
        "            paths.insert(0, full_folder_path)\n"
        "    elif is_default:\n"
        "        paths.insert(0, full_folder_path)\n"
        "    else:\n"
        "        paths.append(full_folder_path)\n"
        "def get_folder_paths(folder_name):\n"
        "    return folder_names_and_paths[folder_name][0][:]\n",
        encoding="utf-8",
    )
    (comfyui_root / "utils").mkdir()
    (comfyui_root / "utils" / "__init__.py").write_text("", encoding="utf-8")
    (comfyui_root / "utils" / "extra_config.py").write_text(
        "import os\n"
        "import yaml\n"
        "import folder_paths\n"
        "def load_extra_path_config(yaml_path):\n"
        "    with open(yaml_path, 'r', encoding='utf-8') as stream:\n"
        "        config = yaml.safe_load(stream)\n"
        "    yaml_dir = os.path.dirname(os.path.abspath(yaml_path))\n"
        "    for name in config:\n"
        "        section = config[name]\n"
        "        if section is None:\n"
        "            continue\n"
        "        base_path = section.pop('base_path', None)\n"
        "        if base_path is not None:\n"
        "            base_path = os.path.expandvars(os.path.expanduser(base_path))\n"
        "            if not os.path.isabs(base_path):\n"
        "                base_path = os.path.abspath(os.path.join(yaml_dir, base_path))\n"
        "        is_default = section.pop('is_default', False)\n"
        "        for folder_name, configured_paths in section.items():\n"
        "            for configured_path in configured_paths.split('\\n'):\n"
        "                if not configured_path:\n"
        "                    continue\n"
        "                full_path = configured_path\n"
        "                if base_path:\n"
        "                    full_path = os.path.join(base_path, full_path)\n"
        "                elif not os.path.isabs(full_path):\n"
        "                    full_path = os.path.abspath(os.path.join(yaml_dir, full_path))\n"
        "                folder_paths.add_model_folder_path(\n"
        "                    folder_name, os.path.normpath(full_path), is_default\n"
        "                )\n",
        encoding="utf-8",
    )
    (comfyui_root / "web_custom_versions" / "desktop_app").mkdir(parents=True)
    (comfyui_root / "main.py").write_text("print('fake comfyui')\n", encoding="utf-8")
    for name in ("input", "output", "user"):
        (data_root / name).mkdir(parents=True)
    extra_models_config = tmp_path / "extra_models_config.yaml"
    extra_models_config.write_text("pixelle:\n  base_path: E:/ComfyUIData\n", encoding="utf-8")
    return comfyui_root, data_root, extra_models_config


def write_fake_comfyui_cli_args(
    comfyui_root: Path,
    supported_flags: str = (
        "--disable-pinned-memory --disable-async-offload --cache-none"
    ),
) -> None:
    (comfyui_root / "comfy" / "cli_args.py").write_text(
        "import argparse\n"
        "import comfy.options\n"
        f"# Supported options: {supported_flags}\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--base-directory')\n"
        "args = (\n"
        "    parser.parse_args()\n"
        "    if comfy.options.args_parsing\n"
        "    else parser.parse_args([])\n"
        ")\n",
        encoding="utf-8",
    )


def write_fake_listening_main_py(comfyui_root: Path) -> None:
    (comfyui_root / "main.py").write_text(
        "\n".join(
            [
                "import argparse",
                "import socket",
                "import time",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--listen', default='127.0.0.1')",
                "parser.add_argument('--port', type=int, required=True)",
                "parser.add_argument('--user-directory')",
                "parser.add_argument('--input-directory')",
                "parser.add_argument('--output-directory')",
                "parser.add_argument('--base-directory')",
                "args, _ = parser.parse_known_args()",
                "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
                "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)",
                "sock.bind((args.listen, args.port))",
                "sock.listen(1)",
                "print('fake comfyui listening', flush=True)",
                "time.sleep(30)",
            ]
        ),
        encoding="utf-8",
    )


def write_fake_short_listening_main_py(comfyui_root: Path) -> None:
    write_fake_listening_main_py(comfyui_root)
    main_py = comfyui_root / "main.py"
    main_py.write_text(
        main_py.read_text(encoding="utf-8").replace("time.sleep(30)", "time.sleep(5)"),
        encoding="utf-8",
    )


def write_fake_hanging_main_py(comfyui_root: Path) -> None:
    (comfyui_root / "main.py").write_text(
        "\n".join(
            [
                "import argparse",
                "import time",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--listen', default='127.0.0.1')",
                "parser.add_argument('--port', type=int, required=True)",
                "parser.add_argument('--user-directory')",
                "parser.add_argument('--input-directory')",
                "parser.add_argument('--output-directory')",
                "parser.add_argument('--base-directory')",
                "args, _ = parser.parse_known_args()",
                "print('fake comfyui started without listener', flush=True)",
                "time.sleep(30)",
            ]
        ),
        encoding="utf-8",
    )


def write_fake_failing_main_py(comfyui_root: Path) -> None:
    (comfyui_root / "main.py").write_text(
        "import sys\n"
        "print('deliberate backend failure api_key=do-not-expose', file=sys.stderr, flush=True)\n"
        "print('{\"comfyui_api_key\": \"json-do-not-expose\", \"Authorization\": \"Bearer bearer-do-not-expose\"}', file=sys.stderr, flush=True)\n"
        "sys.exit(23)\n",
        encoding="utf-8",
    )


def write_fake_reexec_main_py(comfyui_root: Path) -> None:
    (comfyui_root / "main.py").write_text(
        "\n".join(
            [
                "import argparse",
                "import socket",
                "import subprocess",
                "import sys",
                "import time",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--fake-child-listener', action='store_true')",
                "parser.add_argument('--listen', default='127.0.0.1')",
                "parser.add_argument('--port', type=int, required=True)",
                "parser.add_argument('--user-directory')",
                "parser.add_argument('--input-directory')",
                "parser.add_argument('--output-directory')",
                "parser.add_argument('--base-directory')",
                "args, _ = parser.parse_known_args()",
                "if args.fake_child_listener:",
                "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
                "    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)",
                "    sock.bind((args.listen, args.port))",
                "    sock.listen(1)",
                "    print('fake child listening', flush=True)",
                "    time.sleep(20)",
                "else:",
                "    subprocess.Popen([sys.executable, __file__, '--fake-child-listener'] + sys.argv[1:])",
                "    print('fake parent waiting', flush=True)",
                "    time.sleep(4)",
            ]
        ),
        encoding="utf-8",
    )


def write_fake_reexec_with_worker_main_py(comfyui_root: Path) -> None:
    write_fake_reexec_main_py(comfyui_root)
    main_py = comfyui_root / "main.py"
    source = main_py.read_text(encoding="utf-8")
    source = source.replace(
        "import sys",
        "import sys\nfrom pathlib import Path",
    ).replace(
        "    print('fake child listening', flush=True)",
        "    worker = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'])\n"
        "    Path(__file__).with_name('worker.pid').write_text(str(worker.pid))\n"
        "    print('fake child listening', flush=True)",
    )
    main_py.write_text(source, encoding="utf-8")


def write_fake_unicode_sensitive_main_py(comfyui_root: Path) -> None:
    (comfyui_root / "main.py").write_text(
        "\n".join(
            [
                "import argparse",
                "import os",
                "import socket",
                "import time",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--listen', default='127.0.0.1')",
                "parser.add_argument('--port', type=int, required=True)",
                "parser.add_argument('--user-directory')",
                "parser.add_argument('--input-directory')",
                "parser.add_argument('--output-directory')",
                "parser.add_argument('--base-directory')",
                "args, _ = parser.parse_known_args()",
                "if os.environ.get('PYTHONIOENCODING') != 'utf-8':",
                "    raise RuntimeError('PYTHONIOENCODING was not propagated')",
                "print('\\U0001f389 fake comfyui started', flush=True)",
                "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
                "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)",
                "sock.bind((args.listen, args.port))",
                "sock.listen(1)",
                "time.sleep(20)",
            ]
        ),
        encoding="utf-8",
    )


def write_fake_external_launcher(
    launcher_path: Path,
    comfyui_root: Path,
) -> None:
    launcher_path.write_text(
        "\n".join(
            [
                "import subprocess",
                "import sys",
                "import time",
                "subprocess.Popen([sys.executable, r'%s'] + sys.argv[1:])"
                % str(comfyui_root / "main.py"),
                "time.sleep(20)",
            ]
        ),
        encoding="utf-8",
    )


def reserve_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_port(port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for port {port}")


def windows_process_is_running(process_id: int) -> bool:
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            f"if (Get-Process -Id {process_id} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


def stop_process_for_test(process_id: int) -> None:
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-Command",
            f"Stop-Process -Id {process_id} -Force -ErrorAction Stop",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def wait_for_process_exit(process_id: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not windows_process_is_running(process_id):
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for process {process_id} to exit")


def kill_fake_comfyui_processes(comfyui_root: Path) -> None:
    escaped = str(comfyui_root / "main.py").replace("'", "''")
    cleanup = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -like '*{escaped}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cleanup],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def fake_listening_comfyui_command(
    comfyui_root: Path,
    data_root: Path,
    port: int,
) -> list[str]:
    extra_models_config = comfyui_root.parent / "extra_models_config.yaml"
    database_url = f"sqlite:///{(data_root / 'user' / 'comfyui.db').as_posix()}"
    return [
        sys.executable,
        str(comfyui_root / "main.py"),
        "--user-directory",
        str(data_root / "user"),
        "--input-directory",
        str(data_root / "input"),
        "--output-directory",
        str(data_root / "output"),
        "--base-directory",
        str(data_root),
        "--database-url",
        database_url,
        "--extra-model-paths-config",
        str(extra_models_config),
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
        "--normalvram",
        "--disable-pinned-memory",
    ]


def start_fake_listening_comfyui(
    comfyui_root: Path,
    data_root: Path,
    port: int,
) -> subprocess.Popen:
    process = subprocess.Popen(
        fake_listening_comfyui_command(comfyui_root, data_root, port)
    )
    wait_for_port(port)
    return process


def run_fake_backend_stop(
    *,
    comfyui_root: Path,
    data_root: Path,
    extra_models_config: Path,
    runtime_dir: Path,
    port: int,
    shared_base_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    shared_base_arguments: list[object] = []
    if shared_base_path is not None:
        shared_base_arguments = ["-SharedBasePath", shared_base_path]
    return run_powershell(
        SCRIPT_DIR / "stop_backend.ps1",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        *shared_base_arguments,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        str(port),
    )


def assert_fake_backend_listener_absent(
    *,
    comfyui_root: Path,
    data_root: Path,
    extra_models_config: Path,
    runtime_dir: Path,
    port: int,
) -> None:
    check = run_powershell(
        SCRIPT_DIR / "check_backend.ps1",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        str(port),
    )
    assert check.returncode == 0, check.stderr
    assert json.loads(check.stdout)["listener_present"] is False


def test_start_backend_dry_run_initializes_missing_profile_dirs(
    tmp_path: Path,
) -> None:
    comfyui_root = tmp_path / "ComfyUI"
    data_root = tmp_path / "profiles" / "image-data"
    runtime_dir = tmp_path / "runtime" / "image"
    logs_dir = tmp_path / "logs" / "image"
    comfyui_root.mkdir()
    (comfyui_root / "comfy").mkdir()
    (comfyui_root / "comfy" / "cli_args.py").write_text(
        "--disable-pinned-memory --disable-async-offload --cache-none",
        encoding="utf-8",
    )
    (comfyui_root / "web_custom_versions" / "desktop_app").mkdir(parents=True)
    (comfyui_root / "main.py").write_text("print('fake comfyui')\n", encoding="utf-8")
    extra_models_config = tmp_path / "extra_models_config.yaml"
    extra_models_config.write_text("pixelle:\n  base_path: E:/ComfyUIData\n", encoding="utf-8")

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-ProfileName",
        "image",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["profile"] == "image"
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 65500
    assert payload["data_root"] == str(data_root)
    assert payload["runtime_dir"] == str(runtime_dir)
    assert payload["logs_dir"] == str(logs_dir)
    assert payload["database_url"].endswith("/profiles/image-data/user/comfyui.db")
    assert payload["pid_file"] == str(runtime_dir / "comfyui-backend.pid")
    assert payload["launcher_pid_file"] == str(runtime_dir / "comfyui-backend.launcher.pid")
    assert payload["stdout_log"] == str(logs_dir / "comfyui-backend.stdout.log")
    assert payload["stderr_log"] == str(logs_dir / "comfyui-backend.stderr.log")
    for directory in (
        data_root / "input",
        data_root / "output",
        data_root / "user",
        runtime_dir,
        logs_dir,
    ):
        assert directory.is_dir()


def test_backend_pid_and_logs_are_profile_scoped(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    first_root.mkdir()
    comfyui_root, first_data_root, extra_models_config = make_fake_comfyui(
        first_root
    )
    second_data_root = tmp_path / "second" / "ComfyUIData"
    for name in ("input", "output", "user"):
        (second_data_root / name).mkdir(parents=True)
    first_runtime_dir = tmp_path / "runtime" / "image"
    first_logs_dir = tmp_path / "logs" / "image"
    second_runtime_dir = tmp_path / "runtime" / "tts"
    second_logs_dir = tmp_path / "logs" / "tts"

    first = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        first_data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        first_runtime_dir,
        "-LogsDir",
        first_logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )
    second = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        second_data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        second_runtime_dir,
        "-LogsDir",
        second_logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65501",
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["pid_file"] == str(first_runtime_dir / "comfyui-backend.pid")
    assert second_payload["pid_file"] == str(second_runtime_dir / "comfyui-backend.pid")
    assert first_payload["stdout_log"] == str(first_logs_dir / "comfyui-backend.stdout.log")
    assert second_payload["stdout_log"] == str(second_logs_dir / "comfyui-backend.stdout.log")
    assert first_payload["pid_file"] != second_payload["pid_file"]
    assert first_payload["stdout_log"] != second_payload["stdout_log"]


def test_process_with_same_data_root_but_different_port_is_not_managed(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    actual_port = reserve_free_port()
    target_port = reserve_free_port()
    process = start_fake_listening_comfyui(comfyui_root, data_root, actual_port)
    try:
        command = [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                ". (Join-Path $PWD 'scripts/comfyui/backend_common.ps1'); "
                "$config = Resolve-PixelleComfyUIBackendConfig "
                f"-PythonExe '{ps_single_quote(sys.executable)}' "
                f"-ComfyUIRoot '{ps_single_quote(comfyui_root)}' "
                f"-DataRoot '{ps_single_quote(data_root)}' "
                f"-ExtraModelsConfig '{ps_single_quote(extra_models_config)}' "
                "-RuntimeDir 'unused-runtime' "
                "-HostAddress '127.0.0.1' "
                f"-Port {target_port}; "
                f"if (Test-ManagedComfyUIProcess $config {process.pid}) "
                "{ 'managed' } else { 'unmanaged' }"
            ),
        ]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unmanaged"


def test_managed_process_identity_covers_every_behavioral_launch_argument(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    probe_script = tmp_path / "probe-complete-process-identity.ps1"
    probe_script.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. '{ps_single_quote(SCRIPT_DIR / "backend_common.ps1")}'
$config = Resolve-PixelleComfyUIBackendConfig `
    -PythonExe '{ps_single_quote(sys.executable)}' `
    -ComfyUIRoot '{ps_single_quote(comfyui_root)}' `
    -DataRoot '{ps_single_quote(data_root)}' `
    -SharedBasePath '{ps_single_quote(data_root)}' `
    -ExtraModelsConfig '{ps_single_quote(extra_models_config)}' `
    -RuntimeDir '{ps_single_quote(tmp_path / "runtime")}' `
    -HostAddress '127.0.0.1' `
    -Port 65510
$arguments = @($config.PythonExe) + @(Get-BackendArguments $config)
$exact = ConvertTo-WindowsCommandLine $arguments
$resolvedInterpreter = [object[]]$arguments.Clone()
$resolvedInterpreter[0] = 'C:\\Program Files\\Python\\python.exe'
$wrongData = [object[]]$arguments.Clone()
$wrongData[3] = '{ps_single_quote(tmp_path / "other-user")}'
$wrongExtra = [object[]]$arguments.Clone()
$wrongExtra[($wrongExtra.IndexOf('--extra-model-paths-config') + 1)] = `
    '{ps_single_quote(tmp_path / "other-paths.yaml")}'
$additionalExtra = [System.Collections.Generic.List[string]]::new()
foreach ($argument in $arguments) {{ [void]$additionalExtra.Add([string]$argument) }}
$additionalExtra.Insert(
    $additionalExtra.IndexOf('--extra-model-paths-config') + 2,
    '{ps_single_quote(tmp_path / "additional-paths.yaml")}'
)
$wrongDatabase = [object[]]$arguments.Clone()
$wrongDatabase[($wrongDatabase.IndexOf('--database-url') + 1)] = `
    'sqlite:///D:/other.db'
$duplicatePort = @($arguments) + @('--port', '65510')
@{{
    exact = Test-ManagedComfyUICommandLine $config $exact
    resolved_interpreter = Test-ManagedComfyUICommandLine `
        $config (ConvertTo-WindowsCommandLine $resolvedInterpreter)
    wrong_data = Test-ManagedComfyUICommandLine `
        $config (ConvertTo-WindowsCommandLine $wrongData)
    wrong_extra = Test-ManagedComfyUICommandLine `
        $config (ConvertTo-WindowsCommandLine $wrongExtra)
    additional_extra = Test-ManagedComfyUICommandLine `
        $config (ConvertTo-WindowsCommandLine $additionalExtra)
    wrong_database = Test-ManagedComfyUICommandLine `
        $config (ConvertTo-WindowsCommandLine $wrongDatabase)
    duplicate_port = Test-ManagedComfyUICommandLine `
        $config (ConvertTo-WindowsCommandLine $duplicatePort)
}} | ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )

    result = run_powershell(probe_script)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "exact": True,
        "resolved_interpreter": True,
        "wrong_data": False,
        "wrong_extra": False,
        "additional_extra": False,
        "wrong_database": False,
        "duplicate_port": False,
    }


def test_backend_launch_identity_changes_when_path_config_content_changes(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    probe_script = tmp_path / "probe-launch-identity.ps1"
    probe_script.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. '{ps_single_quote(SCRIPT_DIR / "backend_common.ps1")}'
$config = Resolve-PixelleComfyUIBackendConfig `
    -PythonExe '{ps_single_quote(sys.executable)}' `
    -ComfyUIRoot '{ps_single_quote(comfyui_root)}' `
    -DataRoot '{ps_single_quote(data_root)}' `
    -SharedBasePath '{ps_single_quote(data_root)}' `
    -ExtraModelsConfig '{ps_single_quote(extra_models_config)}' `
    -RuntimeDir '{ps_single_quote(tmp_path / "runtime")}' `
    -Port 65511
$before = Get-BackendLaunchIdentity $config
Set-Content `
    -LiteralPath '{ps_single_quote(extra_models_config)}' `
    -Value "pixelle:`n  base_path: D:/changed" `
    -Encoding UTF8
$after = Get-BackendLaunchIdentity $config
@{{ before = $before; after = $after }} | ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )

    result = run_powershell(probe_script)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["before"]) == 64
    assert len(payload["after"]) == 64
    assert payload["before"] != payload["after"]


def test_supervisor_process_identity_uses_the_launch_identity(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    probe_script = tmp_path / "probe-supervisor-identity.ps1"
    probe_script.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. '{ps_single_quote(SCRIPT_DIR / "backend_common.ps1")}'
$config = Resolve-PixelleComfyUIBackendConfig `
    -PythonExe '{ps_single_quote(sys.executable)}' `
    -ComfyUIRoot '{ps_single_quote(comfyui_root)}' `
    -DataRoot '{ps_single_quote(data_root)}' `
    -SharedBasePath '{ps_single_quote(data_root)}' `
    -ExtraModelsConfig '{ps_single_quote(extra_models_config)}' `
    -RuntimeDir '{ps_single_quote(tmp_path / "runtime")}' `
    -Port 65513
$launchIdentity = Get-BackendLaunchIdentity $config
$arguments = @(
    '{ps_single_quote(SCRIPT_DIR / "backend_supervisor.ps1")}',
    '-PythonExe', $config.PythonExe,
    '-WorkingDirectory', $config.ComfyUIRoot,
    '-ArgumentsBase64', 'opaque-serialization',
    '-LaunchIdentity', $launchIdentity,
    '-ProfileName', $config.ProfileName,
    '-ComfyUIRoot', $config.ComfyUIRoot,
    '-SharedBasePath', $config.SharedBasePath,
    '-CustomNodeLoading', $config.CustomNodeLoading,
    '-AllowedCustomNodeFoldersBase64', $config.AllowedCustomNodeFoldersBase64,
    '-AcceleratorMutexName', $config.AcceleratorMutexName,
    '-Port', [string]$config.Port
)
$exact = Test-ManagedComfyUICommandLine `
    $config (ConvertTo-WindowsCommandLine $arguments)
$arguments[$arguments.IndexOf('-LaunchIdentity') + 1] = ('0' * 64)
$wrongIdentity = Test-ManagedComfyUICommandLine `
    $config (ConvertTo-WindowsCommandLine $arguments)
@{{ exact = $exact; wrong_identity = $wrongIdentity }} |
    ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )

    result = run_powershell(probe_script)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "exact": True,
        "wrong_identity": False,
    }


def test_backend_ownership_rejects_path_config_changed_after_launch(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    probe_script = tmp_path / "probe-ownership-config-change.ps1"
    probe_script.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. '{ps_single_quote(SCRIPT_DIR / "backend_common.ps1")}'
$config = Resolve-PixelleComfyUIBackendConfig `
    -PythonExe '{ps_single_quote(sys.executable)}' `
    -ComfyUIRoot '{ps_single_quote(comfyui_root)}' `
    -DataRoot '{ps_single_quote(data_root)}' `
    -SharedBasePath '{ps_single_quote(data_root)}' `
    -ExtraModelsConfig '{ps_single_quote(extra_models_config)}' `
    -RuntimeDir '{ps_single_quote(runtime_dir)}' `
    -Port 65512
Write-BackendOwnershipRecord $config $PID $PID
$before = Test-BackendProcessOwnership $config $PID 'backend'
Set-Content `
    -LiteralPath '{ps_single_quote(extra_models_config)}' `
    -Value "pixelle:`n  base_path: D:/changed-after-launch" `
    -Encoding UTF8
$after = Test-BackendProcessOwnership $config $PID 'backend'
$record = Read-BackendOwnershipRecord $config
@{{ before = $before; after = $after; version = $record.version }} |
    ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )

    result = run_powershell(probe_script)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "before": True,
        "after": False,
        "version": 2,
    }


def test_start_backend_dry_run_uses_headless_safe_args(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    argv = payload["arguments"]

    assert payload["dry_run"] is True
    assert payload["would_start"] is True
    assert "--log-stdout" not in argv
    assert "--enable-manager" not in argv
    assert argv[:2] == [str(comfyui_root / "main.py"), "--user-directory"]
    assert "--listen" in argv
    assert argv[argv.index("--listen") + 1] == "127.0.0.1"
    assert "--port" in argv
    assert argv[argv.index("--port") + 1] == "65500"
    assert "--extra-model-paths-config" in argv
    assert "--front-end-root" not in argv
    assert "--enable-cors-header" not in argv


def test_start_backend_dry_run_loads_only_allowed_custom_nodes(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes --whitelist-custom-nodes",
    )
    custom_nodes_root = data_root / "custom_nodes"
    custom_nodes_root.mkdir()
    for folder in ("ComfyUI-OmniVoice-TTS", "ComfyUI-VideoHelperSuite"):
        (custom_nodes_root / folder).mkdir()
    encoded_folders = base64.b64encode(
        json.dumps(
            ["ComfyUI-OmniVoice-TTS", "ComfyUI-VideoHelperSuite"],
            separators=(",", ":"),
        ).encode("utf-8")
    ).decode("ascii")

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root / "pixelle-tts",
        "-SharedBasePath",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65502",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folders,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    argv = payload["arguments"]
    assert payload["custom_node_loading"] == "allowlist"
    assert payload["allowed_custom_node_folders"] == [
        "ComfyUI-OmniVoice-TTS",
        "ComfyUI-VideoHelperSuite",
    ]
    assert (
        payload["accelerator_mutex_name"]
        == "Global\\Pixelle-ComfyUI-Accelerator-v1"
    )
    assert "--disable-all-custom-nodes" in argv
    allowlist_index = argv.index("--whitelist-custom-nodes")
    assert argv[allowlist_index + 1 :] == [
        "ComfyUI-OmniVoice-TTS",
        "ComfyUI-VideoHelperSuite",
    ]
    assert "ComfyUI-nunchaku" not in argv


def test_custom_node_process_identity_rejects_extra_allowlisted_folder(
    tmp_path: Path,
) -> None:
    probe_script = tmp_path / "probe-custom-node-policy.ps1"
    common_script = ps_single_quote(SCRIPT_DIR / "backend_common.ps1")
    probe_script.write_text(
        f"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. '{common_script}'
$config = @{{
    CustomNodeLoading = 'allowlist'
    AllowedCustomNodeFolders = @('ComfyUI-GGUF', 'ComfyUI-Easy-Use')
}}
$exact = Test-BackendCustomNodePolicyCommandLine `
    $config `
    'python main.py --disable-all-custom-nodes --whitelist-custom-nodes ComfyUI-GGUF ComfyUI-Easy-Use'
$extra = Test-BackendCustomNodePolicyCommandLine `
    $config `
    'python main.py --disable-all-custom-nodes --whitelist-custom-nodes ComfyUI-GGUF ComfyUI-Easy-Use ComfyUI-nunchaku'
$laterFlag = Test-BackendCustomNodePolicyCommandLine `
    $config `
    'python main.py --disable-all-custom-nodes --whitelist-custom-nodes ComfyUI-GGUF ComfyUI-Easy-Use --preview-method auto'
$duplicateOption = Test-BackendCustomNodePolicyCommandLine `
    $config `
    'python main.py --disable-all-custom-nodes --whitelist-custom-nodes ComfyUI-GGUF ComfyUI-Easy-Use --whitelist-custom-nodes ComfyUI-GGUF ComfyUI-Easy-Use'
@{{
    exact = $exact
    extra = $extra
    later_flag = $laterFlag
    duplicate_option = $duplicateOption
}} | ConvertTo-Json -Compress
""".strip(),
        encoding="utf-8",
    )

    result = run_powershell(probe_script)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "exact": True,
        "extra": False,
        "later_flag": True,
        "duplicate_option": False,
    }


def test_start_backend_rejects_missing_allowed_custom_node(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes --whitelist-custom-nodes",
    )
    encoded_folders = base64.b64encode(
        json.dumps(["Missing-Custom-Node"]).encode("utf-8")
    ).decode("ascii")

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-Port",
        "65503",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folders,
    )

    assert result.returncode != 0
    assert "does not exist" in (result.stdout + result.stderr)


def test_start_backend_rejects_scalar_custom_node_payload(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    encoded_folder = base64.b64encode(
        json.dumps("ComfyUI-GGUF").encode("utf-8")
    ).decode("ascii")

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folder,
    )

    assert result.returncode != 0
    assert "base64 JSON" in (result.stdout + result.stderr)


def test_backend_diagnostic_tail_reads_utf8_without_a_byte_order_mark(
    tmp_path: Path,
) -> None:
    diagnostic_log = tmp_path / "diagnostic.log"
    diagnostic_log.write_bytes("插件加载错误\n".encode("utf-8"))
    probe_script = tmp_path / "probe-diagnostic-tail.ps1"
    probe_script.write_text(
        "\n".join(
            [
                f". '{ps_single_quote(SCRIPT_DIR / 'backend_common.ps1')}'",
                "$tail = Get-BackendDiagnosticTail -Paths "
                f"@('{ps_single_quote(diagnostic_log)}')",
                "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($tail))",
            ]
        ),
        encoding="utf-8",
    )

    result = run_powershell(probe_script)

    assert result.returncode == 0, result.stderr
    decoded_tail = base64.b64decode(result.stdout.strip()).decode("utf-8")
    assert "插件加载错误" in decoded_tail


def test_start_backend_ignores_unregistered_application_custom_node_copy(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes "
        "--whitelist-custom-nodes",
    )
    folder = "ComfyUI-GGUF"
    (comfyui_root / "custom_nodes" / folder).mkdir(parents=True)
    (data_root / "custom_nodes" / folder).mkdir(parents=True)
    encoded_folder = base64.b64encode(json.dumps([folder]).encode("utf-8")).decode(
        "ascii"
    )

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root / "profile",
        "-SharedBasePath",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folder,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["effective_custom_node_roots"] == [
        str((data_root / "custom_nodes").resolve())
    ]
    assert payload["allowed_custom_node_folders"] == [folder]


def test_start_backend_deduplicates_the_same_custom_node_root(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes "
        "--whitelist-custom-nodes",
    )
    folder = "ComfyUI-GGUF"
    custom_nodes_root = data_root / "custom_nodes"
    (custom_nodes_root / folder).mkdir(parents=True)
    (comfyui_root / "extra_model_paths.yaml").write_text(
        "external_comfyui:\n"
        f"  base_path: {data_root.as_posix()}\n"
        "  is_default: true\n"
        "  custom_nodes: custom_nodes/\n",
        encoding="utf-8",
    )
    encoded_folder = base64.b64encode(json.dumps([folder]).encode("utf-8")).decode(
        "ascii"
    )

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-SharedBasePath",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folder,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["effective_custom_node_roots"] == [str(custom_nodes_root.resolve())]
    assert payload["allowed_custom_node_folders"] == [folder]


def test_start_backend_rejects_a_second_effective_custom_node_root(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes "
        "--whitelist-custom-nodes",
    )
    folder = "ComfyUI-GGUF"
    (data_root / "custom_nodes" / folder).mkdir(parents=True)
    second_root = tmp_path / "SecondComfyUIData"
    (second_root / "custom_nodes").mkdir(parents=True)
    (comfyui_root / "extra_model_paths.yaml").write_text(
        "external_comfyui:\n"
        f"  base_path: {second_root.as_posix()}\n"
        "  custom_nodes: custom_nodes/\n",
        encoding="utf-8",
    )
    encoded_folder = base64.b64encode(json.dumps([folder]).encode("utf-8")).decode(
        "ascii"
    )

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-SharedBasePath",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folder,
    )

    assert result.returncode != 0
    diagnostic = result.stdout + result.stderr
    assert "requires exactly one effective custom_nodes root" in diagnostic
    assert "ComfyUIData\\custom_nodes" in diagnostic
    assert "SecondComfyUIData\\custom_nodes" in diagnostic


def test_start_backend_rejects_case_aliases_of_the_effective_custom_node_root(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes "
        "--whitelist-custom-nodes",
    )
    folder = "ComfyUI-GGUF"
    (data_root / "custom_nodes" / folder).mkdir(parents=True)
    (comfyui_root / "extra_model_paths.yaml").write_text(
        "external_comfyui:\n"
        f"  base_path: {str(data_root).swapcase().replace(os.sep, '/')}\n"
        "  custom_nodes: custom_nodes/\n",
        encoding="utf-8",
    )
    encoded_folder = base64.b64encode(json.dumps([folder]).encode("utf-8")).decode(
        "ascii"
    )

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-SharedBasePath",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folder,
    )

    assert result.returncode != 0
    assert "resolved 2" in (result.stdout + result.stderr)


def test_custom_node_root_error_does_not_leak_configuration_contents(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_comfyui_cli_args(
        comfyui_root,
        "--disable-pinned-memory --disable-all-custom-nodes "
        "--whitelist-custom-nodes",
    )
    folder = "ComfyUI-GGUF"
    (data_root / "custom_nodes" / folder).mkdir(parents=True)
    secret = "path-secret-must-not-leak"
    (comfyui_root / "extra_model_paths.yaml").write_text(
        f"broken: [{secret}\n",
        encoding="utf-8",
    )
    encoded_folder = base64.b64encode(json.dumps([folder]).encode("utf-8")).decode(
        "ascii"
    )

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-SharedBasePath",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-CustomNodeLoading",
        "allowlist",
        "-AllowedCustomNodeFoldersBase64",
        encoded_folder,
    )

    diagnostic = result.stdout + result.stderr
    assert result.returncode != 0
    assert "could not load ComfyUI path configuration" in diagnostic
    assert secret not in diagnostic


def test_custom_node_root_resolver_timeout_is_bounded(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    (comfyui_root / "comfy" / "options.py").write_text(
        "import time\n"
        "time.sleep(5)\n"
        "args_parsing = False\n"
        "def enable_args_parsing(enable=True):\n"
        "    global args_parsing\n"
        "    args_parsing = enable\n",
        encoding="utf-8",
    )
    probe_script = tmp_path / "probe-resolver-timeout.ps1"
    probe_script.write_text(
        "\n".join(
            [
                f". '{ps_single_quote(SCRIPT_DIR / 'backend_common.ps1')}'",
                "$config = Resolve-PixelleComfyUIBackendConfig "
                f"-PythonExe '{ps_single_quote(sys.executable)}' "
                f"-ComfyUIRoot '{ps_single_quote(comfyui_root)}' "
                f"-DataRoot '{ps_single_quote(data_root)}' "
                f"-SharedBasePath '{ps_single_quote(data_root)}' "
                f"-ExtraModelsConfig '{ps_single_quote(extra_models_config)}' "
                f"-RuntimeDir '{ps_single_quote(tmp_path / 'runtime')}'",
                "Invoke-BackendCustomNodeRootResolver $config 300",
            ]
        ),
        encoding="utf-8",
    )

    started_at = time.monotonic()
    result = run_powershell(probe_script)
    elapsed = time.monotonic() - started_at

    assert result.returncode != 0
    assert elapsed < 4
    assert "exceeded 300 milliseconds" in (result.stdout + result.stderr)


def test_start_backend_memory_safe_policy_preserves_batch_reuse_and_offload(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    (comfyui_root / "comfy" / "cli_args.py").write_text(
        "--disable-pinned-memory",
        encoding="utf-8",
    )
    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-ResourcePolicy",
        "memory_safe",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["resource_policy"] == "memory_safe"
    assert "--disable-pinned-memory" in payload["arguments"]
    assert "--disable-async-offload" not in payload["arguments"]
    assert "--disable-dynamic-vram" not in payload["arguments"]
    assert "--cache-none" not in payload["arguments"]


def test_start_backend_auto_policy_defaults_to_memory_safe(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-ResourcePolicy",
        "auto",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["requested_resource_policy"] == "auto"
    assert payload["resource_policy"] == "memory_safe"
    assert "--disable-pinned-memory" in payload["arguments"]
    assert "--disable-async-offload" not in payload["arguments"]
    assert "--cache-none" not in payload["arguments"]
    assert payload["minimum_free_commit_mode"] == "automatic"
    assert 2 <= payload["minimum_free_commit_gb"] <= 6


def test_start_backend_resolves_relative_runtime_and_log_paths_from_repo_root(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    runtime_dir = Path("_runtime") / "tests" / tmp_path.name / "runtime"
    logs_dir = Path("_runtime") / "tests" / tmp_path.name / "logs"

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["runtime_dir"]) == (REPO_ROOT / runtime_dir).resolve()
    assert Path(payload["logs_dir"]) == (REPO_ROOT / logs_dir).resolve()
    assert Path(payload["stdout_log"]).parent == (REPO_ROOT / logs_dir).resolve()
    assert Path(payload["supervisor_stderr_log"]).parent == (REPO_ROOT / logs_dir).resolve()


def test_start_backend_memory_safe_policy_fails_when_support_is_unverifiable(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    (comfyui_root / "comfy" / "cli_args.py").unlink()

    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-ResourcePolicy",
        "memory_safe",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode != 0
    assert "cannot prove support" in result.stderr


def test_data_root_environment_does_not_override_shared_base_path(tmp_path: Path) -> None:
    data_root = tmp_path / "isolated" / "pixelle"
    shared_root = tmp_path / "shared"
    environment = os.environ.copy()
    environment["PIXELLE_COMFYUI_DATA_ROOT"] = str(data_root)
    environment["PIXELLE_COMFYUI_SHARED_BASE_PATH"] = str(shared_root)
    command = [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            ". (Join-Path $PWD 'scripts/comfyui/backend_common.ps1'); "
            "$config = Resolve-PixelleComfyUIBackendConfig; "
            "$config | ConvertTo-Json -Compress"
        ),
    ]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["DataRoot"] == str(data_root)
    assert payload["SharedBasePath"] == str(shared_root)
    assert payload["PythonExe"] == str(shared_root / ".venv" / "Scripts" / "python.exe")


def test_localhost_is_normalized_to_numeric_loopback(tmp_path: Path) -> None:
    comfyui_root, data_root, _ = make_fake_comfyui(tmp_path)
    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-DryRun",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-RuntimeDir",
        tmp_path / "runtime",
        "-LogsDir",
        tmp_path / "logs",
        "-HostAddress",
        "localhost",
        "-Port",
        "65499",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["host"] == "127.0.0.1"
    argv = payload["arguments"]
    assert argv[argv.index("--listen") + 1] == "127.0.0.1"
    assert "--database-url" in argv
    database_path = str(data_root / "user" / "comfyui.db").replace("\\", "/")
    expected_database_url = f"sqlite:///{database_path}"
    assert argv[argv.index("--database-url") + 1] == expected_database_url


def test_start_backend_refuses_occupied_port_even_in_dry_run(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        occupied_port = listener.getsockname()[1]

        result = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-DryRun",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            tmp_path / "runtime",
            "-LogsDir",
            tmp_path / "logs",
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(occupied_port),
        )

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    assert "already in use" in combined_output
    assert "Refusing to start" in combined_output


def test_start_backend_refuses_wildcard_address_port_conflict(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen(1)
        occupied_port = listener.getsockname()[1]

        result = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-DryRun",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            tmp_path / "runtime",
            "-LogsDir",
            tmp_path / "logs",
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(occupied_port),
        )

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    assert "already in use" in combined_output
    assert "Refusing to start" in combined_output


def test_stop_backend_without_pid_file_is_safe_noop(tmp_path: Path) -> None:
    port = reserve_free_port()
    runtime_dir = tmp_path / "runtime" / "image"
    logs_dir = tmp_path / "logs" / "image"
    data_root = tmp_path / "data" / "image"
    result = run_powershell(
        SCRIPT_DIR / "stop_backend.ps1",
        "-Json",
        "-ProfileName",
        "image",
        "-DataRoot",
        data_root,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        str(port),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["stopped"] is False
    assert payload["reason"] == "pid_file_missing"
    assert payload["profile"] == "image"
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == port
    assert payload["data_root"] == str(data_root)
    assert payload["runtime_dir"] == str(runtime_dir)
    assert payload["logs_dir"] == str(logs_dir)
    assert payload["pid_file"] == str(runtime_dir / "comfyui-backend.pid")
    assert payload["launcher_pid_file"] == str(runtime_dir / "comfyui-backend.launcher.pid")
    assert payload["stdout_log"] == str(logs_dir / "comfyui-backend.stdout.log")
    assert payload["stderr_log"] == str(logs_dir / "comfyui-backend.stderr.log")


def test_stop_backend_preserves_matching_listener_without_pid_file(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    port = reserve_free_port()

    try:
        process = start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is False
        assert isinstance(payload["listener_pid"], int)
        assert payload["listener_pid"] > 0
        assert payload["reason"] == "pid_file_missing"
        assert process.poll() is None
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_removes_invalid_pid_files(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    pid_file = runtime_dir / "comfyui-backend.pid"
    launcher_pid_file = runtime_dir / "comfyui-backend.launcher.pid"
    pid_file.write_text("not-a-pid", encoding="ascii")
    launcher_pid_file.write_text("also-not-a-pid", encoding="ascii")
    port = reserve_free_port()

    result = run_powershell(
        SCRIPT_DIR / "stop_backend.ps1",
        "-Json",
        "-RuntimeDir",
        runtime_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        str(port),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["stopped"] is False
    assert payload["reason"] == "pid_file_invalid"
    assert not pid_file.exists()
    assert not launcher_pid_file.exists()


def test_stop_backend_preserves_matching_listener_when_pid_file_is_invalid(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "comfyui-backend.pid").write_text("not-a-pid", encoding="ascii")
    (runtime_dir / "comfyui-backend.launcher.pid").write_text(
        "also-not-a-pid",
        encoding="ascii",
    )
    port = reserve_free_port()

    try:
        process = start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is False
        assert payload["reason"] == "pid_file_invalid"
        assert process.poll() is None
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_preserves_matching_listener_when_pid_file_is_stale(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "comfyui-backend.pid").write_text("999999", encoding="ascii")
    port = reserve_free_port()

    try:
        process = start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is False
        assert payload["reason"] == "process_missing"
        assert payload["pid"] == 999999
        assert process.poll() is None
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_preserves_matching_listener_when_pid_file_points_elsewhere(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "comfyui-backend.pid").write_text(
        str(os.getpid()),
        encoding="ascii",
    )
    port = reserve_free_port()

    try:
        process = start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is False
        assert payload["reason"] == "pid_file_points_to_unmanaged_process"
        assert payload["pid"] == os.getpid()
        assert process.poll() is None
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_check_backend_reports_clear_port_without_side_effects(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime" / "image"
    logs_dir = tmp_path / "logs" / "image"
    data_root = tmp_path / "data" / "image"
    result = run_powershell(
        SCRIPT_DIR / "check_backend.ps1",
        "-Json",
        "-ProfileName",
        "image",
        "-DataRoot",
        data_root,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        "65500",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["listener_present"] is False
    assert payload["pid_file_present"] is False
    assert payload["profile"] == "image"
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 65500
    assert payload["data_root"] == str(data_root)
    assert payload["runtime_dir"] == str(runtime_dir)
    assert payload["logs_dir"] == str(logs_dir)
    assert payload["pid_file"] == str(runtime_dir / "comfyui-backend.pid")
    assert payload["launcher_pid_file"] == str(runtime_dir / "comfyui-backend.launcher.pid")
    assert payload["stdout_log"] == str(logs_dir / "comfyui-backend.stdout.log")
    assert payload["stderr_log"] == str(logs_dir / "comfyui-backend.stderr.log")


def test_check_backend_does_not_claim_matching_process_without_pid_file(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    port = reserve_free_port()
    process = start_fake_listening_comfyui(comfyui_root, data_root, port)
    try:
        result = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            tmp_path / "runtime",
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["listener_present"] is True
    assert payload["pid_file_present"] is False
    assert payload["listener_is_managed_backend"] is False


def test_start_backend_tracks_listener_pid_when_launcher_spawns_child(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_reexec_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    logs_dir = tmp_path / "logs"
    port = reserve_free_port()

    try:
        result = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
            "-ReadyTimeoutSeconds",
            "8",
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["started"] is True
        assert payload["pid"] != payload["launched_pid"]

        pid_file = runtime_dir / "comfyui-backend.pid"
        launch_pid_file = runtime_dir / "comfyui-backend.launcher.pid"
        assert int(pid_file.read_text(encoding="ascii").strip()) == payload["pid"]
        assert int(launch_pid_file.read_text(encoding="ascii").strip()) == payload["launched_pid"]

        check = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert check.returncode == 0, check.stderr
        check_payload = json.loads(check.stdout)
        assert check_payload["listener_is_managed_backend"] is True

        pid_file.unlink()
        launch_pid_file.unlink()
        recovered_check = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert recovered_check.returncode == 0, recovered_check.stderr
        assert json.loads(recovered_check.stdout)["listener_is_managed_backend"] is True

        idempotent_start = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert idempotent_start.returncode == 0, idempotent_start.stderr
        assert json.loads(idempotent_start.stdout)["already_running"] is True
        assert pid_file.exists()

        stop = run_powershell(
            SCRIPT_DIR / "stop_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert stop.returncode == 0, stop.stderr
        stop_payload = json.loads(stop.stdout)
        assert stop_payload["stopped"] is True
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_start_backend_preserves_supervisor_arguments_with_spaces(
    tmp_path: Path,
) -> None:
    spaced_root = tmp_path / "installation with spaces"
    spaced_root.mkdir()
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(spaced_root)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = spaced_root / "runtime files"
    logs_dir = spaced_root / "log files"
    port = reserve_free_port()

    try:
        start = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
            "-ReadyTimeoutSeconds",
            "8",
        )
        assert start.returncode == 0, start.stderr
        start_payload = json.loads(start.stdout)
        assert start_payload["started"] is True

        stop = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )
        assert stop.returncode == 0, stop.stderr
        assert json.loads(stop.stdout)["stopped"] is True
        wait_for_process_exit(start_payload["launched_pid"])
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_terminates_owned_service_descendants(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_reexec_with_worker_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    logs_dir = tmp_path / "logs"
    port = reserve_free_port()

    try:
        start = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
            "-ReadyTimeoutSeconds",
            "8",
        )
        assert start.returncode == 0, start.stderr

        worker_pid_file = comfyui_root / "worker.pid"
        deadline = time.monotonic() + 5
        while not worker_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert worker_pid_file.exists()
        worker_pid = int(worker_pid_file.read_text(encoding="utf-8"))
        assert windows_process_is_running(worker_pid)

        stop = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert stop.returncode == 0, stop.stderr
        stop_payload = json.loads(stop.stdout)
        assert stop_payload["stopped"] is True, json.dumps(stop_payload, indent=2)
        wait_for_process_exit(worker_pid)
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_stops_owned_launcher_after_listener_crashes(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_reexec_main_py(comfyui_root)
    main_py = comfyui_root / "main.py"
    main_py.write_text(
        main_py.read_text(encoding="utf-8").replace("time.sleep(4)", "time.sleep(20)"),
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    launcher_process = subprocess.Popen(
        fake_listening_comfyui_command(comfyui_root, data_root, port)
    )

    try:
        wait_for_port(port)
        check = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert check.returncode == 0, check.stderr
        listener_pid = json.loads(check.stdout)["listener_pid"]
        launcher_pid = launcher_process.pid
        assert listener_pid != launcher_pid
        (runtime_dir / "comfyui-backend.pid").write_text(
            str(listener_pid),
            encoding="ascii",
        )
        (runtime_dir / "comfyui-backend.launcher.pid").write_text(
            str(launcher_pid),
            encoding="ascii",
        )
        write_fake_backend_ownership(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
            backend_pid=listener_pid,
            launcher_pid=launcher_pid,
        )

        stop_process_for_test(listener_pid)
        wait_for_process_exit(listener_pid)
        assert windows_process_is_running(launcher_pid)

        stop = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
            shared_base_path=data_root,
        )

        assert stop.returncode == 0, stop.stderr
        stop_payload = json.loads(stop.stdout)
        assert stop_payload["stopped"] is True
        assert stop_payload["reason"] == "process_missing"
        assert stop_payload["stopped_launcher"] is True
        wait_for_process_exit(launcher_pid)
        assert not (runtime_dir / "comfyui-backend.owner.json").exists()
    finally:
        if launcher_process.poll() is None:
            launcher_process.terminate()
            launcher_process.wait(timeout=10)
        kill_fake_comfyui_processes(comfyui_root)


def test_start_backend_forces_utf8_child_output_encoding(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_unicode_sensitive_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    logs_dir = tmp_path / "logs"
    port = reserve_free_port()

    try:
        result = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
            "-ReadyTimeoutSeconds",
            "8",
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["started"] is True
        assert (logs_dir / "comfyui-backend.stdout.log").read_text(
            encoding="utf-8"
        ).startswith("\U0001f389 fake comfyui started")
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_start_backend_archives_existing_backend_logs_before_launch(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_short_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    stdout_log = logs_dir / "comfyui-backend.stdout.log"
    stderr_log = logs_dir / "comfyui-backend.stderr.log"
    stdout_log.write_text("old stdout crash\n", encoding="utf-8")
    stderr_log.write_text("old stderr crash\n", encoding="utf-8")
    port = reserve_free_port()

    try:
        result = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
            "-ReadyTimeoutSeconds",
            "8",
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        archived_stdout_log = Path(payload["previous_stdout_log"])
        archived_stderr_log = Path(payload["previous_stderr_log"])

        assert archived_stdout_log.exists()
        assert archived_stderr_log.exists()
        assert archived_stdout_log.read_text(encoding="utf-8") == "old stdout crash\n"
        assert archived_stderr_log.read_text(encoding="utf-8") == "old stderr crash\n"
        assert archived_stdout_log.name.startswith("comfyui-backend.stdout.")
        assert archived_stderr_log.name.startswith("comfyui-backend.stderr.")
        assert stdout_log.read_text(encoding="utf-8").startswith("fake comfyui listening")
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_preserves_legacy_pid_record_without_ownership_file(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_reexec_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    command = fake_listening_comfyui_command(comfyui_root, data_root, port)
    process = subprocess.Popen(command)

    try:
        wait_for_port(port)
        (runtime_dir / "comfyui-backend.pid").write_text(
            str(process.pid),
            encoding="ascii",
        )

        stop = run_powershell(
            SCRIPT_DIR / "stop_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-SharedBasePath",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert stop.returncode == 0, stop.stderr
        payload = json.loads(stop.stdout)
        assert payload["stopped"] is False
        assert payload["reason"] == "ownership_record_missing_or_mismatch"
        assert process.poll() is None

        check = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert check.returncode == 0, check.stderr
        assert json.loads(check.stdout)["listener_present"] is True
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_preserves_matching_pid_when_creation_time_changed(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    process = start_fake_listening_comfyui(comfyui_root, data_root, port)

    try:
        (runtime_dir / "comfyui-backend.pid").write_text(
            str(process.pid),
            encoding="ascii",
        )
        (runtime_dir / "comfyui-backend.launcher.pid").write_text(
            str(process.pid),
            encoding="ascii",
        )
        write_fake_backend_ownership(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
            backend_pid=process.pid,
            launcher_pid=process.pid,
        )
        ownership_file = runtime_dir / "comfyui-backend.owner.json"
        ownership = json.loads(ownership_file.read_text(encoding="utf-8-sig"))
        ownership["backend_creation_time_utc"] = "2000-01-01T00:00:00.0000000Z"
        ownership_file.write_text(json.dumps(ownership), encoding="utf-8")

        stop = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
            shared_base_path=data_root,
        )

        assert stop.returncode == 0, stop.stderr
        payload = json.loads(stop.stdout)
        assert payload["stopped"] is False
        assert payload["reason"] == "ownership_record_missing_or_mismatch"
        assert process.poll() is None

        (runtime_dir / "comfyui-backend.pid").write_text(
            str(process.pid),
            encoding="ascii",
        )
        (runtime_dir / "comfyui-backend.launcher.pid").write_text(
            str(process.pid),
            encoding="ascii",
        )
        ownership_file.write_text("{}", encoding="utf-8")

        malformed_stop = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
            shared_base_path=data_root,
        )

        assert malformed_stop.returncode == 0, malformed_stop.stderr
        assert json.loads(malformed_stop.stdout)["reason"] == (
            "ownership_record_missing_or_mismatch"
        )
        assert process.poll() is None
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_does_not_kill_unmanaged_parent_launcher(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    launcher_path = tmp_path / "external_launcher.py"
    write_fake_external_launcher(launcher_path, comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    listener_arguments = fake_listening_comfyui_command(
        comfyui_root,
        data_root,
        port,
    )[2:]
    launcher = subprocess.Popen(
        [sys.executable, str(launcher_path), *listener_arguments]
    )

    try:
        wait_for_port(port)
        listener_check = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert listener_check.returncode == 0, listener_check.stderr
        listener_pid = json.loads(listener_check.stdout)["listener_pid"]
        (runtime_dir / "comfyui-backend.pid").write_text(
            str(listener_pid),
            encoding="ascii",
        )
        (runtime_dir / "comfyui-backend.launcher.pid").write_text(
            str(launcher.pid),
            encoding="ascii",
        )

        stop = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
            shared_base_path=data_root,
        )

        assert stop.returncode == 0, stop.stderr
        payload = json.loads(stop.stdout)
        assert payload["stopped"] is False
        assert payload["reason"] == "ownership_record_missing_or_mismatch"
        assert launcher.poll() is None
    finally:
        launcher.terminate()
        try:
            launcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill()
            launcher.wait(timeout=10)
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_cleans_owned_orphan_and_preserves_external_listener(
    tmp_path: Path,
) -> None:
    owned_dir = tmp_path / "owned"
    external_dir = tmp_path / "external"
    owned_dir.mkdir()
    external_dir.mkdir()
    owned_root, owned_data, owned_models = make_fake_comfyui(owned_dir)
    external_root, external_data, _ = make_fake_comfyui(external_dir)
    write_fake_hanging_main_py(owned_root)
    write_fake_listening_main_py(external_root)
    runtime_dir = owned_dir / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    owned_process = subprocess.Popen(
        fake_listening_comfyui_command(owned_root, owned_data, port)
    )
    external_process = None

    try:
        (runtime_dir / "comfyui-backend.pid").write_text(
            str(owned_process.pid),
            encoding="ascii",
        )
        (runtime_dir / "comfyui-backend.launcher.pid").write_text(
            str(owned_process.pid),
            encoding="ascii",
        )
        write_fake_backend_ownership(
            comfyui_root=owned_root,
            data_root=owned_data,
            extra_models_config=owned_models,
            runtime_dir=runtime_dir,
            port=port,
            backend_pid=owned_process.pid,
            launcher_pid=owned_process.pid,
        )
        external_process = start_fake_listening_comfyui(
            external_root,
            external_data,
            port,
        )

        stop = run_fake_backend_stop(
            comfyui_root=owned_root,
            data_root=owned_data,
            extra_models_config=owned_models,
            runtime_dir=runtime_dir,
            port=port,
            shared_base_path=owned_data,
        )

        assert stop.returncode == 0, stop.stderr
        payload = json.loads(stop.stdout)
        assert payload["stopped"] is True
        assert payload["reason"] == "owned_process_stopped_external_listener_preserved"
        assert payload["preserved_external_listener"] is True
        owned_process.wait(timeout=10)
        assert external_process.poll() is None
        assert not (runtime_dir / "comfyui-backend.pid").exists()
        assert not (runtime_dir / "comfyui-backend.owner.json").exists()
    finally:
        if owned_process.poll() is None:
            owned_process.terminate()
            owned_process.wait(timeout=10)
        if external_process is not None and external_process.poll() is None:
            external_process.terminate()
            external_process.wait(timeout=10)
        kill_fake_comfyui_processes(owned_root)
        kill_fake_comfyui_processes(external_root)


def test_stop_backend_clears_unmanaged_stale_pid_without_listener(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    pid_file = runtime_dir / "comfyui-backend.pid"
    launcher_pid_file = runtime_dir / "comfyui-backend.launcher.pid"
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    launcher_pid_file.write_text(str(os.getpid()), encoding="ascii")
    port = reserve_free_port()

    result = run_powershell(
        SCRIPT_DIR / "stop_backend.ps1",
        "-Json",
        "-RuntimeDir",
        runtime_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        str(port),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["stopped"] is False
    assert payload["reason"] == "pid_file_points_to_unmanaged_process"
    assert not pid_file.exists()
    assert not launcher_pid_file.exists()


def test_start_backend_cleans_up_when_backend_never_listens(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_hanging_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    logs_dir = tmp_path / "logs"
    port = reserve_free_port()

    try:
        result = run_powershell(
            SCRIPT_DIR / "start_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-LogsDir",
            logs_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
            "-ReadyTimeoutSeconds",
            "1",
        )

        assert result.returncode != 0
        assert "did not listen" in (result.stdout + result.stderr)
        assert not (runtime_dir / "comfyui-backend.pid").exists()
        assert not (runtime_dir / "comfyui-backend.launcher.pid").exists()

        check = run_powershell(
            SCRIPT_DIR / "check_backend.ps1",
            "-Json",
            "-PythonExe",
            sys.executable,
            "-ComfyUIRoot",
            comfyui_root,
            "-DataRoot",
            data_root,
            "-ExtraModelsConfig",
            extra_models_config,
            "-RuntimeDir",
            runtime_dir,
            "-HostAddress",
            "127.0.0.1",
            "-Port",
            str(port),
        )
        assert check.returncode == 0, check.stderr
        assert json.loads(check.stdout)["listener_present"] is False
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_start_backend_reports_early_backend_exit_without_waiting_for_timeout(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_failing_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    logs_dir = tmp_path / "logs"
    port = reserve_free_port()

    started_at = time.monotonic()
    result = run_powershell(
        SCRIPT_DIR / "start_backend.ps1",
        "-Json",
        "-PythonExe",
        sys.executable,
        "-ComfyUIRoot",
        comfyui_root,
        "-DataRoot",
        data_root,
        "-ExtraModelsConfig",
        extra_models_config,
        "-RuntimeDir",
        runtime_dir,
        "-LogsDir",
        logs_dir,
        "-HostAddress",
        "127.0.0.1",
        "-Port",
        str(port),
        "-ReadyTimeoutSeconds",
        "8",
    )
    elapsed = time.monotonic() - started_at

    combined_output = result.stdout + result.stderr
    assert result.returncode != 0
    assert elapsed < 5
    assert "exited with code 23" in combined_output
    assert "deliberate backend failure" in combined_output
    assert "api_key=[REDACTED]" in combined_output
    assert "do-not-expose" not in combined_output
    assert "json-do-not-expose" not in combined_output
    assert "bearer-do-not-expose" not in combined_output
    assert "comfyui-backend.stderr.log" in combined_output
    assert not (runtime_dir / "comfyui-backend.pid").exists()
    assert not (runtime_dir / "comfyui-backend.launcher.pid").exists()


def test_backend_supervisor_writes_its_own_startup_failure_log(tmp_path: Path) -> None:
    stdout_log = tmp_path / "backend.stdout.log"
    stderr_log = tmp_path / "backend.stderr.log"
    supervisor_stderr_log = tmp_path / "supervisor.stderr.log"
    exit_code_file = tmp_path / "backend.exit-code"
    arguments_base64 = base64.b64encode(json.dumps([]).encode("utf-8")).decode("ascii")

    result = run_powershell(
        SCRIPT_DIR / "backend_supervisor.ps1",
        "-PythonExe",
        tmp_path / "missing-python.exe",
        "-WorkingDirectory",
        tmp_path,
        "-StdoutLog",
        stdout_log,
        "-StderrLog",
        stderr_log,
        "-SupervisorStderrLog",
        supervisor_stderr_log,
        "-ExitCodeFile",
        exit_code_file,
        "-ArgumentsBase64",
        arguments_base64,
        "-AcceleratorMutexName",
        f"Local\\Pixelle-Test-{uuid.uuid4().hex}",
    )

    assert result.returncode != 0
    assert supervisor_stderr_log.exists()
    assert supervisor_stderr_log.read_text(encoding="utf-8").strip()
    assert not exit_code_file.exists()


def test_backend_supervisor_waits_for_a_transient_accelerator_handoff(
    tmp_path: Path,
) -> None:
    mutex_name = f"Local\\Pixelle-Test-{uuid.uuid4().hex}"
    ready_file = tmp_path / "holder-ready"
    holder_script = tmp_path / "hold-mutex.ps1"
    holder_script.write_text(
        "\n".join(
            [
                f"$mutex = [Threading.Mutex]::new($false, '{mutex_name}')",
                "$acquired = $mutex.WaitOne()",
                f"Set-Content -LiteralPath '{ps_single_quote(ready_file)}' -Value ready",
                "Start-Sleep -Milliseconds 500",
                "if ($acquired) { $mutex.ReleaseMutex() }",
                "$mutex.Dispose()",
            ]
        ),
        encoding="utf-8",
    )
    holder = subprocess.Popen(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(holder_script),
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not ready_file.exists() and time.monotonic() < deadline:
            if holder.poll() is not None:
                raise AssertionError("mutex holder exited before signaling readiness")
            time.sleep(0.05)
        assert ready_file.exists()

        arguments_base64 = base64.b64encode(
            json.dumps(["-c", "pass"]).encode("utf-8")
        ).decode("ascii")
        started_at = time.monotonic()
        result = run_powershell(
            SCRIPT_DIR / "backend_supervisor.ps1",
            "-PythonExe",
            sys.executable,
            "-WorkingDirectory",
            tmp_path,
            "-StdoutLog",
            tmp_path / "backend.stdout.log",
            "-StderrLog",
            tmp_path / "backend.stderr.log",
            "-SupervisorStderrLog",
            tmp_path / "supervisor.stderr.log",
            "-ExitCodeFile",
            tmp_path / "backend.exit-code",
            "-ArgumentsBase64",
            arguments_base64,
            "-AcceleratorMutexName",
            mutex_name,
            "-AcceleratorMutexWaitMilliseconds",
            "3000",
        )
        elapsed = time.monotonic() - started_at
    finally:
        holder.wait(timeout=10)

    assert result.returncode == 0, result.stderr
    assert 0.2 <= elapsed < 3


def test_backend_supervisor_allows_only_one_accelerator_owner(
    tmp_path: Path,
) -> None:
    mutex_name = f"Local\\Pixelle-Test-{uuid.uuid4().hex}"
    arguments_base64 = base64.b64encode(
        json.dumps(["-c", "import time; time.sleep(30)"]).encode("utf-8")
    ).decode("ascii")

    def supervisor_command(prefix: str) -> list[str]:
        return [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_DIR / "backend_supervisor.ps1"),
            "-PythonExe",
            sys.executable,
            "-WorkingDirectory",
            str(tmp_path),
            "-StdoutLog",
            str(tmp_path / f"{prefix}.stdout.log"),
            "-StderrLog",
            str(tmp_path / f"{prefix}.stderr.log"),
            "-SupervisorStderrLog",
            str(tmp_path / f"{prefix}.supervisor.stderr.log"),
            "-ExitCodeFile",
            str(tmp_path / f"{prefix}.exit-code"),
            "-ArgumentsBase64",
            arguments_base64,
            "-AcceleratorMutexName",
            mutex_name,
        ]

    first = subprocess.Popen(
        supervisor_command("first"),
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        first_stdout = tmp_path / "first.stdout.log"
        while not first_stdout.exists() and time.monotonic() < deadline:
            if first.poll() is not None:
                raise AssertionError("first supervisor exited before acquiring mutex")
            time.sleep(0.05)
        assert first_stdout.exists()

        second = subprocess.run(
            supervisor_command("second"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

        assert second.returncode != 0
        second_error = tmp_path / "second.supervisor.stderr.log"
        assert "[PIXELLE_ACCELERATOR_BUSY]" in second_error.read_text(
            encoding="utf-8"
        )
    finally:
        first.terminate()
        try:
            first.wait(timeout=10)
        except subprocess.TimeoutExpired:
            first.kill()
            first.wait(timeout=10)
