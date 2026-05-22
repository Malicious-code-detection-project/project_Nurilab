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
