"""Markdown and JSON report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from project_nurilab.schemas import AnalysisReport


class NamedLineSymbol(Protocol):
    """Structural protocol for symbols that have a name and line."""

    name: str
    line: int


class ReportGenerator:
    """Persist report output in Markdown and JSON formats."""

    def write(self, report: AnalysisReport, output_dir: str | Path) -> tuple[Path, Path]:
        """Write Markdown and JSON files, returning their paths."""

        target_dir = Path(output_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(report.analysis.path).stem
        markdown_path = target_dir / f"{stem}.analysis.md"
        json_path = target_dir / f"{stem}.analysis.json"

        markdown_path.write_text(self.to_markdown(report), encoding="utf-8")
        json_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return markdown_path, json_path

    def to_markdown(self, report: AnalysisReport) -> str:
        """Render a readable Markdown report."""

        analysis = report.analysis
        review = report.review

        lines = [
            "# Python Code Review Report",
            "",
            "## Metadata",
            "",
            f"- Generated At: `{report.generated_at}`",
            f"- Analyzer Version: `{report.analyzer_version}`",
            f"- File: `{analysis.path}`",
            f"- Lines: `{analysis.line_count}`",
            f"- Skipped: `{analysis.skipped}`",
            f"- Risk Level: `{review.risk_level}`",
            "",
            "## Summary",
            "",
            review.summary,
            "",
        ]

        if analysis.skip_reason:
            lines.extend(["## Skip Reason", "", analysis.skip_reason, ""])

        if analysis.syntax_error:
            lines.extend(["## Syntax Error", "", analysis.syntax_error, ""])

        lines.extend(
            [
                "## Static Analysis",
                "",
                "### Imports",
                "",
                *_render_imports(report),
                "",
                "### Functions",
                "",
                *_render_symbols("function", analysis.functions),
                "",
                "### Classes",
                "",
                *_render_symbols("class", analysis.classes),
                "",
                "### Suspicious Calls",
                "",
                *_render_suspicious_calls(report),
                "",
                "### Potential Secrets",
                "",
                *_render_secrets(report),
                "",
                "## Findings",
                "",
                *_render_review_findings(report),
                "",
            ]
        )

        return "\n".join(lines).rstrip() + "\n"


def _render_imports(report: AnalysisReport) -> list[str]:
    if not report.analysis.imports:
        return ["- None"]
    rendered: list[str] = []
    for item in report.analysis.imports:
        name = f"{item.module}.{item.name}" if item.name else item.module
        alias = f" as {item.alias}" if item.alias else ""
        rendered.append(f"- Line {item.line}: `{name}{alias}`")
    return rendered


def _render_symbols(label: str, symbols: list[NamedLineSymbol]) -> list[str]:
    if not symbols:
        return ["- None"]
    return [f"- Line {symbol.line}: `{label} {symbol.name}`" for symbol in symbols]


def _render_suspicious_calls(report: AnalysisReport) -> list[str]:
    if not report.analysis.suspicious_calls:
        return ["- None"]
    return [
        (
            f"- Line {call.line}: `{call.name}` "
            f"({call.severity}, {call.category}) - {call.reason}"
        )
        for call in report.analysis.suspicious_calls
    ]


def _render_secrets(report: AnalysisReport) -> list[str]:
    if not report.analysis.secrets:
        return ["- None"]
    return [
        (
            f"- Line {secret.line}: `{secret.kind}` "
            f"({secret.severity}) - {secret.reason} Preview: `{secret.preview}`"
        )
        for secret in report.analysis.secrets
    ]


def _render_review_findings(report: AnalysisReport) -> list[str]:
    if not report.review.findings:
        return ["- No findings for the current phase 1 rule set."]

    rendered: list[str] = []
    for index, finding in enumerate(report.review.findings, start=1):
        line = f"Line {finding.line}" if finding.line is not None else "No line"
        rendered.extend(
            [
                f"### {index}. {finding.title}",
                "",
                f"- Severity: `{finding.severity}`",
                f"- Location: {line}",
                f"- Reason: {finding.reason}",
                f"- Recommendation: {finding.recommendation}",
                "",
            ]
        )
    return rendered
