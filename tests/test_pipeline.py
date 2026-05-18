from __future__ import annotations

from pathlib import Path

from project_nurilab.pipeline import Phase1Pipeline


FIXTURES = Path(__file__).parent / "fixtures"


def test_phase1_pipeline_generates_reports(tmp_path: Path) -> None:
    report, markdown_path, json_path = Phase1Pipeline().run(
        input_path=FIXTURES / "clean_sample.py",
        output_dir=tmp_path,
    )

    assert report.analysis.path.endswith("clean_sample.py")
    assert report.review.risk_level == "low"
    assert markdown_path.name == "clean_sample.analysis.md"
    assert json_path.name == "clean_sample.analysis.json"
    assert markdown_path.exists()
    assert json_path.exists()
