from pathlib import Path


def test_web_python_files_do_not_use_deprecated_use_container_width():
    project_root = Path(__file__).resolve().parent.parent
    web_dir = project_root / "web"
    offenders = []

    for path in web_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "use_container_width=" in text:
            offenders.append(path.relative_to(project_root).as_posix())

    assert offenders == []
