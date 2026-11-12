from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from project_nurilab.config import DEFAULT_LLM_MODEL
from project_nurilab.llm.review import LocalLLMReviewClient, MockReviewClient
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.reports.paths import relativize_report
from project_nurilab.schemas import AnalysisReport, ReviewResult
from project_nurilab.web.app import create_app
from project_nurilab.web.settings import WebSettings


FIXTURES = Path(__file__).parent / "fixtures" / "review_quality"
WEB_PROJECT = Path(__file__).parent / "fixtures" / "review_quality_project"
# Added to NURILAB_LLM_TIMEOUT for the connection check, analysis, and polling.
WEB_JOB_MARGIN_SECONDS = 60.0
RUN_LOCAL_LLM = os.getenv("NURILAB_RUN_LOCAL_LLM") == "1"
LOCAL_LLM_FAILURE_TITLES = {
    "Local LLM connection failed",
    "Local LLM request timed out",
    "Local LLM HTTP error",
    "Local LLM JSON parsing failed",
}

pytestmark = [
    pytest.mark.local_llm_integration,
    pytest.mark.skipif(
        not RUN_LOCAL_LLM,
        reason="set NURILAB_RUN_LOCAL_LLM=1 to call an existing vLLM server",
    ),
]


@pytest.mark.parametrize(
    ("fixture_name", "expected_risk_level", "expected_call"),
    [
        ("clean_baseline_sample.py", "low", None),
        ("dynamic_execution_sample.py", "high", "eval"),
    ],
)
def test_real_vllm_review_and_report_generation(
    fixture_name: str,
    expected_risk_level: str,
    expected_call: str | None,
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    target = FIXTURES / fixture_name
    client = LocalLLMReviewClient(model=DEFAULT_LLM_MODEL)
    pipeline = Phase1Pipeline(review_client=client, use_ruff=False)

    record_property("model", client.model)
    record_property("base_url", client.base_url)
    record_property("fixture", fixture_name)

    report, output_paths = pipeline.run(
        input_path=target,
        output_dir=tmp_path / target.stem,
        formats=["html", "json"],
    )

    assert isinstance(report, AnalysisReport)
    assert report.analysis.path == str(target.resolve())
    assert report.analysis.skipped is False
    assert report.analysis.syntax_error is None
    if expected_call is None:
        assert report.analysis.suspicious_calls == []
    else:
        assert expected_call in {
            finding.name for finding in report.analysis.suspicious_calls
        }

    _assert_successful_structured_review(
        report.review,
        expected_risk_level=expected_risk_level,
        expect_findings=expected_call is not None,
    )
    _assert_persisted_reports(report, output_paths)


def test_real_vllm_web_folder_review(
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    """Run the web LLM path end to end and record what the demo measures."""

    files = [
        (
            "files",
            (
                path.relative_to(WEB_PROJECT.parent).as_posix(),
                path.read_bytes(),
                "application/octet-stream",
            ),
        )
        for path in sorted(WEB_PROJECT.rglob("*"))
        if path.is_file()
    ]
    data_dir = tmp_path / "data"

    with TestClient(create_app(WebSettings(data_dir=data_dir))) as client:
        status = client.get("/api/llm-status").json()
        # Recorded before each check so a failed run still says where it stopped.
        record_property("model", status["model"])
        record_property("llm_status", status["status"])
        assert status["status"] == "connected", status

        started = time.monotonic()
        job: dict[str, Any] = {"status": "not_created"}
        try:
            response = client.post(
                "/api/analyses", files=files, data={"review_mode": "local"}
            )
            assert response.status_code == 202, response.json()
            job_id = response.json()["id"]
            # One review request, so its timeout plus a margin; the timeout
            # bounds each wait, not the whole request (WEB_MVP_DESIGN.md §9).
            deadline = started + LocalLLMReviewClient().timeout + WEB_JOB_MARGIN_SECONDS
            while True:
                job = client.get(f"/api/analyses/{job_id}").json()
                if job["status"] in ("completed", "failed"):
                    break
                assert time.monotonic() < deadline, f"job {job_id} did not finish"
                time.sleep(0.5)
        finally:
            record_property("elapsed_seconds", round(time.monotonic() - started, 2))
            record_property("job_status", job["status"])
        # A failed job has no report, so its error is what the run must show.
        assert job["status"] == "completed", job
        report = client.get(f"/api/analyses/{job_id}/report.json").json()
        result = client.get(f"/api/analyses/{job_id}/result").json()

    record_property("file_count", job["file_count"])
    record_property("static_risk_level", job["static_risk_level"])
    record_property("review_risk_level", job["risk_level"])
    record_property("review_finding_count", len(report["review"]["findings"]))
    record_property("llm_input_truncation", result["llm_input_truncation"])
    # Recorded, not asserted: an LLM may cut the server path it was sent, which
    # path relativizing cannot catch (WEB_MVP_DESIGN.md §9). The shallowest
    # ancestor below a top folder such as /tmp also catches a shorter cut, and
    # every longer path contains it.
    server_root = Path(*data_dir.resolve().parts[:3])
    record_property(
        "server_path_in_report",
        str(server_root) in json.dumps(report, ensure_ascii=False),
    )

    assert job["review"] == {
        "client": "local",
        "model": status["model"],
        "status": "ok",
        "failure_code": None,
    }
    assert result["review_failure_message"] is None
    assert report["review"]["summary"].strip()
    assert all(
        finding["source"] == "local_llm" for finding in report["review"]["findings"]
    )
    # The LLM only reviews: the static analysis matches a Mock run.
    mock_report = Phase1Pipeline(
        review_client=MockReviewClient(), use_ruff=False
    ).analyze(WEB_PROJECT)
    mock_report = relativize_report(mock_report, WEB_PROJECT.parent, "")
    assert report["analysis"] == mock_report.to_dict()["analysis"]


def _assert_successful_structured_review(
    review: ReviewResult,
    *,
    expected_risk_level: str,
    expect_findings: bool,
) -> None:
    assert review.summary.strip()
    assert review.risk_level == expected_risk_level
    assert not {
        finding.title
        for finding in review.findings
        if finding.title in LOCAL_LLM_FAILURE_TITLES
    }

    if expect_findings:
        assert review.findings
        assert any(finding.severity == "high" for finding in review.findings)
    else:
        assert review.findings == []

    for finding in review.findings:
        assert finding.title.strip()
        assert finding.severity in {"low", "medium", "high"}
        assert finding.file is None or isinstance(finding.file, str)
        assert finding.line is None or isinstance(finding.line, int)
        assert finding.reason.strip()
        assert finding.recommendation.strip()
        assert finding.source == "local_llm"


def _assert_persisted_reports(
    report: AnalysisReport,
    output_paths: dict[str, Path],
) -> None:
    assert set(output_paths) == {"html", "json"}
    html = output_paths["html"].read_text(encoding="utf-8")
    payload: dict[str, Any] = json.loads(
        output_paths["json"].read_text(encoding="utf-8")
    )

    assert "Python Code Review Report" in html
    assert "Local LLM JSON parsing failed" not in html
    assert payload["analysis"] == report.analysis.to_dict()
    assert payload["review"] == report.review.to_dict()
