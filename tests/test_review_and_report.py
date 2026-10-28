from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from project_nurilab import __version__
from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.llm.review import LocalLLMReviewClient, MockLLMReviewClient
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.reports.generator import (
    EXTERNAL_STATUS_DISPLAY,
    ReportGenerator,
    _external_tool_call_css,
    _render_html_external_tool_calls,
)
from project_nurilab.reports.paths import (
    name_absolute_finding_files,
    relativize_report,
    replace_root,
)
from project_nurilab.schemas import (
    ALLOWED_EXTERNAL_TOOL_CALL_STATUSES,
    AnalysisReport,
    ExternalToolCall,
    ProjectAnalysis,
    ProjectFileSummary,
    ProjectReport,
    ProjectSummary,
    PythonAnalysis,
    ReviewerInfo,
    ReviewFinding,
    ReviewResult,
    RuffFinding,
    SecretFinding,
    SuspiciousCall,
)


FIXTURES = Path(__file__).parent / "fixtures"
REVIEW_QUALITY_FIXTURES = FIXTURES / "review_quality"
MIXED_RISK_PROJECT = FIXTURES / "mixed_risk_project"


def _copy_mixed_risk_project_fixture(tmp_path: Path) -> Path:
    target_project = tmp_path / "mixed_risk_project"
    target_project.mkdir()
    for source_file in MIXED_RISK_PROJECT.glob("*.py"):
        (target_project / source_file.name).write_text(
            source_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (target_project / "syntax_error.py").write_text(
        (MIXED_RISK_PROJECT / "syntax_error_source.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target_project


def _build_project_json_contract_report(root_path: str) -> ProjectReport:
    return ProjectReport(
        generated_at="2026-06-29T00:00:00+00:00",
        analyzer_version=__version__,
        analysis=ProjectAnalysis(
            root_path=root_path,
            file_results=[
                PythonAnalysis(
                    path=f"{root_path}/risky.py",
                    line_count=20,
                    suspicious_calls=[
                        SuspiciousCall(
                            name="eval",
                            line=7,
                            category="dynamic_execution",
                            severity="high",
                            reason="dynamic execution",
                        )
                    ],
                    secrets=[
                        SecretFinding(
                            kind="api_key",
                            line=3,
                            preview="demo-key",
                            severity="high",
                            reason="hard-coded secret",
                        )
                    ],
                ),
                PythonAnalysis(
                    path=f"{root_path}/broken.py",
                    line_count=1,
                    syntax_error="invalid syntax",
                ),
            ],
            ruff_findings=[
                RuffFinding(
                    file=f"{root_path}/risky.py",
                    line=1,
                    column=1,
                    rule_id="F401",
                    message="unused import",
                    severity="medium",
                )
            ],
            summary=ProjectSummary(
                total_files=2,
                analyzed_files=2,
                skipped_files=0,
                severity_counts={"high": 2, "medium": 2},
                risk_level="high",
                file_summaries=[
                    ProjectFileSummary(
                        path="risky.py",
                        risk_level="high",
                        finding_count=3,
                        suspicious_call_count=1,
                        secret_count=1,
                        ruff_finding_count=1,
                    ),
                    ProjectFileSummary(
                        path="broken.py",
                        risk_level="medium",
                        finding_count=1,
                        syntax_error=True,
                    ),
                ],
            ),
        ),
        review=ReviewResult(
            summary="Project contains high-risk findings.",
            risk_level="high",
            findings=[
                ReviewFinding(
                    title="Dynamic execution",
                    severity="high",
                    file=f"{root_path}/risky.py",
                    line=7,
                    reason="uses eval",
                    recommendation="avoid eval",
                    source="pattern",
                    rule_id="DYN001",
                )
            ],
        ),
    )


def test_mock_review_client_turns_static_signals_into_findings() -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)

    review = MockLLMReviewClient().review(analysis)

    assert review.risk_level == "high"
    assert len(review.findings) == 3
    assert any("os.system" in finding.title for finding in review.findings)
    assert any("hard-coded secret" in finding.title for finding in review.findings)


@pytest.mark.parametrize(
    ("fixture_name", "expected_title", "expected_risk"),
    [
        ("dynamic_execution_sample.py", "eval", "high"),
        ("hardcoded_secret_sample.py", "hard-coded secret", "high"),
        ("unsafe_deserialization_sample.py", "pickle.loads", "high"),
        ("network_access_sample.py", "requests.get", "low"),
    ],
)
def test_mock_review_client_covers_review_quality_fixtures(
    fixture_name: str,
    expected_title: str,
    expected_risk: str,
) -> None:
    loaded = PythonFileLoader().load(REVIEW_QUALITY_FIXTURES / fixture_name)
    analysis = PythonStaticAnalyzer().analyze(loaded)

    review = MockLLMReviewClient().review(analysis)

    assert review.risk_level == expected_risk
    assert any(expected_title in finding.title for finding in review.findings)


def test_mock_review_client_keeps_clean_baseline_low_risk() -> None:
    loaded = PythonFileLoader().load(
        REVIEW_QUALITY_FIXTURES / "clean_baseline_sample.py"
    )
    analysis = PythonStaticAnalyzer().analyze(loaded)

    review = MockLLMReviewClient().review(analysis)

    assert review.risk_level == "low"
    assert review.findings == []
    assert "clean baseline" in review.summary


def test_mock_project_review_sorts_findings_deterministically() -> None:
    review = MockLLMReviewClient().review(
        ProjectAnalysis(
            root_path="/tmp/example_project",
            file_results=[
                PythonAnalysis(
                    path="/tmp/example_project/z_low.py",
                    line_count=10,
                    suspicious_calls=[
                        SuspiciousCall(
                            name="requests.get",
                            line=9,
                            category="network_access",
                            severity="low",
                            reason="network call",
                        )
                    ],
                ),
                PythonAnalysis(
                    path="/tmp/example_project/a_high.py",
                    line_count=10,
                    suspicious_calls=[
                        SuspiciousCall(
                            name="eval",
                            line=8,
                            category="dynamic_execution",
                            severity="high",
                            reason="dynamic execution",
                        )
                    ],
                    secrets=[
                        SecretFinding(
                            kind="api_key",
                            line=2,
                            preview="sk-...",
                            severity="high",
                            reason="hard-coded secret",
                        )
                    ],
                ),
            ],
            ruff_findings=[
                RuffFinding(
                    file="/tmp/example_project/a_high.py",
                    line=1,
                    column=1,
                    rule_id="F401",
                    message="unused import",
                    severity="low",
                )
            ],
            summary=ProjectSummary(
                total_files=2,
                analyzed_files=2,
                skipped_files=0,
                risk_level="high",
            ),
        )
    )

    finding_order = [
        (finding.severity, finding.file, finding.line, finding.source, finding.rule_id)
        for finding in review.findings
    ]

    assert finding_order == [
        ("high", "/tmp/example_project/a_high.py", 2, "secret", None),
        ("high", "/tmp/example_project/a_high.py", 8, "pattern", None),
        ("low", "/tmp/example_project/a_high.py", 1, "ruff", "F401"),
        ("low", "/tmp/example_project/z_low.py", 9, "pattern", None),
    ]


def test_report_generator_writes_default_html_and_json(tmp_path: Path) -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)
    review = MockLLMReviewClient().review(analysis)
    report = AnalysisReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=analysis,
        review=review,
    )

    output_paths = ReportGenerator().write(report, tmp_path)

    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()
    assert "Python Code Review Report" in output_paths["html"].read_text(
        encoding="utf-8"
    )
    assert '"risk_level": "high"' in output_paths["json"].read_text(encoding="utf-8")


def test_report_generator_writes_requested_markdown_html_json(
    tmp_path: Path,
) -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)
    review = MockLLMReviewClient().review(analysis)
    report = AnalysisReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=analysis,
        review=review,
    )

    output_paths = ReportGenerator().write(
        report,
        tmp_path,
        formats=["md", "html", "json"],
    )

    assert list(output_paths) == ["md", "html", "json"]
    assert output_paths["md"].name.endswith(".analysis.md")
    assert output_paths["html"].name.endswith(".analysis.html")
    assert output_paths["json"].name.endswith(".analysis.json")


def test_project_report_to_dict_preserves_json_contract() -> None:
    report = _build_project_json_contract_report("/tmp/json_project")

    payload = report.to_dict()

    assert set(payload) == {"generated_at", "analyzer_version", "analysis", "review"}
    assert payload["generated_at"] == "2026-06-29T00:00:00+00:00"
    assert payload["analyzer_version"] == __version__

    analysis = payload["analysis"]
    assert set(analysis) == {"root_path", "file_results", "ruff_findings", "summary"}
    assert analysis["root_path"] == "/tmp/json_project"
    assert analysis["summary"] == {
        "total_files": 2,
        "analyzed_files": 2,
        "skipped_files": 0,
        "severity_counts": {"high": 2, "medium": 2},
        "risk_level": "high",
        "file_summaries": [
            {
                "path": "risky.py",
                "risk_level": "high",
                "finding_count": 3,
                "suspicious_call_count": 1,
                "secret_count": 1,
                "syntax_error": False,
                "ruff_finding_count": 1,
                "skipped": False,
            },
            {
                "path": "broken.py",
                "risk_level": "medium",
                "finding_count": 1,
                "suspicious_call_count": 0,
                "secret_count": 0,
                "syntax_error": True,
                "ruff_finding_count": 0,
                "skipped": False,
            },
        ],
    }
    assert len(analysis["file_results"]) == 2
    assert analysis["file_results"][0]["path"] == "/tmp/json_project/risky.py"
    assert analysis["file_results"][0]["suspicious_calls"][0] == {
        "name": "eval",
        "line": 7,
        "category": "dynamic_execution",
        "severity": "high",
        "reason": "dynamic execution",
    }
    assert analysis["file_results"][0]["secrets"][0] == {
        "kind": "api_key",
        "line": 3,
        "preview": "demo-key",
        "severity": "high",
        "reason": "hard-coded secret",
    }
    assert analysis["file_results"][1]["syntax_error"] == "invalid syntax"
    assert analysis["ruff_findings"] == [
        {
            "file": "/tmp/json_project/risky.py",
            "line": 1,
            "column": 1,
            "rule_id": "F401",
            "message": "unused import",
            "severity": "medium",
            "source": "ruff",
        }
    ]

    review = payload["review"]
    assert set(review) == {"summary", "risk_level", "findings", "reviewer"}
    # A ReviewResult built outside the Mock and Local LLM clients has no source.
    assert review["reviewer"] is None
    assert review["risk_level"] == "high"
    assert review["findings"] == [
        {
            "title": "Dynamic execution",
            "severity": "high",
            "line": 7,
            "reason": "uses eval",
            "recommendation": "avoid eval",
            "file": "/tmp/json_project/risky.py",
            "source": "pattern",
            "column": None,
            "rule_id": "DYN001",
        }
    ]


def test_report_generator_writes_project_json_contract(tmp_path: Path) -> None:
    report = _build_project_json_contract_report(str(tmp_path / "json_project"))

    output_paths = ReportGenerator().write(report, tmp_path, formats=["json"])

    assert set(output_paths) == {"json"}
    assert output_paths["json"].name == "json_project.analysis.json"
    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload == report.to_dict()
    assert "html" not in output_paths


def _jadx_mcp_success_call() -> ExternalToolCall:
    return ExternalToolCall(
        server_url="http://127.0.0.1:8651/mcp",
        tool="get_class_source",
        status="success",
        called_at="2026-10-12T00:00:00+00:00",
        arguments={"class_name": "com.nurilab.mcpprobe.MainActivity"},
        target="mcpprobe-debug.apk",
        server_name="JADX-AI-MCP Plugin Reverse Engineering Server",
        server_version="3.0.2",
        expected_release="jadx-ai-mcp V6.4.1",
        client_sdk="mcp 2.2.0",
        duration_ms=200,
        content="// 주석 </script>\npackage com.nurilab.mcpprobe;\n",
        response_size_bytes=50,
    )


def _jadx_mcp_unavailable_call() -> ExternalToolCall:
    return ExternalToolCall(
        server_url="http://127.0.0.1:8659/mcp",
        tool="get_class_source",
        status="unavailable",
        called_at="2026-10-12T00:00:00+00:00",
        arguments={"class_name": "com.nurilab.mcpprobe.MainActivity"},
        reason="connect failed: ConnectError: All connection attempts failed",
        client_sdk="mcp 2.2.0",
        duration_ms=5,
    )


def _build_single_file_report() -> AnalysisReport:
    return AnalysisReport(
        generated_at="2026-06-29T00:00:00+00:00",
        analyzer_version=__version__,
        analysis=PythonAnalysis(path="/tmp/sample.py", line_count=1),
        review=ReviewResult(summary="No findings.", risk_level="low"),
    )


@pytest.mark.parametrize(
    "build_report",
    [
        _build_single_file_report,
        lambda: _build_project_json_contract_report("/tmp/json_project"),
    ],
    ids=["file", "project"],
)
def test_report_to_dict_adds_external_tool_calls_only_when_recorded(
    build_report,
) -> None:
    """Without an MCP call the JSON contract is unchanged; with one it is appended."""

    report = build_report()
    baseline = report.to_dict()
    assert list(baseline) == ["generated_at", "analyzer_version", "analysis", "review"]

    calls = [_jadx_mcp_success_call(), _jadx_mcp_unavailable_call()]
    report.external_tool_calls = calls
    payload = report.to_dict()

    assert list(payload) == [*baseline, "external_tool_calls"]
    for key, value in baseline.items():
        assert payload[key] == value
    assert payload["external_tool_calls"] == [call.to_dict() for call in calls]
    assert set(payload["external_tool_calls"][0]) == {
        "server_url",
        "tool",
        "status",
        "called_at",
        "arguments",
        "target",
        "target_verified",
        "target_statically_analyzed",
        "reason",
        "server_name",
        "server_version",
        "expected_release",
        "client_sdk",
        "duration_ms",
        "content",
        "response_size_bytes",
        "truncated",
    }
    assert payload["external_tool_calls"][1]["content"] is None
    assert payload["external_tool_calls"][1]["target"] is None
    for call in payload["external_tool_calls"]:
        assert call["target_verified"] is False
        assert call["target_statically_analyzed"] is False


class _ExternalContentParser(HTMLParser):
    """Collect the text a browser shows inside each external-content <pre>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "pre" and ("class", "external-content") in attrs:
            self._inside = True
            self.blocks.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self._inside = False

    def handle_data(self, data: str) -> None:
        if self._inside:
            self.blocks[-1] += data


def _shown_external_content(html: str) -> list[str]:
    parser = _ExternalContentParser()
    parser.feed(html)
    # Browsers drop the single newline right after <pre>; mirror that here.
    return [block.removeprefix("\n") for block in parser.blocks]


_REPORT_BUILDERS = pytest.mark.parametrize(
    ("build_report", "last_section"),
    [
        (_build_single_file_report, "<h2>Findings</h2>"),
        (
            lambda: _build_project_json_contract_report("/tmp/json_project"),
            "<h2>Ruff Findings</h2>",
        ),
    ],
    ids=["file", "project"],
)


def test_external_tool_call_html_parts_are_empty_without_records() -> None:
    """Both insertion points add nothing, so HTML without MCP stays byte-identical."""

    assert _render_html_external_tool_calls([]) == ""
    assert _external_tool_call_css([]) == ""


@pytest.mark.parametrize(
    "build_report",
    [
        _build_single_file_report,
        lambda: _build_project_json_contract_report("/tmp/json_project"),
    ],
    ids=["file", "project"],
)
def test_html_report_omits_external_tool_calls_without_records(build_report) -> None:
    """Runs without an MCP call render no external section and no extra CSS."""

    html = ReportGenerator().to_html(build_report())

    assert "External Tool Calls" not in html
    assert "external-call" not in html
    assert "external-content" not in html


@_REPORT_BUILDERS
def test_html_report_renders_external_tool_call_section(
    build_report, last_section: str
) -> None:
    """The MCP record is shown after the existing sections with its provenance."""

    report = build_report()
    call = _jadx_mcp_success_call()
    report.external_tool_calls = [call]

    html = ReportGenerator().to_html(report)

    section_at = html.index("<h2>External Tool Calls (jadx-ai-mcp)</h2>")
    assert html.index(last_section) < section_at
    assert html.index("</main>") > section_at
    assert "They are not used for findings, risk level, or review." in html
    assert "Returned source is untrusted data" in html
    assert "does not verify that the target matches the APK" in html
    assert (
        "The jadx-ai-mcp target (an APK) is not a format supported by NuriLab "
        "static analysis; the analysis results above do not cover it."
    ) in html
    for label, value in [
        ("Argument: class_name", "com.nurilab.mcpprobe.MainActivity"),
        ("Target", "mcpprobe-debug.apk"),
        ("Target Verified", "False"),
        ("Target Statically Analyzed", "False"),
        ("Server URL", "http://127.0.0.1:8651/mcp"),
        ("Server Name", "JADX-AI-MCP Plugin Reverse Engineering Server"),
        ("Server Version", "3.0.2"),
        ("Expected Release (configured)", "jadx-ai-mcp V6.4.1"),
        ("Client SDK", "mcp 2.2.0"),
        ("Called At", "2026-10-12T00:00:00+00:00"),
        ("Duration", "200 ms"),
        ("Response Size", "50 bytes"),
        ("Truncated", "False"),
    ]:
        assert f'<span class="label">{label}</span><code>{value}</code>' in html, label
    assert (
        '<p><strong>Status:</strong> <span class="badge external-status status-ok">'
        "success</span> The tool returned source.</p>"
    ) in html
    assert "<summary>Returned source (50 bytes shown)</summary>" in html
    assert _shown_external_content(html) == [call.content]
    assert "</script>" not in html


def test_html_report_escapes_untrusted_external_values() -> None:
    """Server and user values never become markup, and the source text survives."""

    hostile = '<img src=x onerror="alert(1)">'
    content = "\n</pre></details><script>alert(1)</script>\nclass A {}"
    report = _build_single_file_report()
    report.external_tool_calls = [
        ExternalToolCall(
            server_url=f"http://127.0.0.1:8651/{hostile}",
            tool="get_class_source",
            status="success",
            called_at="2026-10-12T00:00:00+00:00",
            arguments={"class_name": hostile},
            target=hostile,
            reason=hostile,
            server_name=hostile,
            server_version=hostile,
            content=content,
            response_size_bytes=len(content.encode("utf-8")),
        )
    ]

    html = ReportGenerator().to_html(report)

    assert "<img" not in html
    assert "<script" not in html
    # Only the real closing tags remain; the injected ones are escaped.
    assert html.count("</pre></details>") == 1
    assert html.count("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;") == 6
    assert _shown_external_content(html) == [content]


def test_html_report_shows_failed_external_call_without_source() -> None:
    """A failed call shows its reason and unknown provenance, with no source block."""

    report = _build_single_file_report()
    report.external_tool_calls = [_jadx_mcp_unavailable_call()]

    html = ReportGenerator().to_html(report)

    assert (
        "<p><strong>Status:</strong> "
        '<span class="badge external-status status-failure">unavailable</span> '
        "The tool could not be used (server, plugin, or tool not available; "
        "see Reason).</p>"
    ) in html
    assert (
        '<p class="external-reason"><strong>Reason:</strong> connect failed: '
        "ConnectError: All connection attempts failed</p>"
    ) in html
    assert '<span class="label">Target</span><code>(not given)</code>' in html
    assert '<span class="label">Server Name</span><code>(unknown)</code>' in html
    assert '<span class="label">Response Size</span><code>(none)</code>' in html
    assert "<details>" not in html


def test_html_report_labels_truncated_external_source() -> None:
    """A cut source says how much is shown out of the original response size."""

    report = _build_single_file_report()
    report.external_tool_calls = [
        ExternalToolCall(
            server_url="http://127.0.0.1:8651/mcp",
            tool="get_class_source",
            status="success",
            called_at="2026-10-12T00:00:00+00:00",
            content="가" * 10,
            response_size_bytes=300_000,
            truncated=True,
        )
    ]

    html = ReportGenerator().to_html(report)

    assert (
        "<summary>Returned source (30 bytes shown of 300,000 bytes, truncated)"
        "</summary>"
    ) in html
    assert '<span class="label">Truncated</span><code>True</code>' in html


def test_report_generator_writes_external_tool_call_json(tmp_path: Path) -> None:
    """Untrusted MCP content is stored verbatim as JSON data, not re-encoded."""

    report = _build_single_file_report()
    report.external_tool_calls = [_jadx_mcp_success_call()]

    output_paths = ReportGenerator().write(report, tmp_path, formats=["json"])

    json_text = output_paths["json"].read_text(encoding="utf-8")
    payload = json.loads(json_text)
    assert payload == report.to_dict()
    assert payload["external_tool_calls"][0]["content"] == (
        _jadx_mcp_success_call().content
    )
    assert "// 주석" in json_text


def test_report_generator_renders_local_llm_failure_finding_details(
    tmp_path: Path,
) -> None:
    report = AnalysisReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=PythonAnalysis(
            path=str(tmp_path / "sample.py"),
            line_count=4,
            suspicious_calls=[
                SuspiciousCall(
                    name="os.system",
                    line=4,
                    category="command_execution",
                    severity="high",
                    reason="shell command execution",
                )
            ],
        ),
        review=ReviewResult(
            summary="Local LLM review failed. Static analysis results are still available.",
            risk_level="unknown",
            findings=[
                ReviewFinding(
                    title="Local LLM connection failed",
                    severity="medium",
                    line=None,
                    source="local_llm",
                    reason=(
                        "Unable to reach the Local LLM endpoint. Static analysis "
                        "results are still included in this report."
                    ),
                    recommendation=(
                        "Start or restart vLLM and confirm NURILAB_LLM_BASE_URL."
                    ),
                )
            ],
        ),
    )

    output_paths = ReportGenerator().write(report, tmp_path, formats=["html", "json"])

    html = output_paths["html"].read_text(encoding="utf-8")
    assert "Local LLM connection failed" in html
    assert "<strong>Source:</strong> local_llm" in html
    assert "Static analysis results are still included" in html
    assert "NURILAB_LLM_BASE_URL" in html

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["suspicious_calls"][0]["name"] == "os.system"
    assert payload["review"]["findings"][0]["source"] == "local_llm"
    assert (
        "Static analysis results are still included"
        in payload["review"]["findings"][0]["reason"]
    )
    assert "NURILAB_LLM_BASE_URL" in payload["review"]["findings"][0]["recommendation"]


def test_report_generator_renders_project_file_summary() -> None:
    report = ProjectReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=ProjectAnalysis(
            root_path="/tmp/example_project",
            summary=ProjectSummary(
                total_files=2,
                analyzed_files=2,
                skipped_files=0,
                severity_counts={"high": 1, "low": 1},
                risk_level="high",
                file_summaries=[
                    ProjectFileSummary(
                        path="danger.py",
                        risk_level="high",
                        finding_count=3,
                        suspicious_call_count=1,
                        secret_count=1,
                        ruff_finding_count=1,
                    ),
                    ProjectFileSummary(
                        path="clean.py",
                        risk_level="low",
                        finding_count=0,
                    ),
                ],
            ),
        ),
        review=ReviewResult(
            summary="Project contains one high-risk file.",
            risk_level="high",
        ),
    )

    generator = ReportGenerator()
    markdown = generator.to_markdown(report)
    html = generator.to_html(report)

    assert "## File Summary" in markdown
    assert "danger.py" in markdown
    assert "- Findings: `3`" in markdown
    assert "- Suspicious Calls: `1`" in markdown
    assert "<h2>File Summary</h2>" in html
    assert "danger.py" in html
    assert "<strong>Ruff Findings:</strong> 1" in html


def test_report_generator_renders_readable_project_html() -> None:
    long_path = "src/package/with/a/very/long/path/module_with_security_issue.py"
    report = ProjectReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=ProjectAnalysis(
            root_path="/tmp/example_project",
            file_results=[
                PythonAnalysis(path=long_path, line_count=120),
            ],
            ruff_findings=[
                RuffFinding(
                    file=long_path,
                    line=12,
                    column=4,
                    rule_id="F401",
                    message="unused import",
                    severity="medium",
                )
            ],
            summary=ProjectSummary(
                total_files=3,
                analyzed_files=2,
                skipped_files=1,
                severity_counts={"low": 1, "high": 2, "medium": 1},
                risk_level="high",
                file_summaries=[
                    ProjectFileSummary(
                        path=long_path,
                        risk_level="high",
                        finding_count=3,
                    ),
                ],
            ),
        ),
        review=ReviewResult(
            summary="Project contains high-risk findings.",
            risk_level="high",
            findings=[
                ReviewFinding(
                    title="Low priority observation",
                    severity="low",
                    line=1,
                    reason="Low risk.",
                    recommendation="Review later.",
                    file="clean.py",
                ),
                ReviewFinding(
                    title="High priority issue",
                    severity="high",
                    line=12,
                    reason="High risk.",
                    recommendation="Review first.",
                    file=long_path,
                    source="pattern",
                    rule_id="DYN001",
                ),
            ],
        ),
    )

    html = ReportGenerator().to_html(report)

    assert 'class="summary project-overview"' in html
    assert "Total Python Files" in html
    assert "<strong>3</strong>" in html
    assert "Analyzed Files" in html
    assert "Skipped Files" in html
    assert "high: 2" in html
    assert "{&#x27;high&#x27;" not in html
    assert html.index("High priority issue") < html.index("Low priority observation")
    assert "finding-group severity-high" in html
    assert "Source" in html
    assert "pattern" in html
    assert "Rule" in html
    assert "DYN001" in html
    assert 'class="path-text"' in html
    assert long_path in html
    assert "F401" in html
    assert "12:4" in html


def test_report_generator_renders_mixed_risk_project_fixture_html(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from project_nurilab.pipeline import Phase1Pipeline

    target_project = _copy_mixed_risk_project_fixture(tmp_path)
    clean_file = target_project / "mixed_clean.py"

    def fake_collect(self: object, target: str | Path) -> list[RuffFinding]:
        assert Path(target) == target_project.resolve()
        return [
            RuffFinding(
                file=str(clean_file.resolve()),
                line=1,
                column=1,
                rule_id="F401",
                message="unused import",
                severity="low",
            )
        ]

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fake_collect,
    )

    report, output_paths = Phase1Pipeline().run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    html = output_paths["html"].read_text(encoding="utf-8")

    assert isinstance(report, ProjectReport)
    assert "Python Project Review Report" in html
    assert "Project Summary" in html
    assert "File Summary" in html
    assert "Findings" in html
    assert "Ruff Findings" in html
    assert "hardcoded_secret.py" in html
    assert "suspicious_call.py" in html
    assert "syntax_error.py" in html
    assert "mixed_clean.py" in html
    assert "Review suspicious call: os.system" in html
    assert "Potential hard-coded secret: api_key" in html
    assert "Python syntax error" in html
    assert "Ruff issue: F401" in html
    assert "high: 2" in html
    assert "medium: 1" in html
    assert "low: 1" in html


def test_single_file_html_report_keeps_existing_structure() -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)
    review = MockLLMReviewClient().review(analysis)
    report = AnalysisReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=analysis,
        review=review,
    )

    html = ReportGenerator().to_html(report)

    assert "Python Code Review Report" in html
    assert "Python Project Review Report" not in html
    assert "Project Summary" not in html
    assert "Static Analysis" in html


def test_pipeline_handles_local_llm_failure(monkeypatch, tmp_path: Path) -> None:
    from project_nurilab.llm.review import LocalLLMReviewClient
    from project_nurilab.pipeline import Phase1Pipeline

    # Mock requests.post to return invalid JSON
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "invalid-json"}}]}

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: ResponseStub())

    pipeline = Phase1Pipeline(
        review_client=LocalLLMReviewClient(base_url="http://localhost:8000/v1"),
        use_ruff=False,
    )
    report, output_paths = pipeline.run(
        input_path=FIXTURES / "clean_sample.py",
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    # The pipeline should complete successfully and write both reports
    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()

    # The report should contain the local_llm JSON parsing failure
    assert report.review.risk_level == "unknown"
    assert len(report.review.findings) == 1
    assert report.review.findings[0].source == "local_llm"
    assert report.review.findings[0].title == "Local LLM JSON parsing failed"


def test_pipeline_preserves_analysis_for_non_object_local_llm_json(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from project_nurilab.llm.review import LocalLLMReviewClient
    from project_nurilab.pipeline import Phase1Pipeline

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '[{"summary":"ok","risk_level":"low","findings":[]}]'
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: ResponseStub())

    pipeline = Phase1Pipeline(
        review_client=LocalLLMReviewClient(base_url="http://localhost:8000/v1"),
        use_ruff=False,
    )
    report, output_paths = pipeline.run(
        input_path=FIXTURES / "clean_sample.py",
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, AnalysisReport)
    assert report.analysis.path == str((FIXTURES / "clean_sample.py").resolve())
    assert report.analysis.line_count > 0
    assert report.review.risk_level == "unknown"
    assert report.review.findings[0].title == "Local LLM JSON parsing failed"
    assert "top level must be an object, got array" in report.review.findings[0].reason
    assert set(output_paths) == {"html", "json"}
    persisted_report = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert persisted_report["analysis"]["path"] == report.analysis.path
    assert persisted_report["analysis"]["line_count"] == report.analysis.line_count
    assert persisted_report["review"]["risk_level"] == "unknown"
    assert (
        persisted_report["review"]["findings"][0]["title"]
        == "Local LLM JSON parsing failed"
    )


def _external_call(status: str, **fields) -> ExternalToolCall:
    return ExternalToolCall(
        server_url="http://127.0.0.1:8651/mcp",
        tool="get_class_source",
        status=status,
        called_at="2026-10-14T00:00:00+00:00",
        **fields,
    )


def _render_external_calls(*calls: ExternalToolCall) -> str:
    report = _build_single_file_report()
    report.external_tool_calls = list(calls)
    return ReportGenerator().to_html(report)


def test_external_status_display_covers_every_contract_status() -> None:
    """A new status must get a display group and meaning before it can render."""

    assert set(EXTERNAL_STATUS_DISPLAY) == ALLOWED_EXTERNAL_TOOL_CALL_STATUSES


@pytest.mark.parametrize(
    ("status", "group"),
    [
        ("success", "ok"),
        ("empty", "warning"),
        ("not_found", "warning"),
        ("unavailable", "failure"),
        ("timeout", "failure"),
        ("tool_error", "failure"),
        ("malformed", "failure"),
        ("invalid_input", "not-called"),
        ("not_allowed", "not-called"),
    ],
)
def test_html_report_marks_each_external_status_by_group(
    status: str, group: str
) -> None:
    """Each status shows its group and meaning; only success looks successful."""

    html = _render_external_calls(_external_call(status))

    meaning = EXTERNAL_STATUS_DISPLAY[status][1]
    assert f'<article class="finding external-call status-{group}">' in html
    assert (
        f'<span class="badge external-status status-{group}">{status}</span> '
        f"{meaning}</p>"
    ) in html
    if status != "success":
        assert 'class="badge external-status status-ok"' not in html


def test_html_report_adds_truncated_badge_only_to_truncated_source() -> None:
    """truncated is a separate mark next to success, not a status of its own."""

    whole = _render_external_calls(_external_call("success", content="class A {}"))
    cut = _render_external_calls(
        _external_call(
            "success", content="class A", response_size_bytes=300_000, truncated=True
        )
    )

    badge = '<span class="badge external-status status-warning">truncated</span>'
    assert badge not in whole
    assert (
        '<span class="badge external-status status-ok">success</span> ' + badge
    ) in cut


_MARKDOWN_REPORT_BUILDERS = pytest.mark.parametrize(
    ("build_report", "last_section"),
    [
        (_build_single_file_report, "## Findings"),
        (
            lambda: _build_project_json_contract_report("/tmp/json_project"),
            "## Ruff Findings",
        ),
    ],
    ids=["file", "project"],
)


@_MARKDOWN_REPORT_BUILDERS
def test_markdown_report_adds_external_tool_calls_only_when_recorded(
    build_report, last_section: str
) -> None:
    """Markdown-only runs keep MCP status and reason; others stay unchanged."""

    report = build_report()
    baseline = ReportGenerator().to_markdown(report)
    assert "External Tool Calls" not in baseline

    report.external_tool_calls = [_jadx_mcp_unavailable_call()]
    markdown = ReportGenerator().to_markdown(report)

    assert markdown.startswith(baseline)
    section_at = markdown.index("## External Tool Calls (jadx-ai-mcp)")
    assert markdown.index(last_section) < section_at
    assert "They are not used for findings, risk level, or review." in markdown
    assert "does not verify that the target matches the APK" in markdown
    assert "the analysis results above do not cover it." in markdown
    meaning = EXTERNAL_STATUS_DISPLAY["unavailable"][1]
    assert f"- Status: `unavailable` - {meaning}\n" in markdown
    assert "- Server URL: `http://127.0.0.1:8659/mcp`\n" in markdown
    assert "- Server Name: `(unknown)`\n" in markdown
    assert "- Target Verified: `False`\n" in markdown
    assert (
        "Reason:\n\n```text\n"
        "connect failed: ConnectError: All connection attempts failed\n```\n"
    ) in markdown


def test_markdown_report_omits_external_source() -> None:
    """Untrusted source stays in HTML and JSON; Markdown shows its size only."""

    report = _build_single_file_report()
    report.external_tool_calls = [_jadx_mcp_success_call()]

    markdown = ReportGenerator().to_markdown(report)

    assert "package com.nurilab.mcpprobe" not in markdown
    assert "- Status: `success` - The tool returned source.\n" in markdown
    assert "- Response Size: `50 bytes`\n" in markdown
    assert "use the HTML or JSON report to see it" in markdown
    assert "Reason:" not in markdown


def test_markdown_report_keeps_untrusted_external_values_inert() -> None:
    """Server values cannot close their code span or fence, or hide characters."""

    hostile = "``a`b\n## Injected\u202e[x](http://evil)"
    report = _build_single_file_report()
    report.external_tool_calls = [
        _external_call(
            "tool_error",
            server_name=hostile,
            reason=f"first line\n```\n# Injected heading\n{hostile}",
            truncated=True,
        )
    ]

    markdown = ReportGenerator().to_markdown(report)

    assert (
        "- Server Name: ``` ``a`b\\n## Injected\\u202e[x](http://evil) ```\n"
    ) in markdown
    assert "- Status: `tool_error` (truncated) - " in markdown
    assert (
        "Reason:\n\n````text\nfirst line\n```\n# Injected heading\n"
        "``a`b\n## Injected\\u202e[x](http://evil)\n````\n"
    ) in markdown
    assert "\u202e" not in markdown


def test_reports_show_empty_external_argument_as_placeholder() -> None:
    """An empty class name cannot leave a bare backtick pair in Markdown."""

    report = _build_single_file_report()
    report.external_tool_calls = [
        _external_call("invalid_input", arguments={"class_name": ""})
    ]

    markdown = ReportGenerator().to_markdown(report)
    html = ReportGenerator().to_html(report)

    assert "- Argument: class_name: `(empty)`\n" in markdown
    assert (
        '<span class="label">Argument: class_name</span><code>(empty)</code>'
    ) in html


def test_report_generator_writes_markdown_only_with_external_tool_call(
    tmp_path: Path,
) -> None:
    """An md-only run still leaves the MCP failure in a report file."""

    report = _build_single_file_report()
    report.external_tool_calls = [_jadx_mcp_unavailable_call()]

    output_paths = ReportGenerator().write(report, tmp_path, formats=["md"])

    assert set(output_paths) == {"md"}
    markdown = output_paths["md"].read_text(encoding="utf-8")
    assert "## External Tool Calls (jadx-ai-mcp)" in markdown
    assert "connect failed: ConnectError" in markdown


def test_html_report_shows_bidi_controls_in_external_values() -> None:
    """Bidi controls cannot reorder shown text; other characters stay as-is."""

    trojan = "a\u202eb\u2066c\tq"
    html = _render_external_calls(
        _external_call(
            "success",
            server_name=trojan,
            reason=trojan,
            content=f"class A {{ // {trojan} }}",
        )
    )

    assert "\u202e" not in html
    assert "\u2066" not in html
    shown = "a\\u202eb\\u2066c\tq"
    assert f'<span class="label">Server Name</span><code>{shown}</code>' in html
    assert f"<strong>Reason:</strong> {shown}</p>" in html
    assert _shown_external_content(html) == [f"class A {{ // {shown} }}"]


def test_html_report_keeps_line_breaks_in_external_reason() -> None:
    """A multi-line reason wraps as written instead of joining into one line."""

    html = _render_external_calls(
        _external_call("tool_error", reason="first line\nsecond line")
    )

    assert (
        '<p class="external-reason"><strong>Reason:</strong> '
        "first line\nsecond line</p>"
    ) in html
    assert ".external-reason { white-space: pre-wrap;" in html


@pytest.mark.parametrize(
    ("status", "causes"),
    [
        ("not_found", ["HTTP 404", "not in the APK", "plugin path mismatch"]),
        ("timeout", ["connecting", "calling the tool", "JADX plugin"]),
    ],
)
def test_external_status_meaning_names_every_cause(
    status: str, causes: list[str]
) -> None:
    """Statuses with several causes do not claim a single one."""

    meaning = EXTERNAL_STATUS_DISPLAY[status][1]

    for cause in causes:
        assert cause in meaning
    assert "see Reason" in meaning


def test_replace_root_respects_boundaries_and_drops_separator(tmp_path: Path) -> None:
    root = (tmp_path / "upload").resolve()
    windows_file = str(root / "a.py").replace("/", "\\")

    assert replace_root(f"{root}/myproj/a.py", root, "") == "myproj/a.py"
    assert replace_root(f"Cause: {root}/a.py failed", root, "") == "Cause: a.py failed"
    assert replace_root(windows_file, root, "") == "a.py"
    assert replace_root(str(root), root, "") == ""
    assert replace_root(f"{root}-sibling/a.py", root, "") == f"{root}-sibling/a.py"
    assert replace_root(f"{root}/a.py", root, "<ROOT>") == "<ROOT>/a.py"


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("Checked {root}.", "Checked <data>."),
        ("Checked {root}, then {root}: done", "Checked <data>, then <data>: done"),
        ("path '{root}' and \"{root}\"", "path '<data>' and \"<data>\""),
        ("({root}) [{root}] {{{root}}}", "(<data>) [<data>] {{<data>}}"),
        ("{root} is the job", "<data> is the job"),
        ("{root}..", "<data>.."),
        ("{root}-sibling/a.py", "{root}-sibling/a.py"),
        ("{root}_old", "{root}_old"),
        ("{root}.bak/a.py", "{root}.bak/a.py"),
        ("{root}2", "{root}2"),
        ("{root}한글", "{root}한글"),
    ],
)
def test_replace_root_treats_punctuation_as_boundary(
    tmp_path: Path, template: str, expected: str
) -> None:
    """Free text ends a path with punctuation; name characters continue it."""

    root = (tmp_path / "0b7c8f8e-1111-4222-8333-444455556666").resolve()

    replaced = replace_root(template.format(root=root), root, "<data>")

    assert replaced == expected.format(root=root)


def test_replace_root_keeps_punctuation_after_dropped_root(tmp_path: Path) -> None:
    """Only a separator is dropped with an empty replacement."""

    root = (tmp_path / "upload").resolve()

    assert replace_root(f"Files in {root}.", root, "") == "Files in ."
    assert replace_root(f"({root}/a.py)", root, "") == "(a.py)"


def _write_upload(upload_root: Path, kind: str) -> Path:
    risky_source = "import os\n\n\ndef run(command):\n    return os.system(command)\n"
    if kind == "file":
        upload_root.mkdir(parents=True)
        target = upload_root / "file.py"
        target.write_text(risky_source, encoding="utf-8")
        return target
    project = upload_root / "myproj"
    (project / "pkg").mkdir(parents=True)
    (project / "a.py").write_text(risky_source, encoding="utf-8")
    (project / "pkg" / "b.py").write_text(
        "def load(text):\n    return eval(text)\n", encoding="utf-8"
    )
    return project


def _assert_no_server_path(output_paths: dict[str, Path], server_path: Path) -> None:
    for output_format in ("json", "html"):
        text = output_paths[output_format].read_text(encoding="utf-8")
        assert str(server_path) not in text, output_format
        assert str(server_path).replace("/", "\\") not in text, output_format


@pytest.mark.parametrize("kind", ["file", "project"])
def test_relativize_report_removes_upload_root_from_json_and_html(
    tmp_path: Path, kind: str
) -> None:
    upload_root = tmp_path / "job" / "upload"
    target = _write_upload(upload_root, kind)
    report = Phase1Pipeline(use_ruff=False).analyze(target)
    original = report.to_dict()

    relativized = relativize_report(report, upload_root, "")
    output_paths = ReportGenerator().write(relativized, tmp_path / "out")

    assert report.to_dict() == original
    assert relativized.review.findings
    _assert_no_server_path(output_paths, tmp_path)
    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    if kind == "file":
        assert output_paths["json"].name == "file.analysis.json"
        assert payload["analysis"]["path"] == "file.py"
        assert {finding["file"] for finding in payload["review"]["findings"]} == {
            "file.py"
        }
    else:
        assert output_paths["json"].name == "myproj.analysis.json"
        assert payload["analysis"]["root_path"] == "myproj"
        assert sorted(
            result["path"] for result in payload["analysis"]["file_results"]
        ) == ["myproj/a.py", "myproj/pkg/b.py"]
        assert {finding["file"] for finding in payload["review"]["findings"]} == {
            "myproj/a.py",
            "myproj/pkg/b.py",
        }


def _analyze_with_llm_findings(
    monkeypatch: pytest.MonkeyPatch,
    target: Path,
    llm_files: Sequence[str | None],
    summary: str = "Dynamic execution found.",
) -> AnalysisReport | ProjectReport:
    content = json.dumps(
        {
            "summary": summary,
            "risk_level": "high",
            "findings": [
                {
                    "title": "Dynamic execution",
                    "severity": "high",
                    "file": llm_file,
                    "line": 5,
                    "reason": "os.system runs shell commands.",
                    "recommendation": "Use subprocess.run with a list.",
                }
                for llm_file in llm_files
            ],
        }
    )

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: ResponseStub())
    pipeline = Phase1Pipeline(
        use_ruff=False,
        review_client=LocalLLMReviewClient(base_url="http://localhost:8000/v1"),
    )
    return pipeline.analyze(target)


@pytest.mark.parametrize(
    ("kind", "llm_files", "expected_files"),
    [
        ("file", ["", "file.py", "."], ["file.py", "file.py", None]),
        ("project", ["pkg/b.py", None, "."], ["myproj/pkg/b.py", None, "myproj"]),
    ],
)
def test_relativize_report_removes_upload_root_from_llm_finding_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    llm_files: list[str | None],
    expected_files: list[str | None],
) -> None:
    """LLM finding files are made absolute by the client, then relativized here.

    A single file's ``.`` is the upload directory itself. The emptied file is
    rebuilt through ``ReviewFinding``, which stores an empty file as ``None``.
    """

    upload_root = tmp_path / "job" / "upload"
    target = _write_upload(upload_root, kind)
    report = _analyze_with_llm_findings(monkeypatch, target, llm_files)

    relativized = relativize_report(report, upload_root, "")
    output_paths = ReportGenerator().write(relativized, tmp_path / "out")

    assert [finding.file for finding in relativized.review.findings] == expected_files
    _assert_no_server_path(output_paths, tmp_path)


@pytest.mark.parametrize(
    ("kind", "llm_files", "expected_files"),
    [
        (
            "file",
            [
                "../notes.py",
                "../../outside.py",
                "/etc/passwd",
                "//etc/passwd",
                "C:\\work\\x.py",
                "C:\\",
                "C:\\..",
                "C:\\x\\..",
                "C:\\x\\..\\y.py",
            ],
            [
                "<outside>/notes.py",
                "<outside>/outside.py",
                "<outside>/passwd",
                "<outside>/passwd",
                "<outside>/x.py",
                None,
                None,
                None,
                "<outside>/y.py",
            ],
        ),
        (
            "project",
            ["../../notes.py", "../a.py", "pkg/b.py"],
            ["<outside>/notes.py", "a.py", "myproj/pkg/b.py"],
        ),
    ],
)
def test_web_path_steps_remove_paths_outside_upload_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    llm_files: list[str],
    expected_files: list[str],
) -> None:
    """Upload root, then absolute finding files, then the job directory."""

    job_dir = tmp_path / "data" / "0b7c8f8e-1111-4222-8333-444455556666"
    upload_root = job_dir / "upload"
    target = _write_upload(upload_root, kind)
    report = _analyze_with_llm_findings(
        monkeypatch, target, llm_files, summary=f"Checked {job_dir}/cache, {job_dir}."
    )

    step1 = relativize_report(report, upload_root, "")
    step1_files = [finding.file for finding in step1.review.findings]
    step2 = name_absolute_finding_files(step1, upload_root)
    step3 = relativize_report(step2, job_dir, "<data>")
    output_paths = ReportGenerator().write(step3, tmp_path / "out")

    assert [finding.file for finding in step1.review.findings] == step1_files
    assert [finding.file for finding in step3.review.findings] == expected_files
    assert step3.review.summary == "Checked <data>/cache, <data>."
    _assert_no_server_path(output_paths, tmp_path)
    html = output_paths["html"].read_text(encoding="utf-8")
    assert "&lt;outside&gt;/notes.py" in html
    assert "<outside>" not in html


@pytest.mark.parametrize("kind", ["file", "project"])
def test_web_path_steps_hide_server_directory_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Files naming the upload root or a parent become None, not a folder name."""

    data_dir = tmp_path / "nurilab_data_SECRETNAME"
    job_dir = data_dir / "0b7c8f8e-1111-4222-8333-444455556666"
    upload_root = job_dir / "upload"
    target = _write_upload(upload_root, kind)
    # A single file resolves relative files from upload/, a folder from upload/myproj/.
    up = [".."] * (1 if kind == "file" else 2)
    parent_files = [
        "..",
        *("/".join(up + [".."] * extra) for extra in range(4)),
        str(job_dir),
        f"{job_dir}/../{job_dir.name}/",
        str(data_dir),
        "/",
        # Linux reads a leading "//" as "/", so these name the same parents.
        f"/{job_dir}",
        f"/{data_dir}",
        f"/{tmp_path}",
        "//",
        # Step 1 strips the upload root and leaves "../..", so step 2 resolves it.
        f"{upload_root}/..",
        f"{upload_root}/../../..",
        f"{upload_root}/../../../{data_dir.name}",
        f"{upload_root}/myproj/../../../../{data_dir.name}/",
        # Step 1 also strips the root before "\", so "\" must be read the same way.
        f"{upload_root}\\..\\..",
        f"{upload_root}\\..\\..\\..\\{data_dir.name}",
        # Server parents written entirely with "\".
        str(data_dir).replace("/", "\\"),
        str(job_dir).replace("/", "\\"),
        # An absolute path with "//" inside is read whole, not from the "//".
        f"{data_dir}//{job_dir.name}",
        f"{tmp_path}//{data_dir.name}",
    ]
    report = _analyze_with_llm_findings(monkeypatch, target, parent_files)

    step1 = relativize_report(report, upload_root, "")
    step2 = name_absolute_finding_files(step1, upload_root)
    step3 = relativize_report(step2, job_dir, "<data>")
    output_paths = ReportGenerator().write(step3, tmp_path / "out")

    assert [finding.file for finding in step3.review.findings] == [None] * len(
        parent_files
    )
    for output_format in ("json", "html"):
        text = output_paths[output_format].read_text(encoding="utf-8")
        assert "SECRETNAME" not in text, output_format
        assert job_dir.name not in text, output_format
        assert tmp_path.name not in text, output_format


@pytest.mark.parametrize("kind", ["file", "project"])
def test_web_path_steps_hide_parents_when_data_dir_has_backslash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Linux allows "\\" in a directory name; the root is read like the files."""

    data_dir = tmp_path / "nuri\\SECRETNAME"
    job_dir = data_dir / "0b7c8f8e-1111-4222-8333-444455556666"
    upload_root = job_dir / "upload"
    target = _write_upload(upload_root, kind)
    up = [".."] * (1 if kind == "file" else 2)
    parent_files = [
        "..",
        *("/".join(up + [".."] * extra) for extra in range(3)),
        str(job_dir),
        str(data_dir),
        f"{upload_root}/../..",
    ]
    report = _analyze_with_llm_findings(monkeypatch, target, parent_files)

    step1 = relativize_report(report, upload_root, "")
    step2 = name_absolute_finding_files(step1, upload_root)
    step3 = relativize_report(step2, job_dir, "<data>")
    output_paths = ReportGenerator().write(step3, tmp_path / "out")

    assert [finding.file for finding in step3.review.findings] == [None] * len(
        parent_files
    )
    for output_format in ("json", "html"):
        text = output_paths[output_format].read_text(encoding="utf-8")
        assert "SECRETNAME" not in text, output_format
        assert job_dir.name not in text, output_format


@pytest.mark.parametrize("kind", ["file", "project"])
def test_web_path_steps_read_server_paths_written_with_backslash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A "\\srv\\..." file is not absolute on Linux, so review() joins it under root."""

    data_dir = tmp_path / "nurilab_data_SECRETNAME"
    job_dir = data_dir / "0b7c8f8e-1111-4222-8333-444455556666"
    upload_root = job_dir / "upload"
    target = _write_upload(upload_root, kind)
    backslash_data_dir = str(data_dir).replace("/", "\\")
    llm_files = [
        f"{backslash_data_dir}\\x.py",
        f"{backslash_data_dir}\\..\\{data_dir.name}\\x.py",
    ]
    report = _analyze_with_llm_findings(monkeypatch, target, llm_files)

    step1 = relativize_report(report, upload_root, "")
    step2 = name_absolute_finding_files(step1, upload_root)
    step3 = relativize_report(step2, job_dir, "<data>")
    output_paths = ReportGenerator().write(step3, tmp_path / "out")

    assert [finding.file for finding in step3.review.findings] == [
        "<outside>/x.py",
        "<outside>/x.py",
    ]
    _assert_no_server_path(output_paths, tmp_path)
    for output_format in ("json", "html"):
        text = output_paths[output_format].read_text(encoding="utf-8")
        assert "SECRETNAME" not in text, output_format


def test_web_path_steps_resolve_dotdot_left_after_upload_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files are normalized: inside stays relative, outside is marked."""

    data_dir = tmp_path / "nurilab_data_SECRETNAME"
    job_dir = data_dir / "0b7c8f8e-1111-4222-8333-444455556666"
    upload_root = job_dir / "upload"
    target = _write_upload(upload_root, "project")
    llm_files = [
        f"{upload_root}/myproj/pkg/../a.py",
        f"{upload_root}/../../../{data_dir.name}/other.py",
        # Absolute, so step 1 does not match it; normalizing lands inside the root.
        f"{data_dir}/x/../{job_dir.name}/upload/myproj/a.py",
        f"{upload_root}\\..\\..\\..\\{data_dir.name}\\x.py",
        f"{data_dir}\\x.py",
    ]
    report = _analyze_with_llm_findings(monkeypatch, target, llm_files)

    step1 = relativize_report(report, upload_root, "")
    step2 = name_absolute_finding_files(step1, upload_root)
    step3 = relativize_report(step2, job_dir, "<data>")
    output_paths = ReportGenerator().write(step3, tmp_path / "out")

    assert [finding.file for finding in step3.review.findings] == [
        "myproj/a.py",
        "<outside>/other.py",
        "myproj/a.py",
        "<outside>/x.py",
        "<outside>/x.py",
    ]
    for output_format in ("json", "html"):
        text = output_paths[output_format].read_text(encoding="utf-8")
        assert "SECRETNAME" not in text, output_format


@pytest.mark.parametrize(
    ("kind", "expected_reason"),
    [
        ("file", "UTF-8 decode failed while reading file.py: invalid start byte."),
        (
            "project",
            "UTF-8 decode failed while reading myproj/bad.py: invalid start byte.",
        ),
    ],
)
def test_relativize_report_removes_upload_root_from_skip_reasons(
    tmp_path: Path, kind: str, expected_reason: str
) -> None:
    """Read failure reasons carry the server path inside free text."""

    upload_root = tmp_path / "job" / "upload"
    target = _write_upload(upload_root, kind)
    unreadable = target if kind == "file" else target / "bad.py"
    unreadable.write_bytes(b"\xff\xfe not utf-8")
    report = Phase1Pipeline(use_ruff=False).analyze(target)

    relativized = relativize_report(report, upload_root, "")
    output_paths = ReportGenerator().write(relativized, tmp_path / "out")

    analyses = (
        relativized.analysis.file_results
        if isinstance(relativized, ProjectReport)
        else [relativized.analysis]
    )
    assert [result.skip_reason for result in analyses if result.skipped] == [
        expected_reason
    ]
    if kind == "file":
        # Mock copies a single file's skip reason into its finding.
        assert [finding.reason for finding in relativized.review.findings] == [
            expected_reason
        ]
    _assert_no_server_path(output_paths, tmp_path)


def test_relativize_report_resolves_symlinked_relative_and_home_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline writes resolved paths, so the root is resolved the same way."""

    _write_upload(tmp_path / "real" / "upload", "project")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    report = Phase1Pipeline(use_ruff=False).analyze(
        tmp_path / "link" / "upload" / "myproj"
    )
    assert isinstance(report, ProjectReport)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    for root in (tmp_path / "link" / "upload", "link/upload", "~/link/upload"):
        relativized = relativize_report(report, root, "")
        assert relativized.analysis.root_path == "myproj", root


@pytest.mark.parametrize(
    "analysis",
    [
        PythonAnalysis(path="clean.py", line_count=1),
        PythonAnalysis(path="bad.py", line_count=0, skipped=True, skip_reason="x"),
        PythonAnalysis(path="broken.py", line_count=1, syntax_error="bad syntax"),
        ProjectAnalysis(
            root_path="proj",
            file_results=[PythonAnalysis(path="proj/a.py", line_count=1)],
        ),
    ],
    ids=["file", "skipped", "syntax_error", "project"],
)
def test_mock_review_records_mock_reviewer(
    analysis: PythonAnalysis | ProjectAnalysis,
) -> None:
    """Every Mock path is an ok review with no model, skipped files included."""

    review = MockLLMReviewClient().review(analysis)

    assert review.reviewer == ReviewerInfo(client="mock", model=None, status="ok")
    assert review.to_dict()["reviewer"] == {
        "client": "mock",
        "model": None,
        "status": "ok",
        "failure_code": None,
    }


def test_relativize_report_keeps_reviewer(tmp_path: Path) -> None:
    upload_root = tmp_path / "job" / "upload"
    report = Phase1Pipeline(use_ruff=False).analyze(_write_upload(upload_root, "file"))

    relativized = relativize_report(report, upload_root, "")

    assert relativized.review.reviewer == report.review.reviewer
    assert relativized.review.reviewer is not report.review.reviewer
