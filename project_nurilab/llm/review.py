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

SEVERITY_RANK = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
    "unknown": 0,
}
_REVIEW_RISK_LEVELS = ("low", "medium", "high")
_REVIEW_REQUIRED_FIELDS = ("summary", "risk_level", "findings")
_REVIEW_FINDING_REQUIRED_FIELDS = (
    "title",
    "severity",
    "file",
    "line",
    "reason",
    "recommendation",
)
_REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "risk_level": {"type": "string", "enum": list(_REVIEW_RISK_LEVELS)},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": list(_REVIEW_RISK_LEVELS),
                    },
                    "file": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"]},
                    "reason": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": list(_REVIEW_FINDING_REQUIRED_FIELDS),
            },
        },
    },
    "required": list(_REVIEW_REQUIRED_FIELDS),
}


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

        findings = _sort_review_findings(findings)
        risk_level = _derive_risk_level([finding.severity for finding in findings])
        summary = _build_project_summary(analysis, findings, risk_level)
        return ReviewResult(summary=summary, risk_level=risk_level, findings=findings)

    def _review_file(self, analysis: PythonAnalysis) -> ReviewResult:
        if analysis.skipped:
            return ReviewResult(
                summary="Analysis was skipped because the file could not be loaded.",
                risk_level="unknown",
                findings=[
                    ReviewFinding(
                        title="File skipped",
                        severity="info",
                        file=analysis.path,
                        line=None,
                        reason=analysis.skip_reason or "The file was skipped.",
                        recommendation="Review the skip reason and fix the input so it can be read and analyzed.",
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
        endpoint = f"{self.base_url}/chat/completions"
        try:
            response = requests.post(
                endpoint,
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "reasoning_effort": "low",
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "nurilab_security_review",
                            "strict": True,
                            "schema": _REVIEW_JSON_SCHEMA,
                        },
                    },
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a senior secure code reviewer. "
                                "Return only the final JSON object that matches "
                                "the response schema."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout as exc:
            return _local_llm_request_failure(
                title="Local LLM request timed out",
                reason=(
                    "Local LLM request timed out while calling "
                    f"{endpoint} with model {self.model} after "
                    f"{self.timeout:g} second(s). Cause: {exc}. "
                    "Static analysis results are still included in this report."
                ),
                recommendation=(
                    "Confirm that vLLM has finished loading the model, verify "
                    "the model name, then increase NURILAB_LLM_TIMEOUT if the "
                    "model needs more time to respond."
                ),
            )
        except requests.exceptions.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else "unknown"
            response_text = response.text if response is not None else ""
            response_preview = _preview_response_text(response_text)
            response_detail = (
                f" Response preview: {response_preview}" if response_preview else ""
            )
            return _local_llm_request_failure(
                title="Local LLM HTTP error",
                reason=(
                    "Local LLM endpoint returned an HTTP error while calling "
                    f"{endpoint} with model {self.model}. Status: HTTP {status_code}. "
                    f"Cause: {exc}.{response_detail} Static analysis results "
                    "are still included in this report."
                ),
                recommendation=(
                    "Check the Local LLM base URL (NURILAB_LLM_BASE_URL), the "
                    "model name, the OpenAI-compatible /chat/completions route, "
                    "and vLLM server logs for the returned status code."
                ),
            )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.InvalidSchema,
            requests.exceptions.InvalidURL,
            requests.exceptions.MissingSchema,
            ConnectionError,
        ) as exc:
            return _local_llm_request_failure(
                title="Local LLM connection failed",
                reason=(
                    "Unable to reach the Local LLM endpoint while calling "
                    f"{endpoint} with model {self.model}. Cause: {exc}. "
                    "Static analysis results are still included in this report."
                ),
                recommendation=(
                    "Start or restart vLLM, confirm that NURILAB_LLM_BASE_URL "
                    "points to the listening host and port, verify DNS/network "
                    "access, and confirm the configured model name."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - preserve failures as report data.
            return _local_llm_request_failure(
                title="Local LLM connection failed",
                reason=(
                    "Local LLM server or API call failed while calling "
                    f"{endpoint} with model {self.model}. Cause: {exc}. "
                    "Static analysis results are still included in this report."
                ),
                recommendation=(
                    "Check the Local LLM server logs, confirm the configured "
                    "base URL and model name, and verify the OpenAI-compatible "
                    "response shape."
                ),
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
                        reason=(
                            "Local LLM returned a response that could not be parsed "
                            f"as the expected JSON review. Cause: {exc}. Static "
                            "analysis results are still included in this report."
                        ),
                        recommendation=(
                            "Inspect the raw response preview in the cause, then "
                            "confirm the model is returning only JSON with summary, "
                            "risk_level, and findings. This does not change the "
                            "existing JSON extraction behavior."
                        ),
                    )
                ],
            )


def _preview_response_text(text: str, limit: int = 300) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= limit:
        return compact_text
    return f"{compact_text[:limit]}..."


def _local_llm_request_failure(
    title: str,
    reason: str,
    recommendation: str | None = None,
) -> ReviewResult:
    return ReviewResult(
        summary="Local LLM review failed. Static analysis results are still available.",
        risk_level="unknown",
        findings=[
            ReviewFinding(
                title=title,
                severity="medium",
                line=None,
                source="local_llm",
                reason=reason,
                recommendation=recommendation
                or (
                    "Check that vLLM is running, the network is accessible, "
                    "and the model is loaded."
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


def _sort_review_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    return sorted(findings, key=_review_finding_sort_key)


def _review_finding_sort_key(
    finding: ReviewFinding,
) -> tuple[int, str, int, str, str]:
    line = finding.line if finding.line is not None else 0
    return (
        -SEVERITY_RANK.get(finding.severity, 0),
        finding.file or "",
        line,
        finding.source,
        finding.title,
    )


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
        Explain only what the payload indicates and do not infer source context that is
        absent from the normalized signals. For each reason, identify the relevant signal
        and location without presenting the signal as proof of malicious intent.
        Return only the final JSON object. Do not add Markdown, surrounding prose, or a
        reasoning trace.

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

    review_payload = _validate_llm_review_payload(payload, content)
    findings = [
        ReviewFinding(
            title=item["title"],
            severity=item["severity"],
            file=item["file"],
            line=item["line"],
            source="local_llm",
            reason=item["reason"],
            recommendation=item["recommendation"],
        )
        for item in review_payload["findings"]
    ]

    return ReviewResult(
        summary=review_payload["summary"],
        risk_level=review_payload["risk_level"],
        findings=findings,
    )


def _validate_llm_review_payload(payload: Any, content: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _llm_review_schema_error(
            f"top level must be an object, got {_json_type_name(payload)}",
            content,
        )

    _validate_exact_fields(
        payload,
        required=set(_REVIEW_REQUIRED_FIELDS),
        location="review",
        content=content,
    )

    if not isinstance(payload["summary"], str):
        raise _llm_review_schema_error(
            "review.summary must be a string",
            content,
        )

    risk_level = payload["risk_level"]
    if not isinstance(risk_level, str) or risk_level not in _REVIEW_RISK_LEVELS:
        raise _llm_review_schema_error(
            "review.risk_level must be one of: low, medium, high",
            content,
        )

    findings = payload["findings"]
    if not isinstance(findings, list):
        raise _llm_review_schema_error(
            "review.findings must be an array",
            content,
        )

    for index, finding in enumerate(findings):
        location = f"review.findings[{index}]"
        if not isinstance(finding, dict):
            raise _llm_review_schema_error(
                f"{location} must be an object",
                content,
            )
        _validate_exact_fields(
            finding,
            required=set(_REVIEW_FINDING_REQUIRED_FIELDS),
            location=location,
            content=content,
        )
        if not isinstance(finding["title"], str):
            raise _llm_review_schema_error(
                f"{location}.title must be a string",
                content,
            )
        severity = finding["severity"]
        if not isinstance(severity, str) or severity not in _REVIEW_RISK_LEVELS:
            raise _llm_review_schema_error(
                f"{location}.severity must be one of: low, medium, high",
                content,
            )
        if finding["file"] is not None and not isinstance(finding["file"], str):
            raise _llm_review_schema_error(
                f"{location}.file must be a string or null",
                content,
            )
        line = finding["line"]
        if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
            raise _llm_review_schema_error(
                f"{location}.line must be an integer or null",
                content,
            )
        if not isinstance(finding["reason"], str):
            raise _llm_review_schema_error(
                f"{location}.reason must be a string",
                content,
            )
        if not isinstance(finding["recommendation"], str):
            raise _llm_review_schema_error(
                f"{location}.recommendation must be a string",
                content,
            )

    return payload


def _validate_exact_fields(
    payload: dict[str, Any],
    *,
    required: set[str],
    location: str,
    content: str,
) -> None:
    actual = set(payload)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    violations: list[str] = []
    if missing:
        violations.append(f"missing required field(s): {', '.join(missing)}")
    if unexpected:
        violations.append(f"unexpected field(s): {', '.join(unexpected)}")
    if violations:
        raise _llm_review_schema_error(
            f"{location} {'; '.join(violations)}",
            content,
        )


def _llm_review_schema_error(message: str, content: str) -> ValueError:
    preview = _preview_response_text(content, limit=200)
    return ValueError(
        "Local LLM response does not match the review schema: "
        f"{message}. Raw response preview: {preview!r}"
    )


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


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

    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        return stripped

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
        try:
            return float(configured_timeout)
        except ValueError as exc:
            raise ValueError(
                "NURILAB_LLM_TIMEOUT must be a numeric timeout in seconds."
            ) from exc
    return DEFAULT_LLM_TIMEOUT_SECONDS
