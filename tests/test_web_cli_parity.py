"""Web Mock analysis must produce the same report JSON as CLI ``--no-ruff``."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from project_nurilab.cli import main
from project_nurilab.reports.paths import replace_root
from project_nurilab.web.app import create_app
from project_nurilab.web.settings import WebSettings


FIXTURES = Path(__file__).parent / "fixtures"
UNREADABLE_SOURCE = b"\xff\xfe\x00"


def _single_file(base: Path) -> Path:
    target = base / "vulnerable_sample.py"
    shutil.copy(FIXTURES / "vulnerable_sample.py", target)
    return target


def _nested_folder(base: Path) -> Path:
    target = base / "review_quality_project"
    shutil.copytree(FIXTURES / "review_quality_project", target)
    deep = target / "pkg" / "sub"
    deep.mkdir(parents=True)
    shutil.copy(FIXTURES / "vulnerable_sample.py", deep / "deep.py")
    return target


def _mixed_folder(base: Path) -> Path:
    """Non-Python files, excluded dirs, a syntax error, and an unreadable file."""

    target = base / "mixed_risk_project"
    shutil.copytree(FIXTURES / "mixed_risk_project", target)
    (target / "broken.py").write_text(
        (target / "syntax_error_source.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (target / "README.md").write_text("# notes\n", encoding="utf-8")
    (target / "unreadable.py").write_bytes(UNREADABLE_SOURCE)
    (target / "build").mkdir()
    (target / "build" / "generated.py").write_text("eval('1')\n", encoding="utf-8")
    (target / "sub" / "__pycache__").mkdir(parents=True)
    (target / "sub" / "__pycache__" / "cached.py").write_text(
        "eval('1')\n", encoding="utf-8"
    )
    (target / "sub" / "clean.py").write_text("VALUE = 1\n", encoding="utf-8")
    return target


def _cli_report(target: Path, out: Path) -> dict[str, Any]:
    exit_code = main(
        ["analyze", str(target), "--out", str(out), "--no-ruff", "--format", "json"]
    )
    assert exit_code == 0
    [report_path] = out.glob("*.analysis.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(report, dict)
    return report


def _web_report(client: TestClient, target: Path) -> tuple[dict[str, Any], Any]:
    # Upload names as the browser sends them: the file name, or a path below
    # the folder's parent (webkitRelativePath).
    paths = [target] if target.is_file() else sorted(target.rglob("*"))
    files = [
        (
            "files",
            (
                path.relative_to(target.parent).as_posix(),
                path.read_bytes(),
                "application/octet-stream",
            ),
        )
        for path in paths
        if path.is_file()
    ]
    response = client.post("/api/analyses", files=files)
    assert response.status_code == 202, response.json()
    job_id = response.json()["id"]
    deadline = time.monotonic() + 15.0
    while (job := client.get(f"/api/analyses/{job_id}").json())["status"] not in (
        "completed",
        "failed",
    ):
        assert time.monotonic() < deadline, f"job {job_id} did not finish"
        time.sleep(0.02)
    assert job["status"] == "completed", job
    report = client.get(f"/api/analyses/{job_id}/report.json").json()
    assert isinstance(report, dict)
    return report, job


def _strip_root(value: Any, root: Path) -> Any:
    """Remove the ``root`` prefix from every string.

    The web removes its upload directory prefix the same way (``""``), so CLI
    paths below ``root`` become the upload paths the web reports.
    """

    if isinstance(value, dict):
        return {key: _strip_root(child, root) for key, child in value.items()}
    if isinstance(value, list):
        return [_strip_root(child, root) for child in value]
    if isinstance(value, str):
        return replace_root(value, root, "")
    return value


@pytest.mark.parametrize(
    "build_target",
    [_single_file, _nested_folder, _mixed_folder],
    ids=["single_file", "nested_folder", "mixed_folder"],
)
def test_web_mock_report_matches_cli_no_ruff_report(
    build_target: Callable[[Path], Path], tmp_path: Path
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    target = build_target(inputs)

    cli_report = _strip_root(_cli_report(target, tmp_path / "cli"), target.parent)
    with TestClient(create_app(WebSettings(data_dir=tmp_path / "data"))) as client:
        web_report, job = _web_report(client, target)
    # The only field that differs between runs.
    del cli_report["generated_at"]
    del web_report["generated_at"]

    assert web_report == cli_report
    # Neither side may keep a server path the comparison would otherwise hide.
    assert str(tmp_path) not in json.dumps(cli_report, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(web_report, ensure_ascii=False)
    assert job["review"]["client"] == "mock"
    assert job["risk_level"] == web_report["review"]["risk_level"]


def test_mixed_folder_parity_covers_filtered_and_unreadable_files(
    tmp_path: Path,
) -> None:
    """The mixed fixture really exercises filtering, so its match is not empty."""

    target = _mixed_folder(tmp_path)

    report = _strip_root(_cli_report(target, tmp_path / "cli"), target.parent)

    analysis = report["analysis"]
    results = {result["path"]: result for result in analysis["file_results"]}
    assert "mixed_risk_project/sub/clean.py" in results
    assert not any("build/" in path or "__pycache__" in path for path in results)
    assert not any(path.endswith((".md", ".txt")) for path in results)
    assert results["mixed_risk_project/broken.py"]["syntax_error"] is not None
    assert results["mixed_risk_project/unreadable.py"]["skipped"] is True
    assert analysis["summary"]["skipped_files"] == 1
