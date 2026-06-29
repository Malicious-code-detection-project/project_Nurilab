from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_nurilab.cli import main
from project_nurilab.schemas import RuffFinding


def test_cli_analyze_project_directory_generates_reports_with_no_ruff(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_dir = tmp_path / "target_project"
    project_dir.mkdir()
    (project_dir / "safe.py").write_text(
        "def ok():\n    return 1\n",
        encoding="utf-8",
    )
    (project_dir / "risky.py").write_text(
        "import os\n\n\ndef run(command):\n    return os.system(command)\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"

    def fail_if_ruff_runs(*args, **kwargs) -> list[RuffFinding]:
        raise AssertionError("--no-ruff should disable Ruff collection")

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fail_if_ruff_runs,
    )

    exit_code = main(
        [
            "analyze",
            str(project_dir),
            "--out",
            str(output_dir),
            "--no-ruff",
        ]
    )

    captured = capsys.readouterr()
    html_report = output_dir / "target_project.analysis.html"
    json_report = output_dir / "target_project.analysis.json"

    assert exit_code == 0
    assert f"Analyzed: {project_dir.resolve()}" in captured.out
    assert "Risk Level: high" in captured.out
    assert f"HTML Report: {html_report.resolve()}" in captured.out
    assert f"JSON Report: {json_report.resolve()}" in captured.out
    assert html_report.exists()
    assert json_report.exists()

    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["analysis"]["summary"]["total_files"] == 2
    assert payload["analysis"]["ruff_findings"] == []
    assert payload["review"]["risk_level"] == "high"
    assert (
        payload["review"]["findings"][0]["title"] == "Review suspicious call: os.system"
    )


def test_cli_max_lines_is_deprecated_no_op_for_project_analysis(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "target_project"
    project_dir.mkdir()
    source_lines = [
        "import os",
        *("print('x')" for _ in range(205)),
        "def run(command):",
        "    return os.system(command)",
    ]
    (project_dir / "large.py").write_text("\n".join(source_lines), encoding="utf-8")
    output_dir = tmp_path / "reports"

    def fail_if_ruff_runs(*args, **kwargs) -> list[RuffFinding]:
        raise AssertionError("--no-ruff should disable Ruff collection")

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fail_if_ruff_runs,
    )

    exit_code = main(
        [
            "analyze",
            str(project_dir),
            "--out",
            str(output_dir),
            "--max-lines",
            "1",
            "--no-ruff",
        ]
    )

    json_report = output_dir / "target_project.analysis.json"
    payload = json.loads(json_report.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["analysis"]["summary"]["total_files"] == 1
    assert payload["analysis"]["summary"]["analyzed_files"] == 1
    assert payload["analysis"]["summary"]["skipped_files"] == 0
    assert payload["analysis"]["file_results"][0]["skipped"] is False
    assert payload["review"]["risk_level"] == "high"


def test_cli_max_lines_help_is_marked_deprecated(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["analyze", "--help"])

    captured = capsys.readouterr()

    assert exc_info.value.code == 0
    assert "--max-lines" in captured.out
    assert "Deprecated and ignored" in captured.out
    assert "Maximum allowed source lines" not in captured.out
