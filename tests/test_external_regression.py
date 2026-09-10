import json
import os
import subprocess
from pathlib import Path

import pytest

from project_nurilab.pipeline import Phase1Pipeline

TARGETS_JSON = (
    Path(__file__).parent / "fixtures" / "external_regression" / "targets.json"
)

EXTERNAL_REGRESSION_ROOT = os.getenv("NURILAB_EXTERNAL_REGRESSION_ROOT")

pytestmark = [
    pytest.mark.skipif(
        not EXTERNAL_REGRESSION_ROOT,
        reason="set NURILAB_EXTERNAL_REGRESSION_ROOT to run external regression tests",
    ),
]


def normalize_report(report: dict, root_path: str) -> dict:
    """Remove volatile fields and normalize absolute paths to <ROOT>."""
    report.pop("generated_at", None)

    report_str = json.dumps(report)

    root_posix = Path(root_path).resolve().as_posix()
    report_str = report_str.replace(root_posix, "<ROOT>")

    return json.loads(report_str)


@pytest.fixture(scope="session")
def external_targets() -> dict[str, str]:
    if not TARGETS_JSON.exists():
        pytest.skip(f"{TARGETS_JSON} not found")
    return json.loads(TARGETS_JSON.read_text(encoding="utf-8"))


@pytest.mark.parametrize("use_ruff", [False, True])
def test_external_regression_pinned_targets(
    use_ruff: bool,
    tmp_path: Path,
    external_targets: dict[str, str],
) -> None:
    assert EXTERNAL_REGRESSION_ROOT is not None
    root_path = Path(EXTERNAL_REGRESSION_ROOT).resolve()

    # Scope 3: Verify all targets exist and match the expected commit hash
    for repo_name, expected_sha in external_targets.items():
        repo_path = root_path / repo_name
        if not repo_path.exists() or not repo_path.is_dir():
            pytest.fail(f"Target repository {repo_name} not found at {repo_path}")

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            actual_sha = result.stdout.strip()
            if actual_sha != expected_sha:
                pytest.fail(
                    f"Repository {repo_name} is at {actual_sha}, expected {expected_sha}. "
                    "Please checkout the correct commit."
                )
        except subprocess.CalledProcessError as e:
            pytest.fail(f"Failed to check git commit for {repo_name}: {e}")

    # Scope 1 and 4: Run pipeline on each target and ensure HTML/JSON are generated in tmp_path
    for repo_name in external_targets.keys():
        repo_path = root_path / repo_name

        pipeline = Phase1Pipeline(use_ruff=use_ruff)

        report, output_paths = pipeline.run(
            input_path=repo_path,
            output_dir=tmp_path,
            formats=["html", "json"],
        )

        assert "html" in output_paths
        assert "json" in output_paths
        assert output_paths["html"].exists()
        assert output_paths["json"].exists()

        # Scope 2: Deterministic assertion without volatile fields
        actual_json = json.loads(output_paths["json"].read_text(encoding="utf-8"))
        normalized_actual = normalize_report(actual_json, str(root_path))

        ruff_suffix = "ruff" if use_ruff else "no_ruff"
        expected_file = (
            Path(__file__).parent
            / "fixtures"
            / "external_regression"
            / f"{repo_name}_{ruff_suffix}_expected.json"
        )

        if not expected_file.exists():
            expected_file.write_text(
                json.dumps(normalized_actual, indent=2), encoding="utf-8"
            )
            pytest.fail(
                f"Baseline {expected_file.name} generated. Please re-run to verify."
            )

        expected_json = json.loads(expected_file.read_text(encoding="utf-8"))
        assert normalized_actual == expected_json
