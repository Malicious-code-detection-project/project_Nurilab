"""Review client abstractions and implementations.

The static analyzers produce deterministic signals. Review clients turn those
signals into reviewer-facing summaries, risk levels, and recommendations. Mock
review keeps local tests deterministic; LocalLLMReviewClient targets vLLM's
OpenAI-compatible API.
"""

from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
from typing import Protocol, Any

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
            base_url or os.getenv("NURILAB_LLM_BASE_URL") or DEFAULT_LLM_BASE_URL
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
        except Exception as exc:  # noqa: BLE001 - preserve failures as report data.
            return ReviewResult(
                summary="Local LLM review failed. Static analysis results are still available.",
                risk_level="unknown",
                findings=[
                    ReviewFinding(
                        title="Local LLM connection failed",
                        severity="medium",
                        line=None,
                        source="local_llm",
                        reason=f"Local LLM server or API error: {exc}",
                        recommendation=(
                            "Check that vLLM is running, the network is accessible, "
                            "and the model is loaded."
                        ),
                    )
                ],
            )

        try:
            result = _parse_llm_review(content)
            # Normalize finding paths back to absolute paths
            if isinstance(analysis, ProjectAnalysis):
                for finding in result.findings:
                    if finding.file:
                        p = Path(finding.file)
                        if not p.is_absolute():
                            try:
                                finding.file = str(
                                    (Path(analysis.root_path) / p).resolve()
                                )
                            except Exception:
                                pass
            else:
                for finding in result.findings:
                    if not finding.file:
                        finding.file = analysis.path
                    else:
                        p = Path(finding.file)
                        if not p.is_absolute():
                            try:
                                finding.file = str(
                                    (Path(analysis.path).parent / p).resolve()
                                )
                            except Exception:
                                pass
            return result
        except Exception as exc:  # noqa: BLE001 - preserve failures as report data.
            return ReviewResult(
                summary="Local LLM review failed. Static analysis results are still available.",
                risk_level="unknown",
                findings=[
                    ReviewFinding(
                        title="Local LLM JSON parsing failed",
                        severity="medium",
                        line=None,
                        source="local_llm",
                        reason=str(exc),
                        recommendation=(
                            "Ensure the LLM prompt or parameters encourage valid JSON formatting. "
                            "The response content could not be parsed."
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


def get_relative_path(file_path: str, root_path: str) -> str:
    try:
        p = Path(file_path)
        r = Path(root_path)
        if p.is_absolute() and r.is_absolute():
            return str(p.relative_to(r))
    except Exception:
        pass
    return file_path


def _build_project_payload_summary(analysis: ProjectAnalysis) -> dict[str, Any]:
    # 1. Resolve all file results paths
    file_results_resolved = {}
    for r in analysis.file_results:
        try:
            res_path = str(Path(r.path).resolve())
        except Exception:
            res_path = r.path
        file_results_resolved[res_path] = r

    # 2. Group ruff findings by resolved path
    ruff_by_file = defaultdict(list)
    for ruff in analysis.ruff_findings:
        try:
            res_path = str(Path(ruff.file).resolve())
        except Exception:
            res_path = ruff.file
        ruff_by_file[res_path].append(ruff)

    # 3. Build file summaries for all resolved paths in file results
    file_analyses = []
    processed_paths = set()

    for res_path, file_result in file_results_resolved.items():
        processed_paths.add(res_path)
        file_ruff = ruff_by_file.get(res_path, [])

        has_signal = (
            file_result.skipped
            or file_result.syntax_error
            or len(file_result.suspicious_calls) > 0
            or len(file_result.secrets) > 0
            or len(file_ruff) > 0
        )

        if not has_signal:
            continue

        file_summary = {
            "file": get_relative_path(file_result.path, analysis.root_path),
            "line_count": file_result.line_count,
        }
        if file_result.skipped:
            file_summary["skipped"] = True
            file_summary["skip_reason"] = file_result.skip_reason
        if file_result.syntax_error:
            file_summary["syntax_error"] = file_result.syntax_error
        if file_result.suspicious_calls:
            file_summary["suspicious_calls"] = [
                {
                    "name": call.name,
                    "line": call.line,
                    "category": call.category,
                    "severity": call.severity,
                    "reason": call.reason,
                }
                for call in file_result.suspicious_calls
            ]
        if file_result.secrets:
            file_summary["secrets"] = [
                {
                    "kind": secret.kind,
                    "line": secret.line,
                    "preview": secret.preview,
                    "severity": secret.severity,
                    "reason": secret.reason,
                }
                for secret in file_result.secrets
            ]
        if file_ruff:
            file_summary["ruff_findings"] = [
                {
                    "line": ruff.line,
                    "column": ruff.column,
                    "rule_id": ruff.rule_id,
                    "message": ruff.message,
                    "severity": ruff.severity,
                }
                for ruff in file_ruff
            ]
        file_analyses.append(file_summary)

    # 4. Handle any ruff findings for paths not in file_results
    for res_path, file_ruff in ruff_by_file.items():
        if res_path in processed_paths:
            continue

        raw_path = file_ruff[0].file
        file_summary = {
            "file": get_relative_path(raw_path, analysis.root_path),
            "line_count": 0,
            "ruff_findings": [
                {
                    "line": ruff.line,
                    "column": ruff.column,
                    "rule_id": ruff.rule_id,
                    "message": ruff.message,
                    "severity": ruff.severity,
                }
                for ruff in file_ruff
            ],
        }
        file_analyses.append(file_summary)

    summary_dict = {}
    if analysis.summary:
        summary_dict = {
            "total_files": analysis.summary.total_files,
            "analyzed_files": analysis.summary.analyzed_files,
            "skipped_files": analysis.summary.skipped_files,
            "severity_counts": analysis.summary.severity_counts,
            "risk_level": analysis.summary.risk_level,
        }

    return {
        "root_path": analysis.root_path,
        "summary": summary_dict,
        "file_analyses": file_analyses,
    }


def _build_file_payload_summary(analysis: PythonAnalysis) -> dict[str, Any]:
    payload = {
        "file": analysis.path,
        "line_count": analysis.line_count,
    }
    if analysis.skipped:
        payload["skipped"] = True
        payload["skip_reason"] = analysis.skip_reason
    if analysis.syntax_error:
        payload["syntax_error"] = analysis.syntax_error
    if analysis.suspicious_calls:
        payload["suspicious_calls"] = [
            {
                "name": call.name,
                "line": call.line,
                "category": call.category,
                "severity": call.severity,
                "reason": call.reason,
            }
            for call in analysis.suspicious_calls
        ]
    if analysis.secrets:
        payload["secrets"] = [
            {
                "kind": secret.kind,
                "line": secret.line,
                "preview": secret.preview,
                "severity": secret.severity,
                "reason": secret.reason,
            }
            for secret in analysis.secrets
        ]
    if analysis.ruff_findings:
        payload["ruff_findings"] = [
            {
                "line": ruff.line,
                "column": ruff.column,
                "rule_id": ruff.rule_id,
                "message": ruff.message,
                "severity": ruff.severity,
            }
            for ruff in analysis.ruff_findings
        ]
    return payload


def _build_llm_prompt(analysis: PythonAnalysis | ProjectAnalysis) -> str:
    if isinstance(analysis, ProjectAnalysis):
        payload = _build_project_payload_summary(analysis)
    else:
        payload = _build_file_payload_summary(analysis)

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
        preview = content[:200] + "..." if len(content) > 200 else content
        raise ValueError(
            f"Failed to parse LLM response as JSON. Error: {exc.msg} at line {exc.lineno} col {exc.colno}. "
            f"Raw response preview: {repr(preview)}"
        ) from exc

    if not isinstance(payload, dict):
        payload = {}

    summary_value = payload.get("summary")
    if summary_value is None:
        summary = ""
    elif isinstance(summary_value, str):
        summary = summary_value
    else:
        summary = json.dumps(summary_value, ensure_ascii=False)

    findings_raw = payload.get("findings")
    if not isinstance(findings_raw, list):
        findings_raw = []

    findings: list[ReviewFinding] = []
    for item in findings_raw:
        if not isinstance(item, dict):
            continue

        title_val = item.get("title")
        title = str(title_val) if title_val is not None else ""

        severity_val = item.get("severity")
        severity = str(severity_val) if severity_val is not None else ""

        reason_val = item.get("reason")
        reason = str(reason_val) if reason_val is not None else ""

        rec_val = item.get("recommendation")
        recommendation = str(rec_val) if rec_val is not None else ""

        file_val = item.get("file")
        file_path = str(file_val) if file_val is not None else None

        line_val = item.get("line")
        line: int | None = None
        if line_val is not None:
            try:
                line = int(line_val)
            except (ValueError, TypeError):
                line = None

        findings.append(
            ReviewFinding(
                title=title,
                severity=severity,
                file=file_path,
                line=line,
                source="local_llm",
                reason=reason,
                recommendation=recommendation,
            )
        )

    risk_level_value = payload.get("risk_level")
    if risk_level_value is not None and str(risk_level_value).strip().lower() in {
        "low",
        "medium",
        "high",
    }:
        risk_level = str(risk_level_value).strip().lower()
    else:
        risk_level = _derive_risk_level([f.severity for f in findings])

    return ReviewResult(
        summary=summary,
        risk_level=risk_level,
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
