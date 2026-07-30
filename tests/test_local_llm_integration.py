from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from project_nurilab.config import DEFAULT_LLM_MODEL
from project_nurilab.llm.review import LocalLLMReviewClient
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.schemas import AnalysisReport, ReviewResult


FIXTURES = Path(__file__).parent / "fixtures" / "review_quality"
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
