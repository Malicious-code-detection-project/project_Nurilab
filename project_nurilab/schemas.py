"""Shared data models for analysis, review, and reporting.

The project uses dataclasses instead of a heavier validation dependency for the
first prototype. These models make the pipeline contract explicit while keeping
serialization simple for Markdown and JSON report generation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
