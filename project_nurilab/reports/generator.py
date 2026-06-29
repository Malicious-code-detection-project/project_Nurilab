"""Report generation for human-readable and machine-readable outputs."""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Sequence
from typing import Protocol

from project_nurilab.schemas import AnalysisReport, ProjectFileSummary, ProjectReport


ReportPayload = AnalysisReport | ProjectReport
SEVERITY_RANK = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
    "unknown": 0,
}


class NamedLineSymbol(Protocol):
    """Structural protocol for symbols that have a name and line."""

    name: str
    line: int


class ReportGenerator:
    """Persist report output in HTML, JSON, and optional Markdown formats."""

    SUPPORTED_FORMATS = frozenset({"html", "json", "md"})
    DEFAULT_FORMATS = ("html", "json")

    def write(
        self,
        report: ReportPayload,
        output_dir: str | Path,
        formats: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Path]:
        """Write report files for the requested formats.

        JSON is the canonical machine-readable result. HTML is the default
        human-readable report. Markdown remains available for users who prefer
        lightweight text reports or documentation-friendly output.
        """

        target_dir = Path(output_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        normalized_formats = self._normalize_formats(formats)
        stem = _report_stem(report)
        output_paths: dict[str, Path] = {}

        for output_format in normalized_formats:
            if output_format == "html":
                html_path = target_dir / f"{stem}.analysis.html"
                html_path.write_text(self.to_html(report), encoding="utf-8")
                output_paths["html"] = html_path
            elif output_format == "json":
                json_path = target_dir / f"{stem}.analysis.json"
                json_path.write_text(
                    json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                output_paths["json"] = json_path
            elif output_format == "md":
                markdown_path = target_dir / f"{stem}.analysis.md"
                markdown_path.write_text(self.to_markdown(report), encoding="utf-8")
                output_paths["md"] = markdown_path

        return output_paths

    def _normalize_formats(
        self,
        formats: list[str] | tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        """Normalize, validate, and de-duplicate requested output formats."""

        requested_formats = formats or self.DEFAULT_FORMATS
        normalized: list[str] = []

        for output_format in requested_formats:
            normalized_format = output_format.lower().strip()
            if normalized_format not in self.SUPPORTED_FORMATS:
                supported = ", ".join(sorted(self.SUPPORTED_FORMATS))
                raise ValueError(
                    f"Unsupported report format: {output_format}. "
                    f"Supported formats: {supported}"
                )
            if normalized_format not in normalized:
                normalized.append(normalized_format)

        return tuple(normalized)

    def to_markdown(self, report: ReportPayload) -> str:
        """Render a readable Markdown report."""

        if isinstance(report, ProjectReport):
            return self._project_to_markdown(report)

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

    def to_html(self, report: ReportPayload) -> str:
        """Render a self-contained HTML report for human reviewers."""

        if isinstance(report, ProjectReport):
            return self._project_to_html(report)

        analysis = report.analysis
        review = report.review
        severity_class = _html_class_for_severity(review.risk_level)

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Python Code Review Report</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #5f6b7a;
      --line: #d9dee7;
      --low: #1f7a3f;
      --medium: #9a6400;
      --high: #b42318;
      --critical: #7a1e70;
      --info: #255f99;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}
    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      margin-bottom: 24px;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
      line-height: 1.2;
    }}
    h1 {{
      font-size: 30px;
    }}
    h2 {{
      margin-top: 28px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--line);
      font-size: 21px;
    }}
    h3 {{
      font-size: 17px;
    }}
    .summary {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin: 16px 0;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin: 16px 0;
    }}
    .meta-item, .finding, .section-list {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    code {{
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 13px;
      background: #eef1f5;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    ul {{
      margin: 8px 0 0;
      padding-left: 22px;
    }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      color: white;
      font-weight: 700;
      font-size: 13px;
    }}
    .severity-low {{ background: var(--low); }}
    .severity-medium {{ background: var(--medium); }}
    .severity-high {{ background: var(--high); }}
    .severity-critical {{ background: var(--critical); }}
    .severity-info, .severity-unknown {{ background: var(--info); }}
    .finding {{
      margin: 12px 0;
      border-left: 5px solid var(--line);
    }}
    .finding.severity-low {{ border-left-color: var(--low); }}
    .finding.severity-medium {{ border-left-color: var(--medium); }}
    .finding.severity-high {{ border-left-color: var(--high); }}
    .finding.severity-critical {{ border-left-color: var(--critical); }}
    .finding.severity-info {{ border-left-color: var(--info); }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Python Code Review Report</h1>
      <span class="badge {severity_class}">{_escape_html(review.risk_level)}</span>
    </header>

    <section class="summary">
      <h2>Summary</h2>
      <p>{_escape_html(review.summary)}</p>
    </section>

    <section>
      <h2>Metadata</h2>
      <div class="meta-grid">
        {_render_html_meta("Generated At", report.generated_at)}
        {_render_html_meta("Analyzer Version", report.analyzer_version)}
        {_render_html_meta("File", analysis.path)}
        {_render_html_meta("Lines", str(analysis.line_count))}
        {_render_html_meta("Skipped", str(analysis.skipped))}
      </div>
    </section>

    {_render_html_optional_section("Skip Reason", analysis.skip_reason)}
    {_render_html_optional_section("Syntax Error", analysis.syntax_error)}

    <section>
      <h2>Static Analysis</h2>
      <div class="meta-grid">
        {_render_html_list("Imports", _plain_imports(report))}
        {_render_html_list("Functions", _plain_symbols("function", analysis.functions))}
        {_render_html_list("Classes", _plain_symbols("class", analysis.classes))}
      </div>
      {_render_html_list("Suspicious Calls", _plain_suspicious_calls(report))}
      {_render_html_list("Potential Secrets", _plain_secrets(report))}
    </section>

    <section>
      <h2>Findings</h2>
      {_render_html_findings(report)}
    </section>
  </main>
</body>
</html>
"""

    def _project_to_markdown(self, report: ProjectReport) -> str:
        analysis = report.analysis
        summary = analysis.summary
        lines = [
            "# Python Project Review Report",
            "",
            "## Metadata",
            "",
            f"- Generated At: `{report.generated_at}`",
            f"- Analyzer Version: `{report.analyzer_version}`",
            f"- Root Path: `{analysis.root_path}`",
            f"- Risk Level: `{report.review.risk_level}`",
            "",
            "## Summary",
            "",
            report.review.summary,
            "",
        ]

        if summary:
            lines.extend(
                [
                    "## Project Counts",
                    "",
                    f"- Total Python Files: `{summary.total_files}`",
                    f"- Analyzed Files: `{summary.analyzed_files}`",
                    f"- Skipped Files: `{summary.skipped_files}`",
                    f"- Severity Counts: `{summary.severity_counts}`",
                    "",
                ]
            )
            if summary.file_summaries:
                lines.extend(["## File Summary", ""])
                for file_summary in summary.file_summaries:
                    lines.extend(
                        [
                            f"### `{file_summary.path}`",
                            "",
                            f"- Risk Level: `{file_summary.risk_level}`",
                            f"- Findings: `{file_summary.finding_count}`",
                            (
                                "- Suspicious Calls: "
                                f"`{file_summary.suspicious_call_count}`"
                            ),
                            f"- Potential Secrets: `{file_summary.secret_count}`",
                            f"- Syntax Error: `{file_summary.syntax_error}`",
                            f"- Ruff Findings: `{file_summary.ruff_finding_count}`",
                            f"- Skipped: `{file_summary.skipped}`",
                            "",
                        ]
                    )

        lines.extend(["## Findings", "", *_render_review_findings(report), ""])
        lines.extend(["## File Results", ""])
        for result in analysis.file_results:
            lines.extend(
                [
                    f"### `{result.path}`",
                    "",
                    f"- Lines: `{result.line_count}`",
                    f"- Skipped: `{result.skipped}`",
                    f"- Syntax Error: `{result.syntax_error}`",
                    f"- Suspicious Calls: `{len(result.suspicious_calls)}`",
                    f"- Potential Secrets: `{len(result.secrets)}`",
                    "",
                ]
            )

        if analysis.ruff_findings:
            lines.extend(["## Ruff Findings", ""])
            for finding in analysis.ruff_findings:
                lines.append(
                    f"- `{finding.file}:{finding.line}:{finding.column}` "
                    f"{finding.rule_id} - {finding.message}"
                )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _project_to_html(self, report: ProjectReport) -> str:
        analysis = report.analysis
        summary = analysis.summary
        severity_class = _html_class_for_severity(report.review.risk_level)
        overview_cards = _render_html_project_overview(report)
        severity_counts = (
            _render_html_severity_counts(summary.severity_counts) if summary else ""
        )

        file_summary_rows = ""
        if summary and summary.file_summaries:
            file_summary_rows = _render_html_project_file_summaries(
                summary.file_summaries
            )

        file_rows = "".join(
            _render_html_file_result(result) for result in analysis.file_results
        )
        ruff_rows = _render_html_ruff_findings(analysis.ruff_findings)

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Python Project Review Report</title>
  <style>{_shared_css()}</style>
</head>
<body>
  <main>
    <header>
      <h1>Python Project Review Report</h1>
      <span class="badge {severity_class}">{_escape_html(report.review.risk_level)}</span>
    </header>
    <section class="summary project-overview">
      <div>
        <h2>Project Summary</h2>
        <p>{_escape_html(report.review.summary)}</p>
      </div>
      <div class="overview-grid">
        {overview_cards}
      </div>
      {severity_counts}
    </section>
    <section>
      <h2>Metadata</h2>
      <div class="meta-grid">
        {_render_html_meta("Generated At", report.generated_at)}
        {_render_html_meta("Analyzer Version", report.analyzer_version)}
        {_render_html_meta("Root Path", analysis.root_path)}
        {_render_html_meta("Risk Level", report.review.risk_level)}
      </div>
    </section>
    <section>
      <h2>File Summary</h2>
      {file_summary_rows or '<div class="section-list"><p>No file summaries available.</p></div>'}
    </section>
    <section>
      <h2>Findings</h2>
      {_render_html_project_findings(report)}
    </section>
    <section>
      <h2>File Results</h2>
      {file_rows or '<div class="section-list"><p>No Python files analyzed.</p></div>'}
    </section>
    <section>
      <h2>Ruff Findings</h2>
      {ruff_rows}
    </section>
  </main>
</body>
</html>
"""


def _render_imports(report: AnalysisReport) -> list[str]:
    if not report.analysis.imports:
        return ["- None"]
    rendered: list[str] = []
    for item in report.analysis.imports:
        name = f"{item.module}.{item.name}" if item.name else item.module
        alias = f" as {item.alias}" if item.alias else ""
        rendered.append(f"- Line {item.line}: `{name}{alias}`")
    return rendered


def _plain_imports(report: AnalysisReport) -> list[str]:
    if not report.analysis.imports:
        return ["None"]
    rendered: list[str] = []
    for item in report.analysis.imports:
        name = f"{item.module}.{item.name}" if item.name else item.module
        alias = f" as {item.alias}" if item.alias else ""
        rendered.append(f"Line {item.line}: {name}{alias}")
    return rendered


def _render_symbols(label: str, symbols: Sequence[NamedLineSymbol]) -> list[str]:
    if not symbols:
        return ["- None"]
    return [f"- Line {symbol.line}: `{label} {symbol.name}`" for symbol in symbols]


def _plain_symbols(label: str, symbols: Sequence[NamedLineSymbol]) -> list[str]:
    if not symbols:
        return ["None"]
    return [f"Line {symbol.line}: {label} {symbol.name}" for symbol in symbols]


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


def _plain_suspicious_calls(report: AnalysisReport) -> list[str]:
    if not report.analysis.suspicious_calls:
        return ["None"]
    return [
        (
            f"Line {call.line}: {call.name} "
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


def _plain_secrets(report: AnalysisReport) -> list[str]:
    if not report.analysis.secrets:
        return ["None"]
    return [
        (
            f"Line {secret.line}: {secret.kind} "
            f"({secret.severity}) - {secret.reason} Preview: {secret.preview}"
        )
        for secret in report.analysis.secrets
    ]


def _render_review_findings(report: ReportPayload) -> list[str]:
    if not report.review.findings:
        return ["- No findings for the current phase 1 rule set."]

    rendered: list[str] = []
    for index, finding in enumerate(report.review.findings, start=1):
        location = _finding_location(finding)
        rendered.extend(
            [
                f"### {index}. {finding.title}",
                "",
                f"- Severity: `{finding.severity}`",
                f"- Location: {location}",
                f"- Source: `{finding.source}`",
                f"- Reason: {finding.reason}",
                f"- Recommendation: {finding.recommendation}",
                "",
            ]
        )
    return rendered


def _escape_html(value: str) -> str:
    """Escape HTML-sensitive characters without adding a dependency."""

    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _html_class_for_severity(severity: str) -> str:
    return f"severity-{severity.lower()}"


def _render_html_meta(label: str, value: str) -> str:
    return (
        '<div class="meta-item">'
        f'<span class="label">{_escape_html(label)}</span>'
        f"<code>{_escape_html(value)}</code>"
        "</div>"
    )


def _render_html_optional_section(title: str, value: str | None) -> str:
    if not value:
        return ""
    return (
        "<section>"
        f"<h2>{_escape_html(title)}</h2>"
        f'<div class="section-list"><p>{_escape_html(value)}</p></div>'
        "</section>"
    )


def _render_html_list(title: str, values: list[str]) -> str:
    items = "".join(f"<li>{_escape_html(value)}</li>" for value in values)
    return (
        '<div class="section-list">'
        f"<h3>{_escape_html(title)}</h3>"
        f"<ul>{items}</ul>"
        "</div>"
    )


def _render_html_findings(
    report: ReportPayload, *, sort_by_severity: bool = False
) -> str:
    if not report.review.findings:
        return '<div class="section-list"><p>No findings for the current rule set.</p></div>'

    rendered: list[str] = []
    findings = report.review.findings
    if sort_by_severity:
        findings = sorted(
            findings,
            key=lambda finding: -SEVERITY_RANK.get(finding.severity, 0),
        )

    for finding in findings:
        severity_class = _html_class_for_severity(finding.severity)
        location = _finding_location(finding)
        rendered.append(
            f'<article class="finding {severity_class}">'
            f"<h3>{_escape_html(finding.title)}</h3>"
            f'<p><span class="badge {severity_class}">'
            f"{_escape_html(finding.severity)}</span></p>"
            f"<p><strong>Location:</strong> {_escape_html(location)}</p>"
            f"<p><strong>Reason:</strong> {_escape_html(finding.reason)}</p>"
            f"<p><strong>Recommendation:</strong> "
            f"{_escape_html(finding.recommendation)}</p>"
            "</article>"
        )
    return "\n".join(rendered)


def _render_html_project_findings(report: ProjectReport) -> str:
    if not report.review.findings:
        return '<div class="section-list"><p>No findings for the current rule set.</p></div>'

    grouped: dict[tuple[str, str], list] = {}
    for finding in sorted(
        report.review.findings,
        key=lambda finding: (
            -SEVERITY_RANK.get(finding.severity, 0),
            finding.file or "",
            finding.line if finding.line is not None else 0,
            finding.source,
            finding.title,
        ),
    ):
        grouped.setdefault(
            (finding.severity, finding.file or "Project-level findings"), []
        ).append(finding)

    rendered: list[str] = []
    for (severity, file_path), findings in grouped.items():
        severity_class = _html_class_for_severity(severity)
        rendered.append(
            f'<div class="section-list finding-group {severity_class}">'
            f'<h3><code class="path-text">{_escape_html(file_path)}</code></h3>'
            f'<p><span class="badge {severity_class}">{_escape_html(severity)}</span></p>'
            "</div>"
        )
        for finding in findings:
            severity_class = _html_class_for_severity(finding.severity)
            location = _finding_location(finding)
            rule = finding.rule_id or "N/A"
            rendered.append(
                f'<article class="finding {severity_class}">'
                f"<h3>{_escape_html(finding.title)}</h3>"
                f'<p><span class="badge {severity_class}">'
                f"{_escape_html(finding.severity)}</span></p>"
                '<div class="detail-grid">'
                f"{_render_html_meta('Location', location)}"
                f"{_render_html_meta('Source', finding.source)}"
                f"{_render_html_meta('Rule', rule)}"
                "</div>"
                f"<p><strong>Reason:</strong> {_escape_html(finding.reason)}</p>"
                f"<p><strong>Recommendation:</strong> "
                f"{_escape_html(finding.recommendation)}</p>"
                "</article>"
            )
    return "\n".join(rendered)


def _report_stem(report: ReportPayload) -> str:
    if isinstance(report, ProjectReport):
        return Path(report.analysis.root_path).name or "project"
    return Path(report.analysis.path).stem


def _finding_location(finding) -> str:
    line = f"Line {finding.line}" if finding.line is not None else "No line"
    column = f", Column {finding.column}" if finding.column is not None else ""
    file = f"{finding.file}: " if finding.file else ""
    return f"{file}{line}{column}"


def _render_html_project_overview(report: ProjectReport) -> str:
    summary = report.analysis.summary
    if summary is None:
        return "".join(
            [
                _render_html_stat_card("Risk Level", report.review.risk_level),
                _render_html_stat_card("Total Python Files", "0"),
                _render_html_stat_card("Analyzed Files", "0"),
                _render_html_stat_card("Skipped Files", "0"),
            ]
        )

    return "".join(
        [
            _render_html_stat_card("Risk Level", summary.risk_level),
            _render_html_stat_card("Total Python Files", str(summary.total_files)),
            _render_html_stat_card("Analyzed Files", str(summary.analyzed_files)),
            _render_html_stat_card("Skipped Files", str(summary.skipped_files)),
        ]
    )


def _render_html_stat_card(label: str, value: str) -> str:
    return (
        '<div class="stat-card">'
        f'<span class="label">{_escape_html(label)}</span>'
        f"<strong>{_escape_html(value)}</strong>"
        "</div>"
    )


def _render_html_severity_counts(severity_counts: dict[str, int]) -> str:
    if not severity_counts:
        return '<div class="severity-strip"><span>No severity findings</span></div>'

    chips = []
    for severity in sorted(
        severity_counts,
        key=lambda value: -SEVERITY_RANK.get(value, 0),
    ):
        severity_class = _html_class_for_severity(severity)
        chips.append(
            f'<span class="severity-chip {severity_class}">'
            f"{_escape_html(severity)}: {_escape_html(str(severity_counts[severity]))}"
            "</span>"
        )
    return '<div class="severity-strip">' + "".join(chips) + "</div>"


def _render_html_file_result(result) -> str:
    severity = "info" if result.skipped else "low"
    if result.syntax_error:
        severity = "medium"
    if result.secrets or result.suspicious_calls:
        severity = "high"
    severity_class = _html_class_for_severity(severity)
    return (
        f'<article class="finding {severity_class}">'
        f'<h3><code class="path-text">{_escape_html(result.path)}</code></h3>'
        f"<p><strong>Lines:</strong> {_escape_html(str(result.line_count))}</p>"
        f"<p><strong>Skipped:</strong> {_escape_html(str(result.skipped))}</p>"
        f"<p><strong>Syntax Error:</strong> "
        f"{_escape_html(str(result.syntax_error))}</p>"
        f"<p><strong>Suspicious Calls:</strong> "
        f"{_escape_html(str(len(result.suspicious_calls)))}</p>"
        f"<p><strong>Potential Secrets:</strong> "
        f"{_escape_html(str(len(result.secrets)))}</p>"
        "</article>"
    )


def _render_html_project_file_summaries(
    file_summaries: list[ProjectFileSummary],
) -> str:
    rendered: list[str] = []
    for file_summary in file_summaries:
        severity_class = _html_class_for_severity(file_summary.risk_level)
        rendered.append(
            f'<article class="finding {severity_class}">'
            f'<h3><code class="path-text">{_escape_html(file_summary.path)}</code></h3>'
            f'<p><span class="badge {severity_class}">'
            f"{_escape_html(file_summary.risk_level)}</span></p>"
            f"<p><strong>Findings:</strong> "
            f"{_escape_html(str(file_summary.finding_count))}</p>"
            f"<p><strong>Suspicious Calls:</strong> "
            f"{_escape_html(str(file_summary.suspicious_call_count))}</p>"
            f"<p><strong>Potential Secrets:</strong> "
            f"{_escape_html(str(file_summary.secret_count))}</p>"
            f"<p><strong>Syntax Error:</strong> "
            f"{_escape_html(str(file_summary.syntax_error))}</p>"
            f"<p><strong>Ruff Findings:</strong> "
            f"{_escape_html(str(file_summary.ruff_finding_count))}</p>"
            f"<p><strong>Skipped:</strong> {_escape_html(str(file_summary.skipped))}</p>"
            "</article>"
        )
    return "\n".join(rendered)


def _render_html_ruff_findings(ruff_findings) -> str:
    if not ruff_findings:
        return '<div class="section-list"><p>No Ruff findings.</p></div>'

    rendered: list[str] = []
    for finding in sorted(
        ruff_findings,
        key=lambda item: (
            -SEVERITY_RANK.get(item.severity, 0),
            item.file,
            item.line,
            item.column,
            item.rule_id,
        ),
    ):
        severity_class = _html_class_for_severity(finding.severity)
        rendered.append(
            f'<article class="finding {severity_class}">'
            f'<h3><code class="path-text">{_escape_html(finding.file)}</code></h3>'
            '<div class="detail-grid">'
            f"{_render_html_meta('Location', f'{finding.line}:{finding.column}')}"
            f"{_render_html_meta('Rule', finding.rule_id)}"
            f"{_render_html_meta('Severity', finding.severity)}"
            "</div>"
            f"<p>{_escape_html(finding.message)}</p>"
            "</article>"
        )
    return "\n".join(rendered)


def _shared_css() -> str:
    return """
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #5f6b7a;
      --line: #d9dee7;
      --low: #1f7a3f;
      --medium: #9a6400;
      --high: #b42318;
      --critical: #7a1e70;
      --info: #255f99;
    }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }
    main {
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    header { margin-bottom: 24px; }
    h1, h2, h3 { margin: 0 0 12px; line-height: 1.2; }
    h1 { font-size: 30px; }
    h2 {
      margin-top: 28px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--line);
      font-size: 21px;
    }
    h3 { font-size: 17px; }
    .summary {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin: 16px 0;
    }
    .project-overview {
      display: grid;
      gap: 16px;
    }
    .overview-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
    }
    .stat-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfe;
    }
    .stat-card strong {
      display: block;
      margin-top: 4px;
      font-size: 20px;
    }
    .severity-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .severity-chip {
      border-radius: 999px;
      padding: 4px 10px;
      color: white;
      font-weight: 700;
      font-size: 13px;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin: 16px 0;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 8px;
      margin: 10px 0;
    }
    .meta-item, .finding, .section-list {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    code {
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 13px;
      background: #eef1f5;
      padding: 2px 5px;
      border-radius: 4px;
    }
    .path-text {
      white-space: normal;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    ul { margin: 8px 0 0; padding-left: 22px; }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      color: white;
      font-weight: 700;
      font-size: 13px;
    }
    .severity-low { background: var(--low); }
    .severity-medium { background: var(--medium); }
    .severity-high { background: var(--high); }
    .severity-critical { background: var(--critical); }
    .severity-info, .severity-unknown { background: var(--info); }
    .finding { margin: 12px 0; border-left: 5px solid var(--line); }
    .finding.severity-low { border-left-color: var(--low); }
    .finding.severity-medium { border-left-color: var(--medium); }
    .finding.severity-high { border-left-color: var(--high); }
    .finding.severity-critical { border-left-color: var(--critical); }
    .finding.severity-info { border-left-color: var(--info); }
    """
