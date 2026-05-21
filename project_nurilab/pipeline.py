"""Phase 1 analysis pipeline orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_nurilab import __version__
from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.config import DEFAULT_REPORT_DIR
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.llm.review import MockLLMReviewClient
from project_nurilab.reports.generator import ReportGenerator
from project_nurilab.schemas import AnalysisReport


class Phase1Pipeline:
    """Run the Python-only code review MVP from input file to reports."""

    def __init__(
        self,
        loader: PythonFileLoader | None = None,
        analyzer: PythonStaticAnalyzer | None = None,
        review_client: MockLLMReviewClient | None = None,
        report_generator: ReportGenerator | None = None,
    ) -> None:
        self.loader = loader or PythonFileLoader()
        self.analyzer = analyzer or PythonStaticAnalyzer()
        self.review_client = review_client or MockLLMReviewClient()
        self.report_generator = report_generator or ReportGenerator()

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path = DEFAULT_REPORT_DIR,
    ) -> tuple[AnalysisReport, Path, Path]:
        """Execute the pipeline and return report payload plus output paths."""

        loaded_file = self.loader.load(input_path)
        analysis = self.analyzer.analyze(loaded_file)
        review = self.review_client.review(analysis)

        report = AnalysisReport(
            generated_at=datetime.now(UTC).isoformat(),
            analyzer_version=__version__,
            analysis=analysis,
            review=review,
        )
        markdown_path, json_path = self.report_generator.write(report, output_dir)
        return report, markdown_path, json_path
