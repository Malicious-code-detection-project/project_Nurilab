from __future__ import annotations

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
)


FIXTURES = Path(__file__).parent / "fixtures"
REVIEW_QUALITY_FIXTURES = FIXTURES / "review_quality"


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
    assert 'class="path-text"' in html
    assert long_path in html
    assert "F401" in html
    assert "12:4" in html


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
