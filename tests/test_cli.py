from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_nurilab.cli import main
from project_nurilab.schemas import ExternalToolCall, RuffFinding


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


FIXTURES = Path(__file__).parent / "fixtures"


def _fake_jadx_mcp_client(record: ExternalToolCall, seen_urls: list[str | None]):
    """Build a JadxMcpClient stand-in that returns ``record`` for any call."""

    class FakeJadxMcpClient:
        def __init__(self, url: str | None = None) -> None:
            seen_urls.append(url)

        def call_tool(
            self, tool: str, class_name: str, target: str | None = None
        ) -> ExternalToolCall:
            return record

    return FakeJadxMcpClient


@pytest.mark.parametrize(
    ("record", "expected_line"),
    [
        (
            ExternalToolCall(
                server_url="http://127.0.0.1:9000/mcp",
                tool="get_class_source",
                status="success",
                called_at="2026-10-01T00:00:00+00:00",
                response_size_bytes=12345,
            ),
            "JADX MCP get_class_source: success (12,345 bytes)",
        ),
        (
            ExternalToolCall(
                server_url="http://127.0.0.1:9000/mcp",
                tool="get_class_source",
                status="unavailable",
                called_at="2026-10-01T00:00:00+00:00",
                reason="Cannot connect to JADX plugin\nsecond line",
            ),
            "JADX MCP get_class_source: unavailable - Cannot connect to JADX plugin",
        ),
    ],
)
def test_cli_jadx_mcp_prints_status_line_and_keeps_json(
    tmp_path: Path,
    monkeypatch,
    capsys,
    record: ExternalToolCall,
    expected_line: str,
) -> None:
    """--jadx-mcp-class prints one status line; exit code and JSON stay as-is."""

    seen_urls: list[str | None] = []
    monkeypatch.setattr(
        "project_nurilab.cli.JadxMcpClient",
        _fake_jadx_mcp_client(record, seen_urls),
    )
    output_dir = tmp_path / "reports"

    exit_code = main(
        [
            "analyze",
            str(FIXTURES / "clean_sample.py"),
            "--out",
            str(output_dir),
            "--no-ruff",
            "--jadx-mcp-class",
            "com.nurilab.mcpprobe.MainActivity",
            "--jadx-mcp-url",
            "http://127.0.0.1:9000/mcp",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(
        (output_dir / "clean_sample.analysis.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert seen_urls == ["http://127.0.0.1:9000/mcp"]
    assert captured.out.rstrip().splitlines()[-1] == expected_line
    assert "external_tool_calls" not in payload


def test_cli_without_jadx_mcp_class_never_builds_a_client(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Default runs do not touch MCP and print no MCP status line."""

    def fail_if_built(*args, **kwargs):
        raise AssertionError("JadxMcpClient must not be built without the option")

    monkeypatch.setattr("project_nurilab.cli.JadxMcpClient", fail_if_built)
    monkeypatch.setattr("project_nurilab.pipeline.JadxMcpClient", fail_if_built)

    exit_code = main(
        [
            "analyze",
            str(FIXTURES / "clean_sample.py"),
            "--out",
            str(tmp_path),
            "--no-ruff",
        ]
    )

    assert exit_code == 0
    assert "JADX MCP" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "option",
    [
        ["--jadx-mcp-url", "http://127.0.0.1:9000/mcp"],
        ["--jadx-mcp-target", "mcpprobe-debug.apk"],
    ],
)
def test_cli_jadx_mcp_options_require_class(
    tmp_path: Path, capsys, option: list[str]
) -> None:
    """URL or target without --jadx-mcp-class is a usage error, not ignored."""

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "analyze",
                str(FIXTURES / "clean_sample.py"),
                "--out",
                str(tmp_path),
                *option,
            ]
        )

    assert exc_info.value.code == 2
    assert "require --jadx-mcp-class" in capsys.readouterr().err
