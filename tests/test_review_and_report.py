from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_nurilab import __version__
from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.llm.review import MockLLMReviewClient
from project_nurilab.reports.generator import ReportGenerator
from project_nurilab.schemas import AnalysisReport


FIXTURES = Path(__file__).parent / "fixtures"


def test_mock_review_client_turns_static_signals_into_findings() -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)

    review = MockLLMReviewClient().review(analysis)

    assert review.risk_level == "high"
    assert len(review.findings) == 3
    assert any("os.system" in finding.title for finding in review.findings)
    assert any("hard-coded secret" in finding.title for finding in review.findings)


def test_report_generator_writes_markdown_and_json(tmp_path: Path) -> None:
    loaded = PythonFileLoader().load(FIXTURES / "vulnerable_sample.py")
    analysis = PythonStaticAnalyzer().analyze(loaded)
    review = MockLLMReviewClient().review(analysis)
    report = AnalysisReport(
        generated_at=datetime.now(UTC).isoformat(),
        analyzer_version=__version__,
        analysis=analysis,
        review=review,
    )

    markdown_path, json_path = ReportGenerator().write(report, tmp_path)

    assert markdown_path.exists()
    assert json_path.exists()
    assert "Python Code Review Report" in markdown_path.read_text(encoding="utf-8")
    assert '"risk_level": "high"' in json_path.read_text(encoding="utf-8")
