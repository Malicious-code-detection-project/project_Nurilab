"""Review client abstractions.

Phase 1 starts with a deterministic mock client so the pipeline can be tested on
any laptop. A local OpenAI-compatible client can replace this class later
without changing the analyzer or report generator.
"""

from __future__ import annotations

from project_nurilab.schemas import PythonAnalysis, ReviewFinding, ReviewResult


class MockLLMReviewClient:
    """Generate a review from static analysis signals without calling an LLM."""

    def review(self, analysis: PythonAnalysis) -> ReviewResult:
        """Return a deterministic review result for one analysis payload."""

        if analysis.skipped:
            return ReviewResult(
                summary="Analysis was skipped because the file exceeded phase 1 limits.",
                risk_level="unknown",
                findings=[
                    ReviewFinding(
                        title="File skipped",
                        severity="info",
                        line=None,
                        reason=analysis.skip_reason or "The file was skipped.",
                        recommendation="Reduce the file to 200 lines or analyze a smaller unit.",
                    )
                ],
            )

        if analysis.syntax_error:
            return ReviewResult(
                summary="The file could not be parsed as valid Python code.",
                risk_level="medium",
                findings=[
                    ReviewFinding(
                        title="Python syntax error",
                        severity="medium",
                        line=None,
                        reason=analysis.syntax_error,
                        recommendation="Fix the syntax error before running security review.",
                    )
                ],
            )

        findings: list[ReviewFinding] = []

        for call in analysis.suspicious_calls:
            findings.append(
                ReviewFinding(
                    title=f"Review suspicious call: {call.name}",
                    severity=call.severity,
                    line=call.line,
                    reason=call.reason,
                    recommendation=_recommend_for_category(call.category),
                )
            )

        for secret in analysis.secrets:
            findings.append(
                ReviewFinding(
                    title=f"Potential hard-coded secret: {secret.kind}",
                    severity=secret.severity,
                    line=secret.line,
                    reason=f"{secret.reason} Preview: {secret.preview}",
                    recommendation=(
                        "Move secrets to a secret manager or environment variable, "
                        "then rotate the exposed value if it was real."
                    ),
                )
            )

        risk_level = _derive_risk_level([finding.severity for finding in findings])
        summary = _build_summary(analysis, findings, risk_level)
        return ReviewResult(summary=summary, risk_level=risk_level, findings=findings)


def _derive_risk_level(severities: list[str]) -> str:
    """Map finding severities into one report-level risk value."""

    if "critical" in severities or "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    if "low" in severities:
        return "low"
    return "low"


def _build_summary(
    analysis: PythonAnalysis,
    findings: list[ReviewFinding],
    risk_level: str,
) -> str:
    """Create a concise human-readable summary for the report."""

    if not findings:
        return (
            "No suspicious calls or hard-coded secrets were detected by the "
            "phase 1 static checks. This does not prove the code is secure, "
            "but it is a clean baseline for the current rule set."
        )

    return (
        f"Detected {len(findings)} review finding(s) in {analysis.line_count} "
        f"line(s). Overall risk is {risk_level}. Prioritize high-severity "
        "execution, deserialization, and secret handling findings first."
    )


def _recommend_for_category(category: str) -> str:
    """Return practical remediation guidance for a suspicious call category."""

    recommendations = {
        "dynamic_execution": (
            "Avoid dynamic execution. If unavoidable, strictly validate inputs "
            "and isolate execution from untrusted data."
        ),
        "command_execution": (
            "Avoid shell=True, pass arguments as a list, validate user input, "
            "and enforce timeouts."
        ),
        "unsafe_deserialization": (
            "Do not deserialize untrusted input. Use safer formats such as JSON "
            "or safe loaders where available."
        ),
        "network_access": (
            "Validate destination URLs, set timeouts, and avoid sending secrets "
            "or sensitive data."
        ),
        "file_access": (
            "Validate paths, avoid path traversal, and apply least-privilege "
            "file permissions."
        ),
    }
    return recommendations.get(category, "Review the call path and validate inputs.")
