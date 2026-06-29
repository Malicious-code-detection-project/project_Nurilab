from __future__ import annotations

from pathlib import Path

from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.schemas import AnalysisReport, ProjectReport


FIXTURES = Path(__file__).parent / "fixtures"


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
    from typing import Any
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
