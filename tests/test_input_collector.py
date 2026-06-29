from __future__ import annotations

from pathlib import Path

from project_nurilab.input.collector import InputCollector
from project_nurilab.input.manager import PythonFileLoader


def test_input_collector_collects_python_files_and_excludes_dirs(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text(
        "eval('x')\n", encoding="utf-8"
    )

    collected = InputCollector().collect(tmp_path)

    assert collected.root_path == tmp_path.resolve()
    assert [path.name for path in collected.python_files] == ["app.py"]
    assert [path.path.name for path in collected.skipped_paths] == ["README.md"]


def test_input_collector_collects_nested_python_files_and_ignores_excluded_dirs(
    tmp_path: Path,
) -> None:
    included_files = [
        tmp_path / "src" / "sample_app" / "__init__.py",
        tmp_path / "src" / "sample_app" / "main.py",
        tmp_path / "src" / "sample_app" / "services" / "worker.py",
        tmp_path / "scripts" / "admin.py",
    ]
    for path in included_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('included')\n", encoding="utf-8")

    excluded_files = [
        tmp_path / ".venv" / "ignored.py",
        tmp_path / ".git" / "hooks" / "ignored.py",
        tmp_path / "__pycache__" / "ignored.py",
        tmp_path / "reports" / "generated.py",
        tmp_path / "build" / "generated.py",
    ]
    for path in excluded_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("eval('ignored')\n", encoding="utf-8")

    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    (tmp_path / "src" / "sample_app" / "settings.toml").write_text(
        "debug = true\n", encoding="utf-8"
    )

    collected = InputCollector().collect(tmp_path)

    assert [
        path.relative_to(tmp_path).as_posix() for path in collected.python_files
    ] == [
        "scripts/admin.py",
        "src/sample_app/__init__.py",
        "src/sample_app/main.py",
        "src/sample_app/services/worker.py",
    ]
    assert [
        skipped.path.relative_to(tmp_path).as_posix()
        for skipped in collected.skipped_paths
    ] == [
        "README.md",
        "src/sample_app/settings.toml",
    ]


def test_input_collector_keeps_invalid_utf8_python_file_for_loader(
    tmp_path: Path,
) -> None:
    invalid_file = tmp_path / "invalid_utf8.py"
    invalid_file.write_bytes(b"\xff\xfe\x00")

    collected = InputCollector().collect(tmp_path)

    assert collected.python_files == [invalid_file]
    assert collected.skipped_paths == []


def test_python_file_loader_marks_decode_failures_as_skipped(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid_utf8.py"
    invalid_file.write_bytes(b"\xff\xfe\x00")

    loaded = PythonFileLoader().load(invalid_file)

    assert loaded.path == invalid_file.resolve()
    assert loaded.source == ""
    assert loaded.lines == []
    assert loaded.skipped is True
    assert loaded.skip_reason is not None
    assert "UTF-8 decode failed" in loaded.skip_reason
