from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_nurilab.analyzers.tools import RuffToolCollector
from project_nurilab.llm.review import LocalLLMReviewClient
from project_nurilab.schemas import PythonAnalysis


@dataclass
class CompletedProcessStub:
    stdout: str


def test_ruff_tool_collector_parses_json(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcessStub:
        return CompletedProcessStub(
            stdout=(
                '[{"filename":"sample.py","code":"F401","message":"unused import",'
                '"location":{"row":1,"column":1}}]'
            )
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = RuffToolCollector(command_prefix=()).collect(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "F401"
    assert findings[0].message == "unused import"


def test_local_llm_review_client_parses_vllm_response(monkeypatch) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"ok","risk_level":"low","findings":[]}'
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=1)
    )

    assert review.summary == "ok"
    assert review.risk_level == "low"


def test_local_llm_review_client_parses_fenced_json_response(monkeypatch) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "```json\n"
                                "{\n"
                                '  "summary": {\n'
                                '    "total_files": 2,\n'
                                '    "risk_level": "high"\n'
                                "  },\n"
                                '  "risk_level": "high",\n'
                                '  "findings": [\n'
                                "    {\n"
                                '      "title": "Dynamic Execution Risk",\n'
                                '      "severity": "high",\n'
                                '      "file": "sample.py",\n'
                                '      "line": 10,\n'
                                '      "reason": "os.system executes shell commands.",\n'
                                '      "recommendation": "Avoid passing untrusted input."\n'
                                "    }\n"
                                "  ]\n"
                                "}\n"
                                "```"
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert review.risk_level == "high"
    assert review.findings[0].title == "Dynamic Execution Risk"
    assert '"total_files": 2' in review.summary


def test_local_llm_review_client_normalizes_severity_and_handles_missing_fields(
    monkeypatch,
) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "{\n"
                                '  "summary": "Summary of analysis",\n'
                                '  "risk_level": "INVALID_RISK",\n'
                                '  "findings": [\n'
                                "    {\n"
                                '      "title": "Finding 1",\n'
                                '      "severity": "CRITICAL",\n'
                                '      "line": "15",\n'
                                '      "reason": "Reason 1"\n'
                                "    },\n"
                                "    {\n"
                                '      "title": "",\n'
                                '      "severity": "invalid-severity-value",\n'
                                '      "line": "not-an-int",\n'
                                '      "reason": null,\n'
                                '      "recommendation": "Rec 2"\n'
                                "    },\n"
                                '    "not-a-dict-finding"\n'
                                "  ]\n"
                                "}"
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    # Findings that are not dicts (like "not-a-dict-finding") should be ignored.
    assert len(review.findings) == 2

    # Finding 1 assertions
    f1 = review.findings[0]
    assert f1.title == "Finding 1"
    assert f1.severity == "critical"  # CRITICAL normalized to critical
    assert f1.line == 15  # "15" string parsed as 15 int
    assert f1.reason == "Reason 1"
    assert f1.recommendation == ""  # Missing recommendation defaults to empty string

    # Finding 2 assertions
    f2 = review.findings[1]
    assert f2.title == "LLM finding"  # Empty title defaults to LLM finding
    assert f2.severity == "unknown"  # Invalid severity normalized to unknown
    assert f2.line is None  # Invalid line string fallback to None
    assert f2.reason == ""  # Null reason defaults to empty string
    assert f2.recommendation == "Rec 2"

    # Risk level fallback
    # Since "INVALID_RISK" is not low, medium, or high, it should derive from findings
    # findings has "critical" severity, so risk_level should derive to "high"
    assert review.risk_level == "high"


def test_local_llm_review_client_handles_non_dict_payload(monkeypatch) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '[{"some_key": "some_val"}]'  # JSON list instead of JSON dict
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    # Should not crash and should return safe defaults
    assert review.summary == ""
    assert review.risk_level == "low"
    assert len(review.findings) == 0
