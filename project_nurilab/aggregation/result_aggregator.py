"""Project-level aggregation for file analysis and tool findings."""

from __future__ import annotations

from pathlib import Path

from project_nurilab.input.collector import CollectedInput
from project_nurilab.schemas import (
    ProjectAnalysis,
    ProjectSummary,
    PythonAnalysis,
    RuffFinding,
)


SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
    "unknown": -1,
}


class ResultAggregator:
    """Aggregate file-level findings into one project analysis."""

    def aggregate(
        self,
        collected_input: CollectedInput,
        file_results: list[PythonAnalysis],
        ruff_findings: list[RuffFinding] | None = None,
    ) -> ProjectAnalysis:
        """Build a project analysis payload from collected analysis results."""

        tool_findings = ruff_findings or []
        severity_counts = self._count_severities(file_results, tool_findings)
        risk_level = self._derive_project_risk(severity_counts)
        skipped_files = self._count_skipped(collected_input, file_results)

        summary = ProjectSummary(
            total_files=len(collected_input.python_files),
            analyzed_files=sum(1 for result in file_results if not result.skipped),
            skipped_files=skipped_files,
            severity_counts=severity_counts,
            risk_level=risk_level,
        )

        return ProjectAnalysis(
            root_path=str(collected_input.root_path),
            file_results=file_results,
            ruff_findings=tool_findings,
            summary=summary,
        )

    def _count_severities(
        self,
        file_results: list[PythonAnalysis],
        ruff_findings: list[RuffFinding],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in file_results:
            for call in result.suspicious_calls:
                counts[call.severity] = counts.get(call.severity, 0) + 1
            for secret in result.secrets:
                counts[secret.severity] = counts.get(secret.severity, 0) + 1
            if result.syntax_error:
                counts["medium"] = counts.get("medium", 0) + 1
        for finding in ruff_findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def _derive_project_risk(self, severity_counts: dict[str, int]) -> str:
        if not severity_counts:
            return "low"
        return max(
            severity_counts,
            key=lambda severity: SEVERITY_ORDER.get(severity, 0),
        )

    def _count_skipped(
        self,
        collected_input: CollectedInput,
        file_results: list[PythonAnalysis],
    ) -> int:
        skipped_analysis = sum(1 for result in file_results if result.skipped)
        skipped_before_analysis = sum(
            1
            for skipped_path in collected_input.skipped_paths
            if Path(skipped_path.path).suffix == ".py"
        )
        return skipped_analysis + skipped_before_analysis
