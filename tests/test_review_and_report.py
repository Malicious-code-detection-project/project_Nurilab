from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from project_nurilab import __version__
from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.llm.review import MockLLMReviewClient
from project_nurilab.reports.generator import ReportGenerator
from project_nurilab.schemas import (
    AnalysisReport,
    ProjectAnalysis,
    ProjectFileSummary,
    ProjectReport,
    ProjectSummary,
    PythonAnalysis,
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
    assert set(review) == {"summary", "risk_level", "findings"}
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
