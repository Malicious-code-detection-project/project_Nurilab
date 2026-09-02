from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import requests

from project_nurilab.analyzers.python_static import PythonStaticAnalyzer
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.analyzers.tools import RuffToolCollector
from project_nurilab.config import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
)
from project_nurilab.llm.review import LocalLLMReviewClient
from project_nurilab.schemas import PythonAnalysis


FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class CompletedProcessStub:
    stdout: str
    returncode: int = 0
    stderr: str = ""


def test_ruff_tool_collector_parses_json(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcessStub:
        assert kwargs["check"] is False
        return CompletedProcessStub(
            stdout=(
                '[{"filename":"sample.py","code":"F401","message":"unused import",'
                '"location":{"row":1,"column":1}}]'
            ),
            returncode=1,
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = RuffToolCollector(command_prefix=()).collect(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "F401"
    assert findings[0].message == "unused import"


def test_ruff_tool_collector_returns_empty_list_for_empty_stdout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcessStub:
        return CompletedProcessStub(stdout="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = RuffToolCollector(command_prefix=()).collect(tmp_path)

    assert findings == []


def test_ruff_tool_collector_reports_nonzero_command_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcessStub:
        return CompletedProcessStub(
            stdout="", returncode=2, stderr="ruff configuration is invalid"
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = RuffToolCollector(command_prefix=()).collect(tmp_path)

    assert len(findings) == 1
    assert findings[0].file == str(tmp_path.resolve())
    assert findings[0].rule_id == "RUFF_COMMAND_FAILED"
    assert findings[0].severity == "medium"
    assert str(tmp_path.resolve()) in findings[0].message
    assert "exit code 2" in findings[0].message
    assert "ruff configuration is invalid" in findings[0].message


def test_ruff_tool_collector_reports_subprocess_os_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcessStub:
        raise OSError("ruff executable not found")

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = RuffToolCollector(command_prefix=()).collect(tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "RUFF_COMMAND_FAILED"
    assert findings[0].severity == "medium"
    assert "exit code unavailable" in findings[0].message
    assert "ruff executable not found" in findings[0].message


def test_ruff_tool_collector_reports_json_parse_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> CompletedProcessStub:
        return CompletedProcessStub(stdout="not-json", returncode=2)

    monkeypatch.setattr("subprocess.run", fake_run)

    findings = RuffToolCollector(command_prefix=()).collect(tmp_path)

    assert len(findings) == 1
    assert findings[0].file == str(tmp_path.resolve())
    assert findings[0].line == 1
    assert findings[0].column == 1
    assert findings[0].rule_id == "RUFF_PARSE_ERROR"
    assert findings[0].message == "not-json"
    assert findings[0].severity == "medium"


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


def test_local_llm_review_client_parses_fixture_based_review(monkeypatch) -> None:
    import json

    loaded = PythonFileLoader().load(
        FIXTURES / "review_quality" / "dynamic_execution_sample.py"
    )
    analysis = PythonStaticAnalyzer().analyze(loaded)
    sent_prompt = ""

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Dynamic execution signal found.",
                                    "risk_level": "high",
                                    "findings": [
                                        {
                                            "title": "Dynamic execution via eval",
                                            "severity": "high",
                                            "file": None,
                                            "line": 2,
                                            "reason": (
                                                "The static signal identifies eval "
                                                "executing a supplied expression."
                                            ),
                                            "recommendation": (
                                                "Avoid eval for untrusted input."
                                            ),
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        nonlocal sent_prompt
        sent_prompt = kwargs["json"]["messages"][1]["content"]
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(analysis)

    assert "eval" in sent_prompt
    assert review.summary == "Dynamic execution signal found."
    assert review.risk_level == "high"
    assert len(review.findings) == 1
    assert review.findings[0].title == "Dynamic execution via eval"
    assert review.findings[0].file == analysis.path


def test_local_llm_prompt_for_large_file_uses_normalized_analysis_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import json

    sentinel = "NURILAB_LARGE_SOURCE_SENTINEL_DO_NOT_SEND"
    target_file = tmp_path / "large_risky.py"
    source_lines = [
        "import os",
        *(f'SOURCE_LINE_{index} = "{sentinel}_{index}"' for index in range(205)),
        'API_KEY = "demo_key_value_not_real"',
        "",
        "def run(command):",
        "    return os.system(command)",
    ]
    target_file.write_text("\n".join(source_lines), encoding="utf-8")

    loaded = PythonFileLoader().load(target_file)
    analysis = PythonStaticAnalyzer().analyze(loaded)
    sent_prompt = ""

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Large file static signals reviewed.",
                                    "risk_level": "high",
                                    "findings": [],
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        nonlocal sent_prompt
        sent_prompt = kwargs["json"]["messages"][1]["content"]
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(analysis)

    assert analysis.line_count > 200
    assert [call.name for call in analysis.suspicious_calls] == ["os.system"]
    assert [secret.kind for secret in analysis.secrets] == ["api_key"]
    assert review.summary == "Large file static signals reviewed."
    assert review.risk_level == "high"

    assert str(target_file.resolve()) in sent_prompt
    assert f'"line_count": {analysis.line_count}' in sent_prompt
    assert '"suspicious_calls"' in sent_prompt
    assert '"name": "os.system"' in sent_prompt
    assert '"secrets"' in sent_prompt
    assert '"kind": "api_key"' in sent_prompt
    assert sentinel not in sent_prompt
    assert "SOURCE_LINE_204" not in sent_prompt
    assert "demo_key_value_not_real" not in sent_prompt


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
                                '  "summary": "Found a high-risk signal.",\n'
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
    assert review.summary == "Found a high-risk signal."


@pytest.mark.parametrize(
    ("content", "expected_error"),
    [
        (
            '{"risk_level":"low","findings":[]}',
            "review missing required field(s): summary",
        ),
        (
            '{"summary":"ok","findings":[]}',
            "review missing required field(s): risk_level",
        ),
        (
            '{"summary":"ok","risk_level":"low"}',
            "review missing required field(s): findings",
        ),
        (
            '{"summary":"ok","risk_level":"low","findings":[],"extra":true}',
            "review unexpected field(s): extra",
        ),
        (
            '{"summary":{},"risk_level":"low","findings":[]}',
            "review.summary must be a string",
        ),
        (
            '{"summary":"ok","risk_level":"critical","findings":[]}',
            "review.risk_level must be one of: low, medium, high",
        ),
        (
            '{"summary":"ok","risk_level":"low","findings":{}}',
            "review.findings must be an array",
        ),
        (
            '{"summary":"ok","risk_level":"low","findings":["invalid"]}',
            "review.findings[0] must be an object",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"high","file":null,"line":1,'
                '"reason":"reason"}]}'
            ),
            "review.findings[0] missing required field(s): recommendation",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"high","file":null,"line":"1",'
                '"reason":"reason","recommendation":"fix"}]}'
            ),
            "review.findings[0].line must be an integer or null",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":1,"severity":"high","file":null,"line":1,'
                '"reason":"reason","recommendation":"fix"}]}'
            ),
            "review.findings[0].title must be a string",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"critical","file":null,"line":1,'
                '"reason":"reason","recommendation":"fix"}]}'
            ),
            "review.findings[0].severity must be one of: low, medium, high",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"high","file":1,"line":1,'
                '"reason":"reason","recommendation":"fix"}]}'
            ),
            "review.findings[0].file must be a string or null",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"high","file":null,"line":1,'
                '"reason":null,"recommendation":"fix"}]}'
            ),
            "review.findings[0].reason must be a string",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"high","file":null,"line":1,'
                '"reason":"reason","recommendation":null}]}'
            ),
            "review.findings[0].recommendation must be a string",
        ),
        (
            (
                '{"summary":"ok","risk_level":"high","findings":['
                '{"title":"Finding","severity":"high","file":null,"line":1,'
                '"reason":"reason","recommendation":"fix","extra":true}]}'
            ),
            "review.findings[0] unexpected field(s): extra",
        ),
    ],
)
def test_local_llm_review_client_rejects_schema_violations(
    monkeypatch,
    content: str,
    expected_error: str,
) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": content}}]}

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert review.risk_level == "unknown"
    assert len(review.findings) == 1
    finding = review.findings[0]
    assert finding.title == "Local LLM JSON parsing failed"
    assert finding.source == "local_llm"
    assert expected_error in finding.reason


@pytest.mark.parametrize(
    ("content", "json_type"),
    [
        ("[]", "array"),
        (
            '[{"summary":"ok","risk_level":"low","findings":[]}]',
            "array",
        ),
        ('"not a review object"', "string"),
        ("42", "number"),
        ("null", "null"),
    ],
)
def test_local_llm_review_client_rejects_non_object_json(
    monkeypatch,
    content: str,
    json_type: str,
) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": content}}]}

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert review.risk_level == "unknown"
    assert len(review.findings) == 1
    finding = review.findings[0]
    assert finding.title == "Local LLM JSON parsing failed"
    assert finding.source == "local_llm"
    assert f"top level must be an object, got {json_type}" in finding.reason


def test_extract_json_payload() -> None:
    from project_nurilab.llm.review import _extract_json_payload

    # 1. Clean JSON
    assert _extract_json_payload('{"foo": "bar"}') == '{"foo": "bar"}'

    # 2. Fenced JSON (plain ``` markdown fences)
    assert _extract_json_payload('```\n{"foo": "bar"}\n```') == '{"foo": "bar"}'

    # 3. Fenced JSON (with ```json markdown fences)
    assert _extract_json_payload('```json\n{"foo": "bar"}\n```') == '{"foo": "bar"}'

    # 4. JSON with preamble
    assert (
        _extract_json_payload('Here is the json content:\n{"foo": "bar"}')
        == '{"foo": "bar"}'
    )

    # 5. Fenced JSON with preamble
    assert (
        _extract_json_payload('Response:\n```json\n{"foo": "bar"}\n```')
        == '{"foo": "bar"}'
    )

    # 6. Invalid JSON (no braces)
    assert _extract_json_payload("no json content") == "no json content"

    # 7. Partial/invalid JSON (missing closing brace)
    assert _extract_json_payload('{"foo": "bar"') == '{"foo": "bar"'


@pytest.mark.parametrize(
    ("request_error", "expected_reason"),
    [
        (
            requests.exceptions.ConnectionError("Connection refused"),
            "Connection refused",
        ),
        (
            requests.exceptions.InvalidURL("No host supplied"),
            "No host supplied",
        ),
        (
            requests.exceptions.ConnectionError(
                "Name or service not known for host local-llm.invalid"
            ),
            "local-llm.invalid",
        ),
    ],
)
def test_local_llm_review_client_connection_failures_become_findings(
    monkeypatch,
    request_error: requests.exceptions.RequestException,
    expected_reason: str,
) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> None:
        raise request_error

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(
        base_url="http://localhost:8000/v1",
        model="test-model",
    ).review(PythonAnalysis(path="sample.py", line_count=10))

    assert (
        review.summary
        == "Local LLM review failed. Static analysis results are still available."
    )
    assert review.risk_level == "unknown"
    assert len(review.findings) == 1

    finding = review.findings[0]
    assert finding.title == "Local LLM connection failed"
    assert finding.source == "local_llm"
    assert "http://localhost:8000/v1/chat/completions" in finding.reason
    assert "test-model" in finding.reason
    assert expected_reason in finding.reason
    assert "Static analysis results are still included" in finding.reason
    assert "NURILAB_LLM_BASE_URL" in finding.recommendation
    assert "model name" in finding.recommendation


def test_local_llm_review_client_timeout_becomes_finding(monkeypatch) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> None:
        raise requests.exceptions.Timeout("model response exceeded timeout")

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(
        base_url="http://localhost:8000/v1",
        model="test-model",
        timeout=3.5,
    ).review(PythonAnalysis(path="sample.py", line_count=10))

    assert (
        review.summary
        == "Local LLM review failed. Static analysis results are still available."
    )
    assert review.risk_level == "unknown"
    assert len(review.findings) == 1

    finding = review.findings[0]
    assert finding.title == "Local LLM request timed out"
    assert finding.source == "local_llm"
    assert "3.5 second(s)" in finding.reason
    assert "http://localhost:8000/v1/chat/completions" in finding.reason
    assert "test-model" in finding.reason
    assert "model response exceeded timeout" in finding.reason
    assert "Static analysis results are still included" in finding.reason
    assert "NURILAB_LLM_TIMEOUT" in finding.recommendation
    assert "model name" in finding.recommendation


@pytest.mark.parametrize(
    ("status_code", "error_message", "response_body"),
    [
        (400, "400 Client Error: Bad Request", "bad request body"),
        (404, "404 Client Error: Not Found", "model route not found"),
        (500, "500 Server Error: Internal Server Error", "server overloaded"),
    ],
)
def test_local_llm_review_client_http_errors_become_findings(
    monkeypatch,
    status_code: int,
    error_message: str,
    response_body: str,
) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            response = requests.Response()
            response.status_code = status_code
            response._content = response_body.encode("utf-8")
            raise requests.exceptions.HTTPError(error_message, response=response)

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(
        base_url="http://localhost:8000/v1",
        model="test-model",
    ).review(PythonAnalysis(path="sample.py", line_count=10))

    assert (
        review.summary
        == "Local LLM review failed. Static analysis results are still available."
    )
    assert review.risk_level == "unknown"
    assert len(review.findings) == 1

    finding = review.findings[0]
    assert finding.title == "Local LLM HTTP error"
    assert finding.source == "local_llm"
    assert "http://localhost:8000/v1/chat/completions" in finding.reason
    assert "test-model" in finding.reason
    assert str(status_code) in finding.reason
    assert error_message in finding.reason
    assert response_body in finding.reason
    assert "Static analysis results are still included" in finding.reason
    assert "base URL" in finding.recommendation
    assert "model name" in finding.recommendation
    assert "vLLM server logs" in finding.recommendation


def test_local_llm_review_client_uses_default_connection_settings(
    monkeypatch,
) -> None:
    sent_request: dict[str, Any] = {}

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

    def fake_post(url: str, **kwargs: Any) -> ResponseStub:
        sent_request["url"] = url
        sent_request["json"] = kwargs["json"]
        sent_request["timeout"] = kwargs["timeout"]
        return ResponseStub()

    monkeypatch.delenv("NURILAB_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NURILAB_LLM_MODEL", raising=False)
    monkeypatch.delenv("NURILAB_LLM_TIMEOUT", raising=False)
    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient().review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert sent_request["url"] == f"{DEFAULT_LLM_BASE_URL}/chat/completions"
    request_payload = sent_request["json"]
    assert request_payload["model"] == DEFAULT_LLM_MODEL
    assert request_payload["model"] == "openai/gpt-oss-20b"
    assert request_payload["reasoning_effort"] == "low"
    assert "include_reasoning" not in request_payload
    response_format = request_payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "nurilab_security_review"
    assert response_format["json_schema"]["strict"] is True
    response_schema = response_format["json_schema"]["schema"]
    assert response_schema["type"] == "object"
    assert response_schema["additionalProperties"] is False
    assert response_schema["required"] == ["summary", "risk_level", "findings"]
    assert response_schema["properties"]["risk_level"]["enum"] == [
        "low",
        "medium",
        "high",
    ]
    finding_schema = response_schema["properties"]["findings"]["items"]
    assert finding_schema["additionalProperties"] is False
    assert finding_schema["properties"]["severity"]["enum"] == [
        "low",
        "medium",
        "high",
    ]
    assert finding_schema["properties"]["file"]["type"] == ["string", "null"]
    assert finding_schema["properties"]["line"]["type"] == ["integer", "null"]
    assert finding_schema["required"] == [
        "title",
        "severity",
        "file",
        "line",
        "reason",
        "recommendation",
    ]
    system_prompt = request_payload["messages"][0]["content"]
    user_prompt = request_payload["messages"][1]["content"]
    assert "final JSON object" in system_prompt
    assert "Chain of Thought" not in user_prompt
    assert "reasoning trace" in user_prompt
    assert sent_request["timeout"] == DEFAULT_LLM_TIMEOUT_SECONDS
    assert review.risk_level == "low"


def test_local_llm_review_client_uses_environment_connection_settings(
    monkeypatch,
) -> None:
    sent_request: dict[str, Any] = {}

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

    def fake_post(url: str, **kwargs: Any) -> ResponseStub:
        sent_request["url"] = url
        sent_request["json"] = kwargs["json"]
        sent_request["timeout"] = kwargs["timeout"]
        return ResponseStub()

    monkeypatch.setenv("NURILAB_LLM_BASE_URL", "http://127.0.0.1:9000/v1/")
    monkeypatch.setenv("NURILAB_LLM_MODEL", "custom-local-model")
    monkeypatch.setenv("NURILAB_LLM_TIMEOUT", "9.5")
    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient().review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert sent_request["url"] == "http://127.0.0.1:9000/v1/chat/completions"
    assert sent_request["json"]["model"] == "custom-local-model"
    assert sent_request["timeout"] == 9.5
    assert review.risk_level == "low"


def test_local_llm_review_client_uses_timeout_environment_variable(
    monkeypatch,
) -> None:
    sent_timeout = None

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
        nonlocal sent_timeout
        sent_timeout = kwargs["timeout"]
        return ResponseStub()

    monkeypatch.setenv("NURILAB_LLM_TIMEOUT", "7.25")
    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert sent_timeout == 7.25
    assert review.risk_level == "low"


def test_local_llm_review_client_explicit_timeout_overrides_environment(
    monkeypatch,
) -> None:
    sent_timeout = None

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
        nonlocal sent_timeout
        sent_timeout = kwargs["timeout"]
        return ResponseStub()

    monkeypatch.setenv("NURILAB_LLM_TIMEOUT", "7.25")
    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(
        base_url="http://localhost:8000/v1",
        timeout=2.0,
    ).review(PythonAnalysis(path="sample.py", line_count=10))

    assert sent_timeout == 2.0
    assert review.risk_level == "low"


def test_local_llm_review_client_rejects_invalid_timeout_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NURILAB_LLM_TIMEOUT", "not-a-number")

    with pytest.raises(
        ValueError,
        match="NURILAB_LLM_TIMEOUT must be a numeric timeout in seconds",
    ):
        LocalLLMReviewClient(base_url="http://localhost:8000/v1")


def test_local_llm_review_client_parsing_error(monkeypatch) -> None:
    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": ("invalid-json")}}]}

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(
        PythonAnalysis(path="sample.py", line_count=10)
    )

    assert (
        review.summary
        == "Local LLM review failed. Static analysis results are still available."
    )
    assert review.risk_level == "unknown"
    assert len(review.findings) == 1

    finding = review.findings[0]
    assert finding.title == "Local LLM JSON parsing failed"
    assert finding.source == "local_llm"
    assert "Failed to parse LLM response as JSON." in finding.reason
    assert "Raw response preview:" in finding.reason
    assert "invalid-json" in finding.reason
    assert "Static analysis results are still included" in finding.reason
    assert (
        "returning only JSON with summary, risk_level, and findings"
        in finding.recommendation
    )


def test_build_llm_prompt_summarizes_project(tmp_path: Path) -> None:
    from project_nurilab.llm.review import _build_llm_prompt
    from project_nurilab.schemas import (
        ProjectAnalysis,
        ProjectSummary,
        PythonAnalysis,
        RuffFinding,
        SuspiciousCall,
        SecretFinding,
    )

    project_dir = tmp_path / "target_project"
    file1 = project_dir / "safe.py"
    file2 = project_dir / "subdir" / "risky.py"
    file3 = project_dir / "ignored.py"

    analysis = ProjectAnalysis(
        root_path=str(project_dir),
        file_results=[
            PythonAnalysis(
                path=str(file1),
                line_count=5,
                imports=[],
                classes=[],
                functions=[],
                suspicious_calls=[],
                secrets=[],
            ),
            PythonAnalysis(
                path=str(file2),
                line_count=20,
                suspicious_calls=[
                    SuspiciousCall(
                        name="eval",
                        line=10,
                        category="dynamic_execution",
                        severity="high",
                        reason="calls eval",
                    )
                ],
                secrets=[
                    SecretFinding(
                        kind="api_key",
                        line=15,
                        preview="sk-...",
                        severity="high",
                        reason="hardcoded api key",
                    )
                ],
            ),
            PythonAnalysis(
                path=str(file3),
                line_count=0,
                skipped=True,
                skip_reason="exceeds limit",
            ),
        ],
        ruff_findings=[
            RuffFinding(
                file=str(file2),
                line=12,
                column=5,
                rule_id="F401",
                message="unused import",
                severity="low",
            )
        ],
        summary=ProjectSummary(
            total_files=3,
            analyzed_files=2,
            skipped_files=1,
            severity_counts={"high": 2, "low": 1},
            risk_level="high",
        ),
    )

    prompt = _build_llm_prompt(analysis)

    # Verify prompt contains clean summary payload
    assert "target_project" in prompt
    assert '"total_files": 3' in prompt
    assert '"analyzed_files": 2' in prompt
    assert '"skipped_files": 1' in prompt
    assert '"risk_level": "high"' in prompt

    # Verify we excluded the safe file (safe.py) from file_analyses because it has no signals
    assert "safe.py" not in prompt

    # Verify file2 is present and has suspicious_calls, secrets, and ruff findings
    assert "risky.py" in prompt
    assert "eval" in prompt
    assert "api_key" in prompt
    assert "F401" in prompt
    assert "unused import" in prompt

    # Verify skipped file (ignored.py) is present and has skip reason
    assert "ignored.py" in prompt
    assert "exceeds limit" in prompt


def test_local_llm_review_client_resolves_project_finding_paths(
    tmp_path: Path, monkeypatch
) -> None:
    import json
    from project_nurilab.schemas import (
        ProjectAnalysis,
        ProjectSummary,
        PythonAnalysis,
    )
    from project_nurilab.llm.review import LocalLLMReviewClient

    project_dir = (tmp_path / "target_project").resolve()

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "found issues",
                                    "risk_level": "high",
                                    "findings": [
                                        {
                                            "title": "Dynamic execution",
                                            "severity": "high",
                                            "file": "subdir/risky.py",
                                            "line": 10,
                                            "reason": "uses eval",
                                            "recommendation": "do not use eval",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(*args: Any, **kwargs: Any) -> ResponseStub:
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    analysis = ProjectAnalysis(
        root_path=str(project_dir),
        file_results=[
            PythonAnalysis(
                path=str(project_dir / "subdir" / "risky.py"),
                line_count=20,
            )
        ],
        summary=ProjectSummary(
            total_files=1,
            analyzed_files=1,
            skipped_files=0,
            risk_level="high",
        ),
    )

    review = LocalLLMReviewClient(base_url="http://localhost:8000/v1").review(analysis)

    assert review.summary == "found issues"
    assert review.risk_level == "high"
    assert len(review.findings) == 1

    # The relative path "subdir/risky.py" should be resolved to absolute path
    expected_absolute_path = str((project_dir / "subdir" / "risky.py").resolve())
    assert review.findings[0].file == expected_absolute_path


def test_signal_sort_key_priority() -> None:
    from project_nurilab.llm.review import _signal_sort_key

    # 1. Severity descending: critical < high < medium < low < info < unknown
    k_crit = _signal_sort_key("critical", "pattern", "a.py", 10, "eval")
    k_high = _signal_sort_key("high", "pattern", "a.py", 10, "eval")
    k_med = _signal_sort_key("medium", "pattern", "a.py", 10, "eval")
    k_low = _signal_sort_key("low", "pattern", "a.py", 10, "eval")
    k_info = _signal_sort_key("info", "pattern", "a.py", 10, "eval")
    k_unk = _signal_sort_key("unknown", "pattern", "a.py", 10, "eval")

    assert k_crit < k_high < k_med < k_low < k_info < k_unk

    # 2. Source kind tie-break
    k_ast = _signal_sort_key("high", "ast", "a.py", 10, "eval")
    k_pat = _signal_sort_key("high", "pattern", "a.py", 10, "eval")
    k_ruff = _signal_sort_key("high", "ruff", "a.py", 10, "eval")
    k_sec = _signal_sort_key("high", "secret", "a.py", 10, "eval")

    assert k_ast < k_pat < k_ruff < k_sec

    # 3. Relative path tie-break
    k_path_a = _signal_sort_key("high", "pattern", "a.py", 10, "eval")
    k_path_b = _signal_sort_key("high", "pattern", "b.py", 10, "eval")

    assert k_path_a < k_path_b

    # 4. Line tie-break (None is treated as 0)
    k_line_none = _signal_sort_key("high", "pattern", "a.py", None, "eval")
    k_line_5 = _signal_sort_key("high", "pattern", "a.py", 5, "eval")
    k_line_10 = _signal_sort_key("high", "pattern", "a.py", 10, "eval")

    assert k_line_none < k_line_5 < k_line_10

    # 5. Stable rule/name tie-break
    k_name_a = _signal_sort_key("high", "pattern", "a.py", 10, "call_a")
    k_name_b = _signal_sort_key("high", "pattern", "a.py", 10, "call_b")

    assert k_name_a < k_name_b


def test_payload_summary_deterministic_ordering(tmp_path: Path) -> None:
    from project_nurilab.llm.review import (
        _build_file_payload_summary,
        _build_project_payload_summary,
    )
    from project_nurilab.schemas import (
        ProjectAnalysis,
        ProjectSummary,
        PythonAnalysis,
        RuffFinding,
        SecretFinding,
        SuspiciousCall,
    )

    root = tmp_path / "project"
    file_med = root / "med.py"
    file_high = root / "high.py"
    file_low = root / "low.py"

    res_med = PythonAnalysis(
        path=str(file_med),
        line_count=50,
        suspicious_calls=[
            SuspiciousCall(
                name="exec",
                line=20,
                category="dynamic_execution",
                severity="medium",
                reason="med issue",
            )
        ],
    )
    res_high = PythonAnalysis(
        path=str(file_high),
        line_count=100,
        suspicious_calls=[
            SuspiciousCall(
                name="os.system",
                line=30,
                category="command_execution",
                severity="high",
                reason="high issue 2",
            ),
            SuspiciousCall(
                name="eval",
                line=10,
                category="dynamic_execution",
                severity="high",
                reason="high issue 1",
            ),
        ],
        secrets=[
            SecretFinding(
                kind="token",
                line=5,
                preview="tok_...",
                severity="high",
                reason="hardcoded token",
            ),
            SecretFinding(
                kind="api_key",
                line=2,
                preview="sk_...",
                severity="high",
                reason="hardcoded key",
            ),
        ],
    )
    res_low = PythonAnalysis(
        path=str(file_low),
        line_count=10,
        syntax_error=None,
    )
    ruff_low = [
        RuffFinding(
            file=str(file_low),
            line=5,
            column=1,
            rule_id="F401",
            message="unused import",
            severity="low",
        )
    ]

    summary = ProjectSummary(
        total_files=3,
        analyzed_files=3,
        skipped_files=0,
        severity_counts={"high": 4, "medium": 1, "low": 1},
        risk_level="high",
    )

    # Order 1: med, high, low
    proj1 = ProjectAnalysis(
        root_path=str(root),
        file_results=[res_med, res_high, res_low],
        ruff_findings=ruff_low,
        summary=summary,
    )
    # Order 2: low, high, med (shuffled)
    proj2 = ProjectAnalysis(
        root_path=str(root),
        file_results=[res_low, res_high, res_med],
        ruff_findings=ruff_low,
        summary=summary,
    )

    payload1 = _build_project_payload_summary(proj1)
    payload2 = _build_project_payload_summary(proj2)

    # Output must be 100% identical regardless of input collection order
    assert payload1 == payload2

    # Files must be ordered by top severity: high.py -> med.py -> low.py
    file_order = [fa["file"] for fa in payload1["file_analyses"]]
    assert file_order == ["high.py", "med.py", "low.py"]

    # Inside high.py:
    high_analysis = payload1["file_analyses"][0]
    # Suspicious calls sorted: eval (line 10) before os.system (line 30)
    assert [c["name"] for c in high_analysis["suspicious_calls"]] == [
        "eval",
        "os.system",
    ]
    # Secrets sorted: api_key (line 2) before token (line 5)
    assert [s["kind"] for s in high_analysis["secrets"]] == ["api_key", "token"]

    # Also verify single file payload summary sorts signals
    file_payload = _build_file_payload_summary(res_high)
    assert [c["name"] for c in file_payload["suspicious_calls"]] == [
        "eval",
        "os.system",
    ]
    assert [s["kind"] for s in file_payload["secrets"]] == ["api_key", "token"]


def test_calculate_json_bytes_utf8() -> None:
    from project_nurilab.llm.review import _calculate_json_bytes

    payload = {"message": "정적 분석 결과", "count": 42}
    expected_bytes = len(
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    )
    assert _calculate_json_bytes(payload) == expected_bytes
    # Ensure Korean characters are counted as 3 UTF-8 bytes each
    assert "정적 분석 결과".encode("utf-8") == bytes("정적 분석 결과", encoding="utf-8")


def test_resolve_budget_bytes(monkeypatch) -> None:
    from project_nurilab.config import DEFAULT_LLM_INPUT_BUDGET_BYTES
    from project_nurilab.llm.review import _resolve_budget_bytes

    assert DEFAULT_LLM_INPUT_BUDGET_BYTES == 64 * 1024
    assert _resolve_budget_bytes(None) == 65536
    assert _resolve_budget_bytes(2048) == 2048

    with pytest.raises(ValueError, match="positive integer"):
        _resolve_budget_bytes(0)
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_budget_bytes(-10)

    monkeypatch.setenv("NURILAB_LLM_INPUT_BUDGET_BYTES", "32768")
    assert _resolve_budget_bytes(None) == 32768

    monkeypatch.setenv("NURILAB_LLM_INPUT_BUDGET_BYTES", "invalid")
    with pytest.raises(ValueError, match="positive integer"):
        _resolve_budget_bytes(None)


def test_project_payload_budget_truncation_atomic_signals(tmp_path: Path) -> None:
    from project_nurilab.llm.review import (
        _build_project_payload_summary,
        _calculate_json_bytes,
    )
    from project_nurilab.schemas import (
        ProjectAnalysis,
        ProjectSummary,
        PythonAnalysis,
        SecretFinding,
        SuspiciousCall,
    )

    root = tmp_path / "budget_proj"
    # Create 3 files with multiple signals each
    files = []
    for i in range(5):
        p = root / f"file_{i}.py"
        files.append(
            PythonAnalysis(
                path=str(p),
                line_count=100,
                suspicious_calls=[
                    SuspiciousCall(
                        name=f"call_{j}",
                        line=j * 10,
                        category="dynamic_execution",
                        severity="high" if j == 0 else "medium",
                        reason=f"Detailed reason for call_{j} with enough text to consume byte budget.",
                    )
                    for j in range(5)
                ],
                secrets=[
                    SecretFinding(
                        kind="api_key",
                        line=50,
                        preview="sk-...",
                        severity="high",
                        reason="Hardcoded key with descriptive explanation.",
                    )
                ],
            )
        )

    analysis = ProjectAnalysis(
        root_path=str(root),
        file_results=files,
        summary=ProjectSummary(
            total_files=5,
            analyzed_files=5,
            skipped_files=0,
            severity_counts={"high": 10, "medium": 20},
            risk_level="high",
        ),
    )

    # 1. Without budget constraint, entire project fits
    full_payload = _build_project_payload_summary(analysis, budget_bytes=100_000)
    assert "truncation" not in full_payload
    assert len(full_payload["file_analyses"]) == 5

    # 2. With small budget constraint: budget = 1800 bytes
    budget = 1800
    payload1 = _build_project_payload_summary(analysis, budget_bytes=budget)
    payload2 = _build_project_payload_summary(analysis, budget_bytes=budget)

    # Byte-identical output for identical analysis
    json_bytes1 = json.dumps(payload1, ensure_ascii=False, indent=2).encode("utf-8")
    json_bytes2 = json.dumps(payload2, ensure_ascii=False, indent=2).encode("utf-8")
    assert json_bytes1 == json_bytes2

    # Payload byte size strictly within budget
    assert _calculate_json_bytes(payload1) <= budget
    assert len(json_bytes1) <= budget

    # Truncation tracking
    assert "truncation" in payload1
    trunc = payload1["truncation"]
    assert trunc["truncated"] is True
    assert trunc["budget_bytes"] == budget
    assert trunc["before_bytes"] > budget
    assert trunc["sent_bytes"] <= budget
    assert trunc["included_count"] < 30
    assert trunc["omitted_count"] > 0
    assert trunc["included_count"] + trunc["omitted_count"] == 30

    # No signal cut in the middle: every included signal has all fields intact
    for fa in payload1["file_analyses"]:
        for call in fa.get("suspicious_calls", []):
            assert set(call.keys()) == {
                "name",
                "line",
                "category",
                "severity",
                "reason",
            }
            assert isinstance(call["name"], str)
            assert isinstance(call["reason"], str)
            assert not call["reason"].endswith("...")  # not sliced midway
        for secret in fa.get("secrets", []):
            assert set(secret.keys()) == {
                "kind",
                "line",
                "preview",
                "severity",
                "reason",
            }


def test_file_payload_budget_truncation_atomic_signals() -> None:
    from project_nurilab.llm.review import (
        _build_file_payload_summary,
        _calculate_json_bytes,
    )
    from project_nurilab.schemas import PythonAnalysis, SuspiciousCall

    # File with 20 suspicious calls
    calls = [
        SuspiciousCall(
            name=f"call_{i}",
            line=i * 5,
            category="command_execution",
            severity="high" if i < 3 else "low",
            reason=f"Explanation for suspicious call {i} in this file.",
        )
        for i in range(20)
    ]
    analysis = PythonAnalysis(
        path="single_sample.py",
        line_count=200,
        suspicious_calls=calls,
    )

    budget = 800
    payload1 = _build_file_payload_summary(analysis, budget_bytes=budget)
    payload2 = _build_file_payload_summary(analysis, budget_bytes=budget)

    # Byte-identical output
    assert json.dumps(payload1, ensure_ascii=False, indent=2).encode(
        "utf-8"
    ) == json.dumps(payload2, ensure_ascii=False, indent=2).encode("utf-8")
    # Within budget
    assert _calculate_json_bytes(payload1) <= budget
    assert "truncation" in payload1
    trunc = payload1["truncation"]
    assert trunc["truncated"] is True
    assert trunc["budget_bytes"] == budget
    assert trunc["before_bytes"] > budget
    assert trunc["sent_bytes"] <= budget
    assert trunc["included_count"] < 20
    assert trunc["omitted_count"] > 0
    assert trunc["included_count"] + trunc["omitted_count"] == 20

    # High severity calls prioritized
    included_calls = payload1["suspicious_calls"]
    assert len(included_calls) > 0
    # First calls must be high severity
    assert included_calls[0]["severity"] == "high"
    # Complete fields (no signal cut in the middle)
    for c in included_calls:
        assert set(c.keys()) == {"name", "line", "category", "severity", "reason"}


def test_local_llm_request_failure_preserves_input_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    from project_nurilab.llm.review import LocalLLMReviewClient
    from project_nurilab.schemas import ProjectAnalysis, PythonAnalysis, SuspiciousCall

    analysis = ProjectAnalysis(
        root_path=str(tmp_path),
        file_results=[
            PythonAnalysis(
                path=str(tmp_path / f"file_{i}.py"),
                line_count=50,
                suspicious_calls=[
                    SuspiciousCall(
                        name="eval",
                        line=10,
                        category="dynamic_execution",
                        severity="high",
                        reason="Dynamic execution of untrusted input",
                    )
                ],
            )
            for i in range(10)
        ],
    )

    # Small budget so truncation triggers
    client = LocalLLMReviewClient(
        base_url="http://127.0.0.1:9999",
        budget_bytes=500,
    )

    # Calling review on unreachable server should fail but preserve metadata
    review = client.review(analysis)
    assert review.risk_level == "unknown"
    assert review.findings[0].title == "Local LLM connection failed"
    assert review.input_metadata is not None
    assert review.input_metadata["truncated"] is True
    assert review.input_metadata["budget_bytes"] == 500
    assert "before_bytes" in review.input_metadata
    assert "sent_bytes" in review.input_metadata
    assert "included_count" in review.input_metadata
    assert "omitted_count" in review.input_metadata
    assert review.input_metadata["sent_bytes"] <= 500

    # Check serialization to dict
    review_dict = review.to_dict()
    assert "input_metadata" in review_dict
    assert review_dict["input_metadata"]["truncated"] is True


def test_report_generator_renders_input_metadata_views(tmp_path: Path) -> None:
    from datetime import datetime, timezone
    from project_nurilab import __version__
    from project_nurilab.reports.generator import ReportGenerator
    from project_nurilab.schemas import (
        ProjectAnalysis,
        ProjectReport,
        ProjectSummary,
        PythonAnalysis,
        ReviewFinding,
        ReviewResult,
        SuspiciousCall,
    )

    proj_analysis = ProjectAnalysis(
        root_path=str(tmp_path),
        file_results=[
            PythonAnalysis(
                path=str(tmp_path / "app.py"),
                line_count=20,
                suspicious_calls=[
                    SuspiciousCall(
                        name="exec",
                        line=5,
                        category="dynamic_execution",
                        severity="high",
                        reason="Arbitrary execution",
                    )
                ],
            )
        ],
        summary=ProjectSummary(
            total_files=1,
            analyzed_files=1,
            skipped_files=0,
            severity_counts={"high": 1},
            risk_level="high",
        ),
    )

    review_with_truncation = ReviewResult(
        summary="Security review with budget truncation.",
        risk_level="high",
        findings=[
            ReviewFinding(
                title="Dynamic execution via exec",
                severity="high",
                file=str(tmp_path / "app.py"),
                line=5,
                reason="Dynamic code execution detected.",
                recommendation="Avoid exec.",
            )
        ],
        input_metadata={
            "budget_bytes": 1024,
            "before_bytes": 2048,
            "sent_bytes": 950,
            "included_count": 1,
            "omitted_count": 3,
            "truncated": True,
        },
    )

    report = ProjectReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        analyzer_version=__version__,
        analysis=proj_analysis,
        review=review_with_truncation,
    )

    generator = ReportGenerator()
    out = generator.write(report, tmp_path, formats=["json", "html", "md"])

    # 1. JSON representation
    json_text = out["json"].read_text(encoding="utf-8")
    json_data = json.loads(json_text)
    assert json_data["review"]["input_metadata"] == {
        "budget_bytes": 1024,
        "before_bytes": 2048,
        "sent_bytes": 950,
        "included_count": 1,
        "omitted_count": 3,
        "truncated": True,
    }

    # 2. HTML representation
    html_text = out["html"].read_text(encoding="utf-8")
    assert "LLM Input Truncation" in html_text
    assert "1,024 bytes" in html_text
    assert "2,048 bytes" in html_text
    assert "950 bytes" in html_text

    # 3. Markdown representation
    md_text = out["md"].read_text(encoding="utf-8")
    assert "## LLM Input Truncation" in md_text
    assert "- Budget Limit: `1,024 bytes`" in md_text
    assert "- Before Truncation: `2,048 bytes`" in md_text
    assert "- Sent Payload: `950 bytes`" in md_text
    assert "- Signals Included: `1`" in md_text
    assert "- Signals Omitted: `3`" in md_text
    assert "- Truncated: `True`" in md_text


def test_local_llm_review_success_records_input_metadata(monkeypatch) -> None:
    from project_nurilab.llm.review import LocalLLMReviewClient
    from project_nurilab.schemas import PythonAnalysis, SuspiciousCall

    class ResponseStub:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Review summary from LLM",
                                    "risk_level": "medium",
                                    "findings": [],
                                }
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: ResponseStub())

    calls = [
        SuspiciousCall(
            name=f"call_{i}",
            line=i * 5,
            category="command_execution",
            severity="medium",
            reason=f"Suspicious call {i}",
        )
        for i in range(20)
    ]
    analysis = PythonAnalysis(
        path="app.py",
        line_count=100,
        suspicious_calls=calls,
    )

    client = LocalLLMReviewClient(base_url="http://localhost:8000/v1", budget_bytes=600)
    review = client.review(analysis)

    assert review.summary == "Review summary from LLM"
    assert review.risk_level == "medium"
    assert review.input_metadata is not None
    assert review.input_metadata["truncated"] is True
    assert review.input_metadata["budget_bytes"] == 600
    assert review.input_metadata["before_bytes"] > 600
    assert review.input_metadata["sent_bytes"] <= 600
    assert review.input_metadata["included_count"] < 20
    assert review.input_metadata["omitted_count"] > 0
