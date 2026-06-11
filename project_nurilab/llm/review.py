"""Review client abstractions and implementations.

The static analyzers produce deterministic signals. Review clients turn those
signals into reviewer-facing summaries, risk levels, and recommendations. Mock
review keeps local tests deterministic; LocalLLMReviewClient targets vLLM's
OpenAI-compatible API.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

import requests

from project_nurilab.config import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_LLM_TIMEOUT_SECONDS,
)
from project_nurilab.schemas import (
    ProjectAnalysis,
    PythonAnalysis,
    ReviewFinding,
    ReviewResult,
)


class ReviewClient(Protocol):
    """Common review client interface for mock and local LLM implementations."""

    def review(self, analysis: PythonAnalysis | ProjectAnalysis) -> ReviewResult:
        """Return a structured review result for file or project analysis."""


class MockReviewClient:
    """Generate a deterministic review from static analysis signals."""

    def review(self, analysis: PythonAnalysis | ProjectAnalysis) -> ReviewResult:
        """Return review findings without calling an LLM."""

        if isinstance(analysis, ProjectAnalysis):
            return self._review_project(analysis)
        return self._review_file(analysis)

    def _review_project(self, analysis: ProjectAnalysis) -> ReviewResult:
        findings: list[ReviewFinding] = []
        for file_result in analysis.file_results:
            findings.extend(_file_findings(file_result))
        for ruff in analysis.ruff_findings:
            findings.append(
                ReviewFinding(
                    title=f"Ruff issue: {ruff.rule_id}",
                    severity=ruff.severity,
                    file=ruff.file,
                    line=ruff.line,
                    column=ruff.column,
                    source=ruff.source,
                    rule_id=ruff.rule_id,
                    reason=ruff.message,
                    recommendation="Review the Ruff rule and adjust the code or configuration.",
                )
            )

        risk_level = _derive_risk_level([finding.severity for finding in findings])
        summary = _build_project_summary(analysis, findings, risk_level)
        return ReviewResult(summary=summary, risk_level=risk_level, findings=findings)

    def _review_file(self, analysis: PythonAnalysis) -> ReviewResult:
        if analysis.skipped:
            return ReviewResult(
                summary="Analysis was skipped because the file exceeded phase 1 limits.",
                risk_level="unknown",
                findings=[
                    ReviewFinding(
                        title="File skipped",
                        severity="info",
                        file=analysis.path,
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
                        file=analysis.path,
                        line=None,
                        reason=analysis.syntax_error,
                        recommendation="Fix the syntax error before running security review.",
                    )
                ],
            )

        findings = _file_findings(analysis)
        risk_level = _derive_risk_level([finding.severity for finding in findings])
        summary = _build_file_summary(analysis, findings, risk_level)
        return ReviewResult(summary=summary, risk_level=risk_level, findings=findings)


# Backward-compatible alias for existing imports/tests and older docs.
MockLLMReviewClient = MockReviewClient


class LocalLLMReviewClient:
    """Call a vLLM OpenAI-compatible chat completion endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float = DEFAULT_LLM_TEMPERATURE,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("NURILAB_LLM_BASE_URL")
            or DEFAULT_LLM_BASE_URL
        ).rstrip("/")
        self.model = model or os.getenv("NURILAB_LLM_MODEL") or DEFAULT_LLM_MODEL
        self.timeout = _resolve_timeout(timeout)
        self.temperature = temperature

    def review(self, analysis: PythonAnalysis | ProjectAnalysis) -> ReviewResult:
        """Generate a structured review by calling the local LLM server."""

        prompt = _build_llm_prompt(analysis)
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a senior secure code reviewer. "
                                "Return only valid JSON."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_llm_review(content)
        except Exception as exc:  # noqa: BLE001 - preserve failures as report data.
            return ReviewResult(
                summary="Local LLM review failed. Static analysis results are still available.",
                risk_level="unknown",
                findings=[
                    ReviewFinding(
                        title="Local LLM review failed",
                        severity="medium",
                        line=None,
                        source="local_llm",
                        reason=str(exc),
                        recommendation=(
                            "Check that vLLM is running, the model is loaded, "
                            "and the response is valid JSON."
                        ),
                    )
                ],
            )


def _file_findings(analysis: PythonAnalysis) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []

    if analysis.syntax_error:
        findings.append(
            ReviewFinding(
                title="Python syntax error",
                severity="medium",
                file=analysis.path,
                line=None,
                source="ast",
                reason=analysis.syntax_error,
                recommendation="Fix the syntax error before running security review.",
            )
        )

    for call in analysis.suspicious_calls:
        findings.append(
            ReviewFinding(
                title=f"Review suspicious call: {call.name}",
                severity=call.severity,
                file=analysis.path,
                line=call.line,
                source="pattern",
                reason=call.reason,
                recommendation=_recommend_for_category(call.category),
            )
        )

    for secret in analysis.secrets:
        findings.append(
            ReviewFinding(
                title=f"Potential hard-coded secret: {secret.kind}",
                severity=secret.severity,
                file=analysis.path,
                line=secret.line,
                source="secret",
                reason=f"{secret.reason} Preview: {secret.preview}",
                recommendation=(
                    "Move secrets to a secret manager or environment variable, "
                    "then rotate the exposed value if it was real."
                ),
            )
        )

    return findings


def _derive_risk_level(severities: list[str]) -> str:
    """Map finding severities into one report-level risk value."""

    if "critical" in severities or "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    if "low" in severities:
        return "low"
    return "low"


def _build_file_summary(
    analysis: PythonAnalysis,
    findings: list[ReviewFinding],
    risk_level: str,
) -> str:
    """Create a concise human-readable summary for one file."""

    if not findings:
        return (
            "No suspicious calls or hard-coded secrets were detected by the "
            "current static checks. This does not prove the code is secure, "
            "but it is a clean baseline for the current rule set."
        )

    return (
        f"Detected {len(findings)} review finding(s) in {analysis.line_count} "
        f"line(s). Overall risk is {risk_level}. Prioritize high-severity "
        "execution, deserialization, and secret handling findings first."
    )


def _build_project_summary(
    analysis: ProjectAnalysis,
    findings: list[ReviewFinding],
    risk_level: str,
) -> str:
    summary = analysis.summary
    if summary is None:
        return f"Detected {len(findings)} finding(s). Overall risk is {risk_level}."
    return (
        f"Analyzed {summary.analyzed_files} of {summary.total_files} Python file(s), "
        f"with {summary.skipped_files} skipped file(s). Detected {len(findings)} "
        f"finding(s). Overall project risk is {risk_level}."
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


def _build_llm_prompt(analysis: PythonAnalysis | ProjectAnalysis) -> str:
    payload = analysis.to_dict()
    return (
        """Review the following normalized Python static analysis result.
        Return JSON with keys: summary, risk_level, findings.
        Each finding must include title, severity, file, line, reason, recommendation.
        For 'risk_level' and 'severity', strictly use only one of the following values: "low", "medium", or "high".

        IMPORTANT: You are a static signal interpreter, not a definitive malware judge.
        Your role is to explain what the payload indicates objectively.
        
        Step-by-step Analysis (Chain of Thought):
        1. Identify the static signals and their locations in the payload.
        2. Analyze the specific context (e.g., function names, arguments) for each signal.
        3. Synthesize how the context interacts with the static signal to explain the code's behavior objectively.
        4. Formulate the final JSON. For the 'reason' field, output your synthesized explanation rather than just the static rule description.

        Example Response:
        {
        "summary": "Found high severity issue with dynamic execution.",
        "risk_level": "high",
        "findings": [
            {
            "title": "Dynamic execution via eval",
            "severity": "high",
            "file": "main.py",
            "line": 42,
            "reason": "The eval() function is used with user-provided input, which indicates a risk of arbitrary code execution.",
            "recommendation": "Use ast.literal_eval() for safe evaluation of strings."
            }
        ]
        }
        
        """
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _parse_llm_review(content: str) -> ReviewResult:
    normalized_content = _extract_json_payload(content)
    try:
        payload = json.loads(normalized_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {content}") from exc

    summary_value = payload.get("summary", "")
    if isinstance(summary_value, str):
        summary = summary_value
    else:
        summary = json.dumps(summary_value, ensure_ascii=False)

    findings = [
        ReviewFinding(
            title=str(item.get("title", "LLM finding")),
            severity=str(item.get("severity", "medium")),
            file=item.get("file"),
            line=item.get("line"),
            source="local_llm",
            reason=str(item.get("reason", "")),
            recommendation=str(item.get("recommendation", "")),
        )
        for item in payload.get("findings", [])
    ]
    return ReviewResult(
        summary=summary,
        risk_level=str(payload.get("risk_level", _derive_risk_level([f.severity for f in findings]))),
        findings=findings,
    )


def _extract_json_payload(content: str) -> str:
    """Extract a JSON object from raw LLM content.

    Local models often wrap JSON in markdown fences or add a short preamble.
    Accept those variants before failing the parse.
    """

    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        while lines and lines[-1].strip() == "```":
            lines.pop()
        stripped = "\n".join(lines).strip()

    json_start = stripped.find("{")
    json_end = stripped.rfind("}")
    if json_start != -1 and json_end != -1 and json_end >= json_start:
        return stripped[json_start : json_end + 1]
    return stripped


def _resolve_timeout(timeout: float | None) -> float:
    if timeout is not None:
        return timeout
    configured_timeout = os.getenv("NURILAB_LLM_TIMEOUT")
    if configured_timeout:
        return float(configured_timeout)
    return DEFAULT_LLM_TIMEOUT_SECONDS
