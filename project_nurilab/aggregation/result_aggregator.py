"""Project-level aggregation for file analysis and tool findings."""

from __future__ import annotations

from pathlib import Path

from project_nurilab.input.collector import CollectedInput
from project_nurilab.schemas import (
    ProjectAnalysis,
    ProjectFileSummary,
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
        file_summaries = self._build_file_summaries(
            collected_input=collected_input,
            file_results=file_results,
            ruff_findings=tool_findings,
        )

        summary = ProjectSummary(
            total_files=len(collected_input.python_files),
            analyzed_files=sum(1 for result in file_results if not result.skipped),
            skipped_files=skipped_files,
            severity_counts=severity_counts,
            risk_level=risk_level,
            file_summaries=file_summaries,
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

    def _build_file_summaries(
        self,
        collected_input: CollectedInput,
        file_results: list[PythonAnalysis],
        ruff_findings: list[RuffFinding],
    ) -> list[ProjectFileSummary]:
        root_path = Path(collected_input.root_path)
        ruff_by_file: dict[str, list[RuffFinding]] = {}
        for finding in ruff_findings:
            resolved_path = self._resolve_key(finding.file)
            ruff_by_file.setdefault(resolved_path, []).append(finding)

        summaries: list[ProjectFileSummary] = []
        processed_paths: set[str] = set()
        for result in file_results:
            resolved_path = self._resolve_key(result.path)
            processed_paths.add(resolved_path)
            file_ruff_findings = ruff_by_file.get(resolved_path, [])
            summaries.append(
                self._summarize_file(
                    path=result.path,
                    root_path=root_path,
                    suspicious_severities=[
                        call.severity for call in result.suspicious_calls
                    ],
                    secret_severities=[secret.severity for secret in result.secrets],
                    has_syntax_error=result.syntax_error is not None,
                    ruff_findings=file_ruff_findings,
                    skipped=result.skipped,
                )
            )

        for resolved_path, file_ruff_findings in ruff_by_file.items():
            if resolved_path in processed_paths:
                continue
            summaries.append(
                self._summarize_file(
                    path=file_ruff_findings[0].file,
                    root_path=root_path,
                    suspicious_severities=[],
                    secret_severities=[],
                    has_syntax_error=False,
                    ruff_findings=file_ruff_findings,
                    skipped=False,
                )
            )

        return sorted(summaries, key=self._file_summary_sort_key)

    def _summarize_file(
        self,
        path: str,
        root_path: Path,
        suspicious_severities: list[str],
        secret_severities: list[str],
        has_syntax_error: bool,
        ruff_findings: list[RuffFinding],
        skipped: bool,
    ) -> ProjectFileSummary:
        severities = [
            *suspicious_severities,
            *secret_severities,
            *(["medium"] if has_syntax_error else []),
            *(finding.severity for finding in ruff_findings),
        ]
        finding_count = (
            len(suspicious_severities)
            + len(secret_severities)
            + int(has_syntax_error)
            + len(ruff_findings)
        )

        return ProjectFileSummary(
            path=self._relative_path(path, root_path),
            risk_level=self._derive_file_risk(severities, skipped),
            finding_count=finding_count,
            suspicious_call_count=len(suspicious_severities),
            secret_count=len(secret_severities),
            syntax_error=has_syntax_error,
            ruff_finding_count=len(ruff_findings),
            skipped=skipped,
        )

    def _derive_file_risk(self, severities: list[str], skipped: bool) -> str:
        if severities:
            return max(severities, key=lambda severity: SEVERITY_ORDER.get(severity, 0))
        if skipped:
            return "unknown"
        return "low"

    def _file_summary_sort_key(
        self, summary: ProjectFileSummary
    ) -> tuple[int, int, str]:
        return (
            -SEVERITY_ORDER.get(summary.risk_level, 0),
            -summary.finding_count,
            summary.path,
        )

    def _relative_path(self, file_path: str, root_path: Path) -> str:
        path = Path(file_path)
        try:
            return str(path.resolve().relative_to(root_path.resolve()))
        except (OSError, ValueError):
            return file_path

    def _resolve_key(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve())
        except OSError:
            return file_path
