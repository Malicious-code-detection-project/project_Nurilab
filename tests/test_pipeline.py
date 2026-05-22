from __future__ import annotations

from pathlib import Path

from project_nurilab.pipeline import Phase1Pipeline


FIXTURES = Path(__file__).parent / "fixtures"


def test_phase1_pipeline_generates_reports(tmp_path: Path) -> None:
    report, output_paths = Phase1Pipeline().run(
        input_path=FIXTURES / "clean_sample.py",
        output_dir=tmp_path,
        formats=["html", "json"],
    )

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
    (target_project / "safe.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (target_project / "risky.py").write_text(
        "import os\n\n\ndef run(x):\n    os.system(x)\n",
        encoding="utf-8",
    )
    (target_project / ".venv").mkdir()
    (target_project / ".venv" / "ignored.py").write_text("eval('1')\n", encoding="utf-8")

    report, output_paths = Phase1Pipeline(use_ruff=False).run(
        input_path=target_project,
        output_dir=tmp_path,
    )

    assert report.analysis.root_path == str(target_project.resolve())
    assert report.analysis.summary is not None
    assert report.analysis.summary.total_files == 2
    assert report.analysis.summary.analyzed_files == 2
    assert report.review.risk_level == "high"
    assert output_paths["html"].name == "target_project.analysis.html"
    assert output_paths["json"].name == "target_project.analysis.json"
