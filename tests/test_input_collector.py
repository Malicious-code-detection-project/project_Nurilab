from __future__ import annotations

from pathlib import Path

from project_nurilab.input.collector import InputCollector


def test_input_collector_collects_python_files_and_excludes_dirs(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text("eval('x')\n", encoding="utf-8")

    collected = InputCollector().collect(tmp_path)

    assert collected.root_path == tmp_path.resolve()
    assert [path.name for path in collected.python_files] == ["app.py"]
    assert [path.path.name for path in collected.skipped_paths] == ["README.md"]
