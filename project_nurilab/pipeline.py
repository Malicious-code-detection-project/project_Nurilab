"""Analysis pipeline orchestration for file and project targets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_nurilab import __version__
from project_nurilab.aggregation.result_aggregator import ResultAggregator
from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.analyzers.tools import RuffToolCollector
from project_nurilab.config import DEFAULT_REPORT_DIR
from project_nurilab.input.collector import InputCollector
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.llm.review import MockReviewClient, ReviewClient
from project_nurilab.reports.generator import ReportGenerator
from project_nurilab.schemas import AnalysisReport, ProjectReport, PythonAnalysis


class Phase1Pipeline:
    """Run Python code review analysis for one file or a project directory."""

    def __init__(
        self,
        loader: PythonFileLoader | None = None,
        collector: InputCollector | None = None,
        analyzer: PythonStaticAnalyzer | None = None,
        ruff_collector: RuffToolCollector | None = None,
        aggregator: ResultAggregator | None = None,
        review_client: ReviewClient | None = None,
        report_generator: ReportGenerator | None = None,
        use_ruff: bool = True,
    ) -> None:
        self.loader = loader or PythonFileLoader()
        self.collector = collector or InputCollector()
        self.analyzer = analyzer or PythonStaticAnalyzer()
        self.ruff_collector = ruff_collector or RuffToolCollector()
        self.aggregator = aggregator or ResultAggregator()
        self.review_client = review_client or MockReviewClient()
        self.report_generator = report_generator or ReportGenerator()
        self.use_ruff = use_ruff

    def run(
        self,
        input_path: str | Path,
        output_dir: str | Path = DEFAULT_REPORT_DIR,
        formats: list[str] | tuple[str, ...] | None = None,
    ) -> tuple[AnalysisReport | ProjectReport, dict[str, Path]]:
        """Execute the pipeline and return report payload plus output paths."""

        target = Path(input_path).expanduser().resolve()
        collected_input = self.collector.collect(target)
        file_results = [
            self.analyzer.analyze(self.loader.load(path))
            for path in collected_input.python_files
        ]

        if target.is_file():
            analysis = file_results[0] if file_results else self._skipped_file(target)
            if self.use_ruff:
                analysis.ruff_findings = self.ruff_collector.collect(target)
            review = self.review_client.review(analysis)
            single_file_report = AnalysisReport(
                generated_at=datetime.now(UTC).isoformat(),
                analyzer_version=__version__,
                analysis=analysis,
                review=review,
            )
            output_paths = self.report_generator.write(
                single_file_report,
                output_dir,
                formats=formats,
            )
            return single_file_report, output_paths

        ruff_findings = self.ruff_collector.collect(target) if self.use_ruff else []
        project_analysis = self.aggregator.aggregate(
            collected_input=collected_input,
            file_results=file_results,
            ruff_findings=ruff_findings,
        )
        review = self.review_client.review(project_analysis)

        project_report = ProjectReport(
            generated_at=datetime.now(UTC).isoformat(),
            analyzer_version=__version__,
            analysis=project_analysis,
            review=review,
        )
        output_paths = self.report_generator.write(
            project_report, output_dir, formats=formats
        )
        return project_report, output_paths

    def _skipped_file(self, target: Path) -> PythonAnalysis:
        return PythonAnalysis(
            path=str(target),
            line_count=0,
            skipped=True,
            skip_reason="No analyzable Python file was collected from the input.",
        )
