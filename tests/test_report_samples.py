from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


SAMPLES = Path(__file__).parent / "fixtures" / "report_samples" / "the85"
FAILURE_SAMPLES = SAMPLES / "json-parsing-failure"
ABSOLUTE_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|/home/)")


@pytest.mark.parametrize(
    ("sample_name", "expected_path", "expected_suspicious_calls"),
    [
        (
            "clean",
            "tests/fixtures/review_quality/clean_baseline_sample.py",
            [],
        ),
        (
            "dynamic",
            "tests/fixtures/review_quality/dynamic_execution_sample.py",
            ["eval"],
        ),
    ],
)
def test_the85_json_parsing_failure_samples_preserve_static_analysis(
    sample_name: str,
    expected_path: str,
    expected_suspicious_calls: list[str],
) -> None:
    json_path = FAILURE_SAMPLES / f"{sample_name}.analysis.json"
    html_path = FAILURE_SAMPLES / f"{sample_name}.analysis.html"

    json_text = json_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    payload = json.loads(json_text)
    finding = payload["review"]["findings"][0]

    assert payload["analysis"]["path"] == expected_path
    assert [
        call["name"] for call in payload["analysis"]["suspicious_calls"]
    ] == expected_suspicious_calls
    assert payload["review"]["risk_level"] == "unknown"
    assert finding["title"] == "Local LLM JSON parsing failed"
    assert finding["source"] == "local_llm"
    assert "Static analysis results are still included" in finding["reason"]

    assert expected_path in html
    assert finding["title"] in html
    assert "<strong>Source:</strong> local_llm" in html
    assert not ABSOLUTE_PATH_PATTERN.search(json_text)
    assert not ABSOLUTE_PATH_PATTERN.search(html)
