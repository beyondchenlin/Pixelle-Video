import json
import os
import socket
import subprocess
import sys
import time
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


def make_fake_comfyui(tmp_path: Path) -> tuple[Path, Path, Path]:
    comfyui_root = tmp_path / "ComfyUI"
    data_root = tmp_path / "ComfyUIData"
    comfyui_root.mkdir()
    (comfyui_root / "web_custom_versions" / "desktop_app").mkdir(parents=True)
    (comfyui_root / "main.py").write_text("print('fake comfyui')\n", encoding="utf-8")
    for name in ("input", "output", "user"):
        (data_root / name).mkdir(parents=True)
    extra_models_config = tmp_path / "extra_models_config.yaml"
    extra_models_config.write_text("pixelle:\n  base_path: E:/ComfyUIData\n", encoding="utf-8")
    return comfyui_root, data_root, extra_models_config


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
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
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
) -> subprocess.CompletedProcess[str]:
    return run_powershell(
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
    assert "--front-end-root" in argv
    assert argv[argv.index("--front-end-root") + 1] == str(
        comfyui_root / "web_custom_versions" / "desktop_app"
    )
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


def test_stop_backend_stops_matching_listener_without_pid_file(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    port = reserve_free_port()

    try:
        start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is True
        assert payload["pid"] is None
        assert isinstance(payload["listener_pid"], int)
        assert payload["listener_pid"] > 0
        assert payload["stopped_listener"] is True
        assert payload["reason"] == "matching_listener_without_pid_file"

        assert_fake_backend_listener_absent(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )
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


def test_stop_backend_stops_matching_listener_when_pid_file_is_invalid(
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
        start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is True
        assert payload["reason"] == "pid_file_invalid_matching_listener"
        assert payload["stopped_listener"] is True

        assert_fake_backend_listener_absent(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_stops_matching_listener_when_pid_file_is_stale(
    tmp_path: Path,
) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "comfyui-backend.pid").write_text("999999", encoding="ascii")
    port = reserve_free_port()

    try:
        start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is True
        assert payload["reason"] == "process_missing_matching_listener"
        assert payload["pid"] == 999999
        assert payload["stopped_listener"] is True

        assert_fake_backend_listener_absent(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )
    finally:
        kill_fake_comfyui_processes(comfyui_root)


def test_stop_backend_stops_matching_listener_when_pid_file_points_elsewhere(
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
        start_fake_listening_comfyui(comfyui_root, data_root, port)
        result = run_fake_backend_stop(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stopped"] is True
        assert payload["reason"] == "pid_file_unmanaged_matching_listener"
        assert payload["pid"] == os.getpid()
        assert payload["stopped_listener"] is True

        assert_fake_backend_listener_absent(
            comfyui_root=comfyui_root,
            data_root=data_root,
            extra_models_config=extra_models_config,
            runtime_dir=runtime_dir,
            port=port,
        )
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


def test_check_backend_marks_matching_process_as_managed_without_pid_file(
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
    assert payload["listener_is_managed_backend"] is True


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


def test_stop_backend_stops_listener_when_pid_file_points_to_launcher(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_reexec_main_py(comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    command = [
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
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
    ]
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
        assert payload["stopped"] is True
        assert payload["stopped_listener"] is True

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


def test_stop_backend_does_not_kill_unmanaged_parent_launcher(tmp_path: Path) -> None:
    comfyui_root, data_root, extra_models_config = make_fake_comfyui(tmp_path)
    write_fake_listening_main_py(comfyui_root)
    launcher_path = tmp_path / "external_launcher.py"
    write_fake_external_launcher(launcher_path, comfyui_root)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    port = reserve_free_port()
    launcher = subprocess.Popen(
        [
            sys.executable,
            str(launcher_path),
            "--user-directory",
            str(data_root / "user"),
            "--input-directory",
            str(data_root / "input"),
            "--output-directory",
            str(data_root / "output"),
            "--base-directory",
            str(data_root),
            "--listen",
            "127.0.0.1",
            "--port",
            str(port),
        ]
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
        )

        assert stop.returncode == 0, stop.stderr
        payload = json.loads(stop.stdout)
        assert payload["stopped"] is True
        assert payload["stopped_listener"] is True
        assert payload["stopped_launcher"] is False
        assert launcher.poll() is None
    finally:
        launcher.terminate()
        try:
            launcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill()
            launcher.wait(timeout=10)
        kill_fake_comfyui_processes(comfyui_root)


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
    assert payload["reason"] == "pid_file_points_to_unmanaged_process_without_listener"
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
