"""Screen result built from a saved (path-replaced) report JSON."""

from __future__ import annotations

from typing import Any

# Shown instead of the raw Local LLM failure reason, which holds the endpoint
# URL, "Cause:" exception text, and a response preview.
LLM_FAILURE_MESSAGES = {
    "timeout": (
        "LLM 응답 시간이 초과되었습니다. 모델 로딩 상태와 "
        "NURILAB_LLM_TIMEOUT 설정을 확인하세요."
    ),
    "http_error": (
        "LLM 서버가 오류 응답을 반환했습니다. 서버 로그와 모델 설정을 확인하세요."
    ),
    "connection_failed": (
        "LLM 서버에 연결하지 못했습니다. 서버 실행 상태와 주소 설정을 확인하세요."
    ),
    "invalid_response": (
        "LLM 서버 응답을 해석하지 못했습니다. 서버 상태와 API 호환성을 확인하세요."
    ),
    "json_parse_failed": (
        "LLM이 올바른 리뷰 JSON을 반환하지 않았습니다. 모델 출력을 확인하세요."
    ),
}
_LLM_FAILURE_FALLBACK = "LLM 리뷰에 실패했습니다. 서버 로그를 확인하세요."
_FINDING_FIELDS = (
    "title",
    "severity",
    "file",
    "line",
    "column",
    "source",
    "rule_id",
    "reason",
    "recommendation",
)


def build_screen_result(
    report: dict[str, Any], review_status: str | None, failure_code: str | None
) -> dict[str, Any]:
    """Return the fields the screen shows; the saved report is not changed.

    ``review_status`` and ``failure_code`` come from the job record. When the
    review failed, Local LLM finding reasons are replaced on the server so raw
    failure text never reaches the browser. The same fixed text is returned as
    ``review_failure_message`` for the warning at the top of the result.
    """

    review = report.get("review") or {}
    failure_message = None
    if review_status == "failed":
        failure_message = LLM_FAILURE_MESSAGES.get(
            failure_code or "", _LLM_FAILURE_FALLBACK
        )
    findings = []
    for raw in review.get("findings") or []:
        finding = {field: raw.get(field) for field in _FINDING_FIELDS}
        if failure_message is not None and finding["source"] == "local_llm":
            finding["reason"] = failure_message
        findings.append(finding)

    file_results = _file_results(report.get("analysis") or {})
    return {
        "analyzer_version": report.get("analyzer_version"),
        "generated_at": report.get("generated_at"),
        "summary": review.get("summary"),
        "review_failure_message": failure_message,
        "findings": findings,
        "static_signals": [
            signals
            for result in file_results
            if (signals := _static_signals(result)) is not None
        ],
        "skipped_files": [
            result.get("path") for result in file_results if result.get("skipped")
        ],
    }


def _file_results(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    # Folder reports list files; a single-file report is one file result.
    if "file_results" in analysis:
        return list(analysis.get("file_results") or [])
    return [analysis]


def _static_signals(result: dict[str, Any]) -> dict[str, Any] | None:
    calls = [
        {key: call.get(key) for key in ("name", "line", "category", "severity")}
        for call in result.get("suspicious_calls") or []
    ]
    secrets = [
        {key: secret.get(key) for key in ("kind", "line", "severity")}
        for secret in result.get("secrets") or []
    ]
    syntax_error = result.get("syntax_error")
    if not calls and not secrets and not syntax_error:
        return None
    return {
        "file": result.get("path"),
        "suspicious_calls": calls,
        "secrets": secrets,
        "syntax_error": syntax_error,
    }
