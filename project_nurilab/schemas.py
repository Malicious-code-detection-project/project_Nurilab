"""Shared data models for analysis, review, and reporting.

The project uses dataclasses instead of a heavier validation dependency for the
first prototype. These models make the pipeline contract explicit while keeping
serialization simple for Markdown and JSON report generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ALLOWED_SEVERITIES = {"info", "low", "medium", "high", "critical", "unknown"}


@dataclass(slots=True)
class ImportFinding:
    """A Python import discovered by the AST analyzer."""

    module: str
    name: str | None
    alias: str | None
    line: int


@dataclass(slots=True)
class CodeSymbol:
    """A function or class symbol discovered in the target file."""

    name: str
    line: int


@dataclass(slots=True)
class SuspiciousCall:
    """A call expression that should be reviewed by a human or LLM."""

    name: str
    line: int
    category: str
    severity: str
    reason: str


@dataclass(slots=True)
class SecretFinding:
    """A potential hard-coded secret found with conservative pattern checks."""

    kind: str
    line: int
    preview: str
    severity: str
    reason: str


@dataclass(slots=True)
class PythonAnalysis:
    """Normalized static analysis result for one Python file."""

    path: str
    line_count: int
    language: str = "python"
    skipped: bool = False
    skip_reason: str | None = None
    syntax_error: str | None = None
    imports: list[ImportFinding] = field(default_factory=list)
    functions: list[CodeSymbol] = field(default_factory=list)
    classes: list[CodeSymbol] = field(default_factory=list)
    suspicious_calls: list[SuspiciousCall] = field(default_factory=list)
    secrets: list[SecretFinding] = field(default_factory=list)
    ruff_findings: list[RuffFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(slots=True)
class ReviewFinding:
    """A structured review finding shown in the final report."""

    title: str
    severity: str
    line: int | None
    reason: str
    recommendation: str
    file: str | None = None
    source: str = "review"
    column: int | None = None
    rule_id: str | None = None

    def __post_init__(self) -> None:
        # title
        if self.title is None or str(self.title).strip() == "":
            self.title = "LLM finding"
        else:
            self.title = str(self.title).strip()

        # severity
        if self.severity is None:
            self.severity = "unknown"
        else:
            sev = str(self.severity).strip().lower()
            if sev in ALLOWED_SEVERITIES:
                self.severity = sev
            else:
                self.severity = "unknown"

        # line
        if self.line is not None:
            try:
                self.line = int(self.line)
            except (ValueError, TypeError):
                self.line = None

        # reason
        if self.reason is None:
            self.reason = ""
        else:
            self.reason = str(self.reason).strip()

        # recommendation
        if self.recommendation is None:
            self.recommendation = ""
        else:
            self.recommendation = str(self.recommendation).strip()

        # file
        if self.file is not None:
            self.file = str(self.file).strip()
            if not self.file:
                self.file = None

        # source
        if self.source is None:
            self.source = "review"
        else:
            self.source = str(self.source).strip()

        # column
        if self.column is not None:
            try:
                self.column = int(self.column)
            except (ValueError, TypeError):
                self.column = None

        # rule_id
        if self.rule_id is not None:
            self.rule_id = str(self.rule_id).strip()
            if not self.rule_id:
                self.rule_id = None


@dataclass(slots=True)
class ReviewResult:
    """Structured output from a review client."""

    summary: str
    risk_level: str
    findings: list[ReviewFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(slots=True)
class AnalysisReport:
    """Top-level report payload persisted as JSON and Markdown."""

    generated_at: str
    analyzer_version: str
    analysis: PythonAnalysis
    review: ReviewResult

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "generated_at": self.generated_at,
            "analyzer_version": self.analyzer_version,
            "analysis": self.analysis.to_dict(),
            "review": self.review.to_dict(),
        }


@dataclass(slots=True)
class RuffFinding:
    """A Ruff issue normalized into the project analysis schema."""

    file: str
    line: int
    column: int
    rule_id: str
    message: str
    severity: str = "low"
    source: str = "ruff"


@dataclass(slots=True)
class ProjectFileSummary:
    """Aggregated finding counts and risk for one project file."""

    path: str
    risk_level: str
    finding_count: int
    suspicious_call_count: int = 0
    secret_count: int = 0
    syntax_error: bool = False
    ruff_finding_count: int = 0
    skipped: bool = False


@dataclass(slots=True)
class ProjectSummary:
    """Aggregated counts and risk for a project-level analysis."""

    total_files: int
    analyzed_files: int
    skipped_files: int
    severity_counts: dict[str, int] = field(default_factory=dict)
    risk_level: str = "low"
    file_summaries: list[ProjectFileSummary] = field(default_factory=list)


@dataclass(slots=True)
class ProjectAnalysis:
    """Normalized static analysis result for a Python project or directory."""

    root_path: str
    file_results: list[PythonAnalysis] = field(default_factory=list)
    ruff_findings: list[RuffFinding] = field(default_factory=list)
    summary: ProjectSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(slots=True)
class ProjectReport:
    """Top-level project report payload persisted as JSON and HTML."""

    generated_at: str
    analyzer_version: str
    analysis: ProjectAnalysis
    review: ReviewResult

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "generated_at": self.generated_at,
            "analyzer_version": self.analyzer_version,
            "analysis": self.analysis.to_dict(),
            "review": self.review.to_dict(),
        }
