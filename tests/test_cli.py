from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from mcp import types

from project_nurilab.cli import main
from project_nurilab.external.jadx_mcp_client import JadxMcpClient, McpSession
from project_nurilab.schemas import ExternalToolCall, RuffFinding


@pytest.fixture(autouse=True)
def _restore_root_log_handlers():
    """Drop any root log handler a test leaves behind so tests stay independent."""

    root = logging.getLogger()
    handlers_before = list(root.handlers)
    yield
    for handler in root.handlers[:]:
        if handler not in handlers_before:
            root.removeHandler(handler)


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
    """--jadx-mcp-class prints one status line and records the call in JSON."""

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
    assert payload["external_tool_calls"] == [record.to_dict()]


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


def test_cli_escapes_control_characters_in_external_reason(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Terminal control codes from an MCP server are printed as visible escapes."""

    record = ExternalToolCall(
        server_url="http://127.0.0.1:8651/mcp",
        tool="get_class_source",
        status="tool_error",
        called_at="2026-10-07T00:00:00+00:00",
        reason="\x1b[2J\x1b[31mFAKE: all clear",
    )
    monkeypatch.setattr(
        "project_nurilab.cli.JadxMcpClient", _fake_jadx_mcp_client(record, [])
    )

    main(
        [
            "analyze",
            str(FIXTURES / "clean_sample.py"),
            "--out",
            str(tmp_path),
            "--no-ruff",
            "--jadx-mcp-class",
            "A",
        ]
    )

    last_line = capsys.readouterr().out.rstrip().splitlines()[-1]
    assert "\x1b" not in last_line
    assert last_line.endswith("tool_error - \\x1b[2J\\x1b[31mFAKE: all clear")


def test_cli_keeps_jadx_mcp_url_for_empty_class_name(
    tmp_path: Path, monkeypatch
) -> None:
    """An empty --jadx-mcp-class still uses the given URL so the record is accurate."""

    record = ExternalToolCall(
        server_url="http://127.0.0.1:9000/mcp",
        tool="get_class_source",
        status="invalid_input",
        called_at="2026-10-07T00:00:00+00:00",
    )
    seen_urls: list[str | None] = []
    monkeypatch.setattr(
        "project_nurilab.cli.JadxMcpClient", _fake_jadx_mcp_client(record, seen_urls)
    )

    main(
        [
            "analyze",
            str(FIXTURES / "clean_sample.py"),
            "--out",
            str(tmp_path),
            "--no-ruff",
            "--jadx-mcp-class",
            "",
            "--jadx-mcp-url",
            "http://127.0.0.1:9000/mcp",
        ]
    )

    assert seen_urls == ["http://127.0.0.1:9000/mcp"]


@pytest.mark.parametrize(
    "logger_name", ["mcp.client.streamable_http", "client", "httpx2"]
)
def test_cli_escapes_control_characters_in_library_logs(
    tmp_path: Path, monkeypatch, capsys, logger_name: str
) -> None:
    """Warnings a library logs during the MCP call reach stderr only as escapes."""

    record = ExternalToolCall(
        server_url="http://127.0.0.1:8651/mcp",
        tool="get_class_source",
        status="unavailable",
        called_at="2026-10-11T00:00:00+00:00",
    )

    class LoggingJadxMcpClient:
        def __init__(self, url: str | None = None) -> None:
            pass

        def call_tool(
            self, tool: str, class_name: str, target: str | None = None
        ) -> ExternalToolCall:
            # The real SDK logs server-supplied values while the call runs.
            logging.getLogger(logger_name).warning(
                "Unknown SSE event: \x1b[2J\x1b[31mFAKE"
            )
            return record

    monkeypatch.setattr("project_nurilab.cli.JadxMcpClient", LoggingJadxMcpClient)
    handlers_before = list(logging.getLogger().handlers)

    main(
        [
            "analyze",
            str(FIXTURES / "clean_sample.py"),
            "--out",
            str(tmp_path),
            "--no-ruff",
            "--jadx-mcp-class",
            "A",
        ]
    )

    err = capsys.readouterr().err
    assert "Logging error" not in err
    assert "\x1b" not in err
    assert "Unknown SSE event: \\x1b[2J\\x1b[31mFAKE" in err
    assert logging.getLogger().handlers == handlers_before


class _SuccessSession:
    """Offline MCP session that answers get_class_source with a small source."""

    def __init__(self, server_name: str) -> None:
        self.server_name = server_name

    async def initialize(self) -> types.InitializeResult:
        return types.InitializeResult(
            protocol_version="2025-11-25",
            capabilities=types.ServerCapabilities(),
            server_info=types.Implementation(name=self.server_name, version="3.0.2"),
        )

    async def list_tools(
        self, *, params: types.PaginatedRequestParams | None = None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(
            tools=[types.Tool(name="get_class_source", input_schema={"type": "object"})]
        )

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> object:
        payload = {"response": "class A {}"}
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload))],
            structured_content=payload,
        )


@pytest.mark.parametrize(
    ("options", "server_name", "field", "expected"),
    [
        (
            ["--jadx-mcp-class", "Bad\udcff"],
            "jadx",
            "arguments",
            {"class_name": "Bad?"},
        ),
        (
            ["--jadx-mcp-class", "A", "--jadx-mcp-target", "app\udcb0\udca1.apk"],
            "jadx",
            "target",
            "app??.apk",
        ),
        (
            ["--jadx-mcp-class", "A", "--jadx-mcp-url", "http://127.0.0.1:9000/\udcff"],
            "jadx",
            "server_url",
            "http://127.0.0.1:9000/?",
        ),
        (["--jadx-mcp-class", "A"], "jadx\ud800", "server_name", "jadx?"),
    ],
    ids=["class", "target", "url", "server_info"],
)
def test_cli_writes_json_when_mcp_values_contain_lone_surrogates(
    tmp_path: Path,
    monkeypatch,
    capsys,
    options: list[str],
    server_name: str,
    field: str,
    expected: object,
) -> None:
    """Undecodable argv bytes or server text must not break the UTF-8 JSON write."""

    @asynccontextmanager
    async def factory(url: str) -> AsyncGenerator[McpSession, None]:
        yield _SuccessSession(server_name)

    monkeypatch.setattr(
        "project_nurilab.cli.JadxMcpClient",
        lambda url=None: JadxMcpClient(url=url, session_factory=factory),
    )
    output_dir = tmp_path / "reports"

    exit_code = main(
        [
            "analyze",
            str(FIXTURES / "clean_sample.py"),
            "--out",
            str(output_dir),
            "--no-ruff",
            *options,
        ]
    )

    payload = json.loads(
        (output_dir / "clean_sample.analysis.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert capsys.readouterr().out.rstrip().splitlines()[-1].startswith("JADX MCP")
    assert payload["external_tool_calls"][0][field] == expected
