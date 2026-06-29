from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.schemas import AnalysisReport, ProjectReport, RuffFinding


FIXTURES = Path(__file__).parent / "fixtures"
MIXED_RISK_PROJECT = FIXTURES / "mixed_risk_project"


def _copy_mixed_risk_project_fixture(tmp_path: Path) -> Path:
    target_project = tmp_path / "mixed_risk_project"
    target_project.mkdir()
    for source_file in MIXED_RISK_PROJECT.glob("*.py"):
        (target_project / source_file.name).write_text(
            source_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (target_project / "syntax_error.py").write_text(
        (MIXED_RISK_PROJECT / "syntax_error_source.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return target_project


def _write_large_risky_python_file(path: Path) -> int:
    source_lines = [
        "import os",
        *("value = 1" for _ in range(205)),
        "",
        "def run(command):",
        "    return os.system(command)",
    ]
    path.write_text("\n".join(source_lines), encoding="utf-8")
    return len(source_lines)


def test_phase1_pipeline_generates_reports(tmp_path: Path) -> None:
    report, output_paths = Phase1Pipeline().run(
        input_path=FIXTURES / "clean_sample.py",
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, AnalysisReport)
    assert report.analysis.path.endswith("clean_sample.py")
    assert report.review.risk_level == "low"
    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].name == "clean_sample.analysis.html"
    assert output_paths["json"].name == "clean_sample.analysis.json"
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()


def test_pipeline_generates_reports_for_large_python_file(tmp_path: Path) -> None:
    target_file = tmp_path / "large_risky.py"
    suspicious_line = _write_large_risky_python_file(target_file)
    output_dir = tmp_path / "reports"

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_file,
        output_dir=output_dir,
        formats=["html", "json"],
    )

    assert isinstance(report, AnalysisReport)
    assert report.analysis.skipped is False
    assert report.analysis.skip_reason is None
    assert report.analysis.line_count > 200
    assert [call.name for call in report.analysis.suspicious_calls] == ["os.system"]
    assert report.analysis.suspicious_calls[0].line == suspicious_line
    assert report.review.risk_level == "high"
    assert report.review.findings[0].title == "Review suspicious call: os.system"
    assert report.review.findings[0].line == suspicious_line

    assert output_paths["html"].name == "large_risky.analysis.html"
    assert output_paths["json"].name == "large_risky.analysis.json"
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["skipped"] is False
    assert payload["analysis"]["line_count"] > 200
    assert payload["analysis"]["suspicious_calls"][0]["name"] == "os.system"
    assert payload["analysis"]["suspicious_calls"][0]["line"] == suspicious_line
    assert payload["review"]["findings"][0]["title"] == (
        "Review suspicious call: os.system"
    )
    assert payload["review"]["findings"][0]["line"] == suspicious_line


def test_pipeline_generates_project_reports(tmp_path: Path) -> None:
    target_project = tmp_path / "target_project"
    target_project.mkdir()
    (target_project / "safe.py").write_text(
        "def ok():\n    return 1\n", encoding="utf-8"
    )
    (target_project / "risky.py").write_text(
        "import os\n\n\ndef run(x):\n    os.system(x)\n",
        encoding="utf-8",
    )
    (target_project / ".venv").mkdir()
    (target_project / ".venv" / "ignored.py").write_text(
        "eval('1')\n", encoding="utf-8"
    )

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.root_path == str(target_project.resolve())
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 2
    assert report.analysis.summary.analyzed_files == 2
    assert report.review.risk_level == "high"
    assert output_paths["html"].name == "target_project.analysis.html"
    assert output_paths["json"].name == "target_project.analysis.json"


def test_pipeline_generates_project_reports_with_large_python_file(
    tmp_path: Path,
) -> None:
    target_project = tmp_path / "large_project"
    target_project.mkdir()
    large_file = target_project / "large_risky.py"
    suspicious_line = _write_large_risky_python_file(large_file)
    (target_project / "safe.py").write_text(
        "def ok():\n    return 1\n",
        encoding="utf-8",
    )

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 2
    assert report.analysis.summary.analyzed_files == 2
    assert report.analysis.summary.skipped_files == 0
    assert report.review.risk_level == "high"

    large_results = [
        result
        for result in report.analysis.file_results
        if result.path == str(large_file.resolve())
    ]
    assert len(large_results) == 1
    assert large_results[0].skipped is False
    assert large_results[0].line_count > 200
    assert large_results[0].suspicious_calls[0].name == "os.system"
    assert large_results[0].suspicious_calls[0].line == suspicious_line

    matching_findings = [
        finding
        for finding in report.review.findings
        if finding.title == "Review suspicious call: os.system"
    ]
    assert len(matching_findings) == 1
    assert matching_findings[0].file == str(large_file.resolve())
    assert matching_findings[0].line == suspicious_line

    assert output_paths["html"].name == "large_project.analysis.html"
    assert output_paths["json"].name == "large_project.analysis.json"
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["summary"]["total_files"] == 2
    assert payload["analysis"]["summary"]["analyzed_files"] == 2
    assert payload["analysis"]["summary"]["skipped_files"] == 0
    json_large_results = [
        result
        for result in payload["analysis"]["file_results"]
        if result["path"] == str(large_file.resolve())
    ]
    assert len(json_large_results) == 1
    assert json_large_results[0]["skipped"] is False
    assert json_large_results[0]["line_count"] > 200
    assert json_large_results[0]["suspicious_calls"][0]["name"] == "os.system"
    assert json_large_results[0]["suspicious_calls"][0]["line"] == suspicious_line


def test_pipeline_includes_project_ruff_findings_in_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target_project"
    target_project.mkdir()
    target_file = target_project / "risky.py"
    target_file.write_text(
        "import os\n\n\ndef run(x):\n    os.system(x)\n",
        encoding="utf-8",
    )

    def fake_collect(self: Any, target: str | Path) -> list[RuffFinding]:
        assert Path(target) == target_project.resolve()
        return [
            RuffFinding(
                file=str(target_file.resolve()),
                line=1,
                column=1,
                rule_id="F401",
                message="unused import",
                severity="medium",
            )
        ]

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fake_collect,
    )

    report, output_paths = Phase1Pipeline().run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert len(report.analysis.ruff_findings) == 1
    assert report.analysis.ruff_findings[0].rule_id == "F401"
    assert report.analysis.summary is not None
    assert report.analysis.summary.severity_counts["medium"] == 1

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["ruff_findings"] == [
        {
            "file": str(target_file.resolve()),
            "line": 1,
            "column": 1,
            "rule_id": "F401",
            "message": "unused import",
            "severity": "medium",
            "source": "ruff",
        }
    ]


def test_pipeline_project_summary_aggregates_all_signal_severities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "summary_project"
    target_project.mkdir()
    command_file = target_project / "command.py"
    network_file = target_project / "network.py"
    secret_file = target_project / "secret.py"
    syntax_file = target_project / "syntax_error.py"
    invalid_file = target_project / "invalid_utf8.py"

    command_file.write_text(
        "import os\n\n\ndef run(command):\n    return os.system(command)\n",
        encoding="utf-8",
    )
    network_file.write_text(
        "import requests\n\n\ndef fetch(url):\n    return requests.get(url)\n",
        encoding="utf-8",
    )
    secret_file.write_text(
        'API_KEY = "demo_key_value_not_real"\n',
        encoding="utf-8",
    )
    syntax_file.write_text(
        "def broken(:\n    return None\n",
        encoding="utf-8",
    )
    invalid_file.write_bytes(b"\xff\xfe\x00")

    def fake_collect(self: Any, target: str | Path) -> list[RuffFinding]:
        assert Path(target) == target_project.resolve()
        return [
            RuffFinding(
                file=str(network_file.resolve()),
                line=1,
                column=1,
                rule_id="F401",
                message="unused import",
                severity="medium",
            ),
            RuffFinding(
                file=str(secret_file.resolve()),
                line=1,
                column=1,
                rule_id="F841",
                message="assigned but unused",
                severity="low",
            ),
        ]

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fake_collect,
    )

    report, output_paths = Phase1Pipeline().run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 5
    assert report.analysis.summary.analyzed_files == 4
    assert report.analysis.summary.skipped_files == 1
    assert report.analysis.summary.severity_counts == {
        "high": 2,
        "low": 2,
        "medium": 2,
    }
    assert report.analysis.summary.risk_level == "high"

    skipped_results = [
        result for result in report.analysis.file_results if result.skipped
    ]
    assert len(skipped_results) == 1
    assert skipped_results[0].path == str(invalid_file.resolve())

    syntax_results = [
        result for result in report.analysis.file_results if result.syntax_error
    ]
    assert len(syntax_results) == 1
    assert syntax_results[0].path == str(syntax_file.resolve())

    file_summaries = report.analysis.summary.file_summaries
    assert [summary.path for summary in file_summaries] == [
        "secret.py",
        "command.py",
        "network.py",
        "syntax_error.py",
        "invalid_utf8.py",
    ]
    assert file_summaries[0].risk_level == "high"
    assert file_summaries[0].finding_count == 2
    assert file_summaries[0].secret_count == 1
    assert file_summaries[0].ruff_finding_count == 1
    assert file_summaries[1].suspicious_call_count == 1
    assert file_summaries[2].risk_level == "medium"
    assert file_summaries[2].suspicious_call_count == 1
    assert file_summaries[2].ruff_finding_count == 1
    assert file_summaries[3].syntax_error is True
    assert file_summaries[4].risk_level == "unknown"
    assert file_summaries[4].skipped is True

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["summary"]["total_files"] == 5
    assert payload["analysis"]["summary"]["analyzed_files"] == 4
    assert payload["analysis"]["summary"]["skipped_files"] == 1
    assert payload["analysis"]["summary"]["severity_counts"] == {
        "high": 2,
        "low": 2,
        "medium": 2,
    }
    assert payload["analysis"]["summary"]["risk_level"] == "high"
    assert payload["analysis"]["summary"]["file_summaries"][0] == {
        "path": "secret.py",
        "risk_level": "high",
        "finding_count": 2,
        "suspicious_call_count": 0,
        "secret_count": 1,
        "syntax_error": False,
        "ruff_finding_count": 1,
        "skipped": False,
    }


def test_pipeline_generates_report_from_mixed_risk_project_fixture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = _copy_mixed_risk_project_fixture(tmp_path)
    clean_file = target_project / "mixed_clean.py"

    def fake_collect(self: Any, target: str | Path) -> list[RuffFinding]:
        assert Path(target) == target_project.resolve()
        return [
            RuffFinding(
                file=str(clean_file.resolve()),
                line=1,
                column=1,
                rule_id="F401",
                message="unused import",
                severity="low",
            )
        ]

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fake_collect,
    )

    report, output_paths = Phase1Pipeline().run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 4
    assert report.analysis.summary.analyzed_files == 4
    assert report.analysis.summary.skipped_files == 0
    assert report.analysis.summary.severity_counts == {
        "high": 2,
        "medium": 1,
        "low": 1,
    }
    assert report.analysis.summary.risk_level == "high"

    assert [summary.path for summary in report.analysis.summary.file_summaries] == [
        "hardcoded_secret.py",
        "suspicious_call.py",
        "syntax_error.py",
        "mixed_clean.py",
    ]
    file_summaries = {
        summary.path: summary for summary in report.analysis.summary.file_summaries
    }
    assert file_summaries["hardcoded_secret.py"].secret_count == 1
    assert file_summaries["suspicious_call.py"].suspicious_call_count == 1
    assert file_summaries["syntax_error.py"].syntax_error is True
    assert file_summaries["mixed_clean.py"].ruff_finding_count == 1

    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["summary"]["severity_counts"] == {
        "high": 2,
        "medium": 1,
        "low": 1,
    }
    assert payload["analysis"]["ruff_findings"] == [
        {
            "file": str(clean_file.resolve()),
            "line": 1,
            "column": 1,
            "rule_id": "F401",
            "message": "unused import",
            "severity": "low",
            "source": "ruff",
        }
    ]
    assert {
        Path(result["path"]).name for result in payload["analysis"]["file_results"]
    } == {
        "hardcoded_secret.py",
        "mixed_clean.py",
        "suspicious_call.py",
        "syntax_error.py",
    }
    assert any(
        result["syntax_error"]
        for result in payload["analysis"]["file_results"]
        if Path(result["path"]).name == "syntax_error.py"
    )


def test_pipeline_disables_project_ruff_collection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target_project"
    target_project.mkdir()
    (target_project / "safe.py").write_text(
        "def ok():\n    return 1\n",
        encoding="utf-8",
    )

    def fail_if_ruff_runs(*args: Any, **kwargs: Any) -> list[RuffFinding]:
        raise AssertionError("use_ruff=False should disable Ruff collection")

    monkeypatch.setattr(
        "project_nurilab.analyzers.tools.RuffToolCollector.collect",
        fail_if_ruff_runs,
    )

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.ruff_findings == []

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["analysis"]["ruff_findings"] == []


def test_pipeline_keeps_running_when_project_file_decode_fails(
    tmp_path: Path,
) -> None:
    target_project = tmp_path / "target_project"
    target_project.mkdir()
    safe_file = target_project / "safe.py"
    invalid_file = target_project / "invalid_utf8.py"
    safe_file.write_text("def ok():\n    return 1\n", encoding="utf-8")
    invalid_file.write_bytes(b"\xff\xfe\x00")

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 2
    assert report.analysis.summary.analyzed_files == 1
    assert report.analysis.summary.skipped_files == 1

    skipped_results = [
        result for result in report.analysis.file_results if result.skipped
    ]
    assert len(skipped_results) == 1
    assert skipped_results[0].path == str(invalid_file.resolve())
    assert skipped_results[0].line_count == 0
    assert skipped_results[0].skip_reason is not None
    assert "UTF-8 decode failed" in skipped_results[0].skip_reason

    analyzed_paths = {
        result.path for result in report.analysis.file_results if not result.skipped
    }
    assert analyzed_paths == {str(safe_file.resolve())}

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    skipped_payloads = [
        result for result in payload["analysis"]["file_results"] if result["skipped"]
    ]
    assert len(skipped_payloads) == 1
    assert skipped_payloads[0]["path"] == str(invalid_file.resolve())
    assert "UTF-8 decode failed" in skipped_payloads[0]["skip_reason"]


def test_pipeline_keeps_running_when_project_file_read_raises_os_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_project = tmp_path / "target_project"
    target_project.mkdir()
    safe_file = target_project / "safe.py"
    unreadable_file = target_project / "unreadable.py"
    safe_file.write_text("def ok():\n    return 1\n", encoding="utf-8")
    unreadable_file.write_text("def blocked():\n    return 2\n", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == unreadable_file.resolve():
            raise PermissionError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 2
    assert report.analysis.summary.analyzed_files == 1
    assert report.analysis.summary.skipped_files == 1

    skipped_results = [
        result for result in report.analysis.file_results if result.skipped
    ]
    assert len(skipped_results) == 1
    assert skipped_results[0].path == str(unreadable_file.resolve())
    assert skipped_results[0].skip_reason is not None
    assert "Permission denied" in skipped_results[0].skip_reason

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    skipped_payloads = [
        result for result in payload["analysis"]["file_results"] if result["skipped"]
    ]
    assert len(skipped_payloads) == 1
    assert skipped_payloads[0]["path"] == str(unreadable_file.resolve())
    assert "Permission denied" in skipped_payloads[0]["skip_reason"]


def test_pipeline_reviews_mixed_risk_project_fixture(tmp_path: Path) -> None:
    source_project = FIXTURES / "review_quality_project"
    target_project = tmp_path / "review_quality_project"
    target_project.mkdir()

    for source_file in source_project.glob("*.py"):
        (target_project / source_file.name).write_text(
            source_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    (target_project / "syntax_error.py").write_text(
        (source_project / "syntax_error_source.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 5
    assert report.analysis.summary.analyzed_files == 5
    assert report.review.risk_level == "high"

    titles = {finding.title for finding in report.review.findings}
    assert "Review suspicious call: exec" in titles
    assert "Review suspicious call: requests.post" in titles
    assert "Potential hard-coded secret: token" in titles
    assert "Python syntax error" in titles

    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()


def test_pipeline_analyzes_nested_project_inputs_and_generates_reports(
    tmp_path: Path,
) -> None:
    target_project = tmp_path / "nested_project"
    included_sources = {
        "src/sample_app/__init__.py": "",
        "src/sample_app/main.py": (
            "from sample_app.services.worker import run_worker\n\n"
            "def main():\n"
            "    return run_worker()\n"
        ),
        "src/sample_app/services/worker.py": (
            "import requests\n\n"
            "def run_worker():\n"
            "    return requests.post('https://example.invalid/api')\n"
        ),
        "scripts/admin.py": (
            "import os\n\ndef run_admin(command):\n    return os.system(command)\n"
        ),
    }
    for relative_path, source in included_sources.items():
        path = target_project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    excluded_sources = [
        ".venv/ignored.py",
        ".git/hooks/ignored.py",
        "__pycache__/ignored.py",
        "reports/generated.py",
        "build/generated.py",
    ]
    for relative_path in excluded_sources:
        path = target_project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("eval('ignored')\n", encoding="utf-8")

    (target_project / "README.md").write_text("# nested project\n", encoding="utf-8")

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, ProjectReport)
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 4
    assert report.analysis.summary.analyzed_files == 4
    assert report.analysis.summary.skipped_files == 0
    assert report.review.risk_level == "high"

    analyzed_paths = {
        Path(result.path).relative_to(target_project).as_posix()
        for result in report.analysis.file_results
    }
    assert analyzed_paths == set(included_sources)

    finding_titles = {finding.title for finding in report.review.findings}
    assert "Review suspicious call: os.system" in finding_titles
    assert "Review suspicious call: requests.post" in finding_titles

    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].name == "nested_project.analysis.html"
    assert output_paths["json"].name == "nested_project.analysis.json"
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()


def test_pipeline_with_local_llm_for_project(tmp_path: Path, monkeypatch) -> None:
    import json
    from project_nurilab.llm.review import LocalLLMReviewClient

    target_project = tmp_path / "target_project"
    target_project.mkdir()
    (target_project / "safe.py").write_text(
        "def ok():\n    return 1\n", encoding="utf-8"
    )
    (target_project / "risky.py").write_text(
        "import os\n\n\ndef run(x):\n    os.system(x)\n",
        encoding="utf-8",
    )

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
                                    "summary": "Found high severity issue with dynamic execution.",
                                    "risk_level": "high",
                                    "findings": [
                                        {
                                            "title": "Dynamic execution via os.system",
                                            "severity": "high",
                                            "file": "risky.py",
                                            "line": 5,
                                            "reason": "os.system executes arbitrary shell commands.",
                                            "recommendation": "Use subprocess.run with arguments as a list.",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            }

    sent_prompt = None

    def fake_post(url: str, json: dict[str, Any], **kwargs: Any) -> ResponseStub:
        nonlocal sent_prompt
        sent_prompt = json["messages"][1]["content"]
        return ResponseStub()

    monkeypatch.setattr("requests.post", fake_post)

    review_client = LocalLLMReviewClient(base_url="http://localhost:8000/v1")
    pipeline = Phase1Pipeline(use_ruff=False, review_client=review_client)

    report, output_paths = pipeline.run(
        input_path=target_project,
        output_dir=tmp_path,
    )

    assert isinstance(report, ProjectReport)
    # 1. Assertions on the generated report and findings paths
    assert report.review.risk_level == "high"
    assert len(report.review.findings) == 1

    # Path of the finding should be resolved to absolute path
    expected_absolute_path = str((target_project / "risky.py").resolve())
    assert report.review.findings[0].file == expected_absolute_path

    # 2. Assertions on the prompt sent to the LLM (verifying cleaned up summary payload)
    assert sent_prompt is not None
    assert "target_project" in sent_prompt
    assert "safe.py" not in sent_prompt
    assert "risky.py" in sent_prompt
    assert "os.system" in sent_prompt


def test_pipeline_preserves_reports_when_local_llm_connection_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import requests

    from project_nurilab.llm.review import LocalLLMReviewClient

    target_file = tmp_path / "sample.py"
    target_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    def fake_post(*args: Any, **kwargs: Any) -> None:
        raise requests.exceptions.ConnectionError("Connection refused")

    monkeypatch.setattr("requests.post", fake_post)

    report, output_paths = Phase1Pipeline(
        use_ruff=False,
        review_client=LocalLLMReviewClient(
            base_url="http://localhost:8000/v1",
            model="test-model",
        ),
    ).run(
        input_path=target_file,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, AnalysisReport)
    assert report.review.risk_level == "unknown"
    assert len(report.review.findings) == 1
    assert report.review.findings[0].source == "local_llm"
    assert report.review.findings[0].title == "Local LLM connection failed"
    assert "Connection refused" in report.review.findings[0].reason

    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["review"]["risk_level"] == "unknown"
    assert payload["review"]["findings"][0]["source"] == "local_llm"
    assert payload["review"]["findings"][0]["title"] == ("Local LLM connection failed")
    assert "Connection refused" in payload["review"]["findings"][0]["reason"]


def test_pipeline_preserves_reports_when_local_llm_times_out(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import requests

    from project_nurilab.llm.review import LocalLLMReviewClient

    target_file = tmp_path / "sample.py"
    target_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    def fake_post(*args: Any, **kwargs: Any) -> None:
        raise requests.exceptions.Timeout("model response exceeded timeout")

    monkeypatch.setattr("requests.post", fake_post)

    report, output_paths = Phase1Pipeline(
        use_ruff=False,
        review_client=LocalLLMReviewClient(
            base_url="http://localhost:8000/v1",
            model="test-model",
            timeout=3.5,
        ),
    ).run(
        input_path=target_file,
        output_dir=tmp_path,
        formats=["html", "json"],
    )

    assert isinstance(report, AnalysisReport)
    assert report.review.risk_level == "unknown"
    assert len(report.review.findings) == 1
    assert report.review.findings[0].source == "local_llm"
    assert report.review.findings[0].title == "Local LLM request timed out"
    assert "3.5 second(s)" in report.review.findings[0].reason

    assert set(output_paths) == {"html", "json"}
    assert output_paths["html"].exists()
    assert output_paths["json"].exists()

    payload = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert payload["review"]["risk_level"] == "unknown"
    assert payload["review"]["findings"][0]["source"] == "local_llm"
    assert payload["review"]["findings"][0]["title"] == "Local LLM request timed out"
    assert (
        "model response exceeded timeout" in payload["review"]["findings"][0]["reason"]
    )
