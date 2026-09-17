"""Opt-in regression snapshots for pinned public Python repositories."""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from project_nurilab.analyzers.tools import RuffToolCollector
from project_nurilab.llm.review import MockReviewClient
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.schemas import ProjectReport, RuffFinding


FIXTURES = Path(__file__).parent / "fixtures" / "external_regression"
TARGETS_JSON = FIXTURES / "targets.json"
SUPPORTED_TARGETS = ("packaging", "click", "requests")


def _load_targets(path: Path = TARGETS_JSON) -> dict[str, str]:
    """Load the fixed target-to-commit mapping without changing fixtures."""
    try:
        raw_targets = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"External regression manifest is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"External regression manifest is malformed: {path}") from exc

    if not isinstance(raw_targets, dict) or not raw_targets:
        raise ValueError(
            f"External regression manifest must be a non-empty object: {path}"
        )
    if set(raw_targets) != set(SUPPORTED_TARGETS):
        raise ValueError(
            "External regression manifest must contain exactly "
            f"{', '.join(SUPPORTED_TARGETS)}: {path}"
        )
    if not all(
        isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
        for sha in raw_targets.values()
    ):
        raise ValueError(
            f"External regression manifest must contain 40-character lowercase SHA pins: {path}"
        )
    return {name: raw_targets[name] for name in SUPPORTED_TARGETS}


def _baseline_path(repo_name: str, use_ruff: bool) -> Path:
    suffix = "ruff" if use_ruff else "no_ruff"
    return FIXTURES / f"{repo_name}_{suffix}_expected.json"


def _load_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        pytest.fail(
            f"External regression baseline is missing: {path}. "
            "Regenerate it through the documented maintainer workflow."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"External regression baseline is malformed: {path}: {exc}")
    if not isinstance(payload, dict):
        pytest.fail(f"External regression baseline must be a JSON object: {path}")
    return payload


def _external_root_from_env(environment: Mapping[str, str]) -> Path | None:
    configured_root = environment.get("NURILAB_EXTERNAL_REGRESSION_ROOT")
    if configured_root is None:
        return None
    if not configured_root.strip():
        raise ValueError("NURILAB_EXTERNAL_REGRESSION_ROOT is set but empty")

    root_path = Path(configured_root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError(
            "NURILAB_EXTERNAL_REGRESSION_ROOT must name an existing directory: "
            f"{root_path}"
        )
    return root_path


def _git_output(target: Path, *arguments: str) -> str:
    command = ["git", *arguments]
    try:
        completed = subprocess.run(
            command,
            cwd=target,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError as exc:
        raise ValueError(f"Unable to run git for {target}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise ValueError(f"Git validation failed for {target}: {details}") from exc
    return completed.stdout.strip()


def _validate_target_checkout(target: Path, expected_sha: str) -> None:
    if not target.is_dir():
        raise ValueError(f"Target repository is missing: {target}")

    resolved_target = target.resolve()
    git_root = Path(_git_output(target, "rev-parse", "--show-toplevel")).resolve()
    if git_root != resolved_target:
        raise ValueError(
            f"Target must be its own Git checkout: {resolved_target} "
            f"is nested in {git_root}"
        )

    actual_sha = _git_output(target, "rev-parse", "HEAD")
    if actual_sha != expected_sha:
        raise ValueError(
            f"Target {target.name} is at {actual_sha}, expected {expected_sha}. "
            "Check out the pinned commit."
        )

    status = _git_output(
        target,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignored=matching",
    )
    if status:
        raise ValueError(
            f"Target {target.name} must be clean, including ignored files. "
            "git status --porcelain=v1 --untracked-files=all --ignored=matching "
            f"returned:\n{status}"
        )


def _normalize_string(value: str, root_path: Path) -> str:
    root = root_path.resolve()
    root_variants = {
        str(root),
        root.as_posix(),
        str(root).replace("\\", "/"),
        root.as_posix().replace("/", "\\"),
    }
    normalized = value
    for root_variant in sorted(root_variants, key=len, reverse=True):
        if not root_variant:
            continue
        start = 0
        while (index := normalized.find(root_variant, start)) != -1:
            end = index + len(root_variant)
            if end == len(normalized) or normalized[end] in {"/", "\\"}:
                normalized = f"{normalized[:index]}<ROOT>{normalized[end:]}"
                start = index + len("<ROOT>")
            else:
                start = end
    return normalized


def normalize_report(report: dict[str, Any], root_path: Path) -> dict[str, Any]:
    """Return a non-mutating snapshot with only top-level time/path variance removed."""

    def normalize(value: Any, *, depth: int) -> Any:
        if isinstance(value, dict):
            return {
                key: normalize(child, depth=depth + 1)
                for key, child in value.items()
                if not (depth == 0 and key == "generated_at")
            }
        if isinstance(value, list):
            return [normalize(child, depth=depth + 1) for child in value]
        if isinstance(value, str):
            return _normalize_string(value, root_path)
        return value

    normalized = normalize(report, depth=0)
    assert isinstance(normalized, dict)
    return normalized


class _ReadOnlyRuffCollector(RuffToolCollector):
    """Use the test interpreter's locked Ruff without allowing source mutation."""

    def collect(self, target: str | Path) -> list[RuffFinding]:
        resolved_target = Path(target).expanduser().resolve()
        command = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(resolved_target),
            "--no-fix",
            "--no-fix-only",
            "--no-cache",
            "--output-format",
            "json",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            pytest.fail(f"Could not run locked Ruff for {resolved_target}: {exc}")

        if completed.returncode not in {0, 1}:
            pytest.fail(
                f"Locked Ruff failed for {resolved_target} with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )
        if not completed.stdout.strip():
            pytest.fail(f"Locked Ruff returned empty JSON output for {resolved_target}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"Locked Ruff returned invalid JSON for {resolved_target}: {exc}"
            )
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            pytest.fail(
                f"Locked Ruff returned a non-list JSON payload for {resolved_target}"
            )
        return [self._from_ruff_item(item) for item in payload]


@pytest.fixture(scope="session")
def external_targets() -> dict[str, str]:
    try:
        return _load_targets()
    except ValueError as exc:
        pytest.fail(str(exc))


@pytest.fixture
def external_root() -> Path:
    try:
        root = _external_root_from_env(os.environ)
    except ValueError as exc:
        pytest.fail(str(exc))
    if root is None:
        pytest.skip(
            "set NURILAB_EXTERNAL_REGRESSION_ROOT to run external regression tests"
        )
    return root


def test_external_regression_manifest_has_all_supported_targets() -> None:
    targets = _load_targets()
    assert tuple(targets) == SUPPORTED_TARGETS


@pytest.mark.parametrize("use_ruff", [False, True])
@pytest.mark.parametrize("repo_name", SUPPORTED_TARGETS)
def test_external_regression_pinned_targets(
    use_ruff: bool,
    repo_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    external_targets: dict[str, str],
    external_root: Path,
) -> None:
    repo_path = external_root / repo_name
    try:
        _validate_target_checkout(repo_path, external_targets[repo_name])
    except ValueError as exc:
        pytest.fail(str(exc))

    ruff_collector = _ReadOnlyRuffCollector() if use_ruff else RuffToolCollector()
    monkeypatch.setenv("RUFF_NO_CACHE", "1")
    report, output_paths = Phase1Pipeline(
        ruff_collector=ruff_collector,
        review_client=MockReviewClient(),
        use_ruff=use_ruff,
    ).run(input_path=repo_path, output_dir=tmp_path, formats=["html", "json"])

    assert isinstance(report, ProjectReport)
    assert set(output_paths) == {"html", "json"}
    html = output_paths["html"].read_text(encoding="utf-8")
    assert html.strip()
    assert "<h1>Python Project Review Report</h1>" in html

    persisted_report = json.loads(output_paths["json"].read_text(encoding="utf-8"))
    assert persisted_report == report.to_dict()
    try:
        _validate_target_checkout(repo_path, external_targets[repo_name])
    except ValueError as exc:
        pytest.fail(f"Target changed during analysis: {exc}")

    expected = _load_baseline(_baseline_path(repo_name, use_ruff))
    assert normalize_report(persisted_report, external_root) == expected


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "missing"),
        ("{", "malformed"),
        ("{}", "non-empty"),
        (json.dumps({"packaging": "a", "click": "b"}), "exactly"),
        (
            json.dumps({"packaging": "a" * 40, "click": "b" * 40, "requests": ""}),
            "40-character",
        ),
        (
            json.dumps(
                {"packaging": "a" * 40, "click": "B" * 40, "requests": "c" * 40}
            ),
            "40-character",
        ),
    ],
)
def test_load_targets_rejects_invalid_manifests(
    tmp_path: Path,
    content: str | None,
    message: str,
) -> None:
    manifest = tmp_path / "targets.json"
    if content is not None:
        manifest.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _load_targets(manifest)


def test_load_baseline_fails_without_creating_a_file(tmp_path: Path) -> None:
    baseline = tmp_path / "missing.json"

    with pytest.raises(pytest.fail.Exception, match="baseline is missing"):
        _load_baseline(baseline)

    assert not baseline.exists()


def test_load_baseline_rejects_malformed_json(tmp_path: Path) -> None:
    baseline = tmp_path / "bad.json"
    baseline.write_text("{", encoding="utf-8")

    with pytest.raises(pytest.fail.Exception, match="baseline is malformed"):
        _load_baseline(baseline)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [({}, None), ({"NURILAB_EXTERNAL_REGRESSION_ROOT": ""}, "set but empty")],
)
def test_external_root_configuration_distinguishes_unset_and_empty(
    environment: dict[str, str],
    expected: str | None,
) -> None:
    if expected is None:
        assert _external_root_from_env(environment) is None
    else:
        with pytest.raises(ValueError, match=expected):
            _external_root_from_env(environment)


def test_external_root_configuration_rejects_invalid_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="existing directory"):
        _external_root_from_env(
            {"NURILAB_EXTERNAL_REGRESSION_ROOT": str(tmp_path / "missing")}
        )


def _make_git_repository(tmp_path: Path, name: str = "target") -> tuple[Path, str]:
    repository = tmp_path / name
    repository.mkdir()
    (repository / "tracked.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=NuriLab Tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "-m",
            "initial",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return repository, _git_output(repository, "rev-parse", "HEAD")


def test_validate_target_checkout_rejects_wrong_sha(tmp_path: Path) -> None:
    repository, _ = _make_git_repository(tmp_path)

    with pytest.raises(ValueError, match="expected"):
        _validate_target_checkout(repository, "0" * 40)


def test_validate_target_checkout_rejects_nested_directory(tmp_path: Path) -> None:
    repository, sha = _make_git_repository(tmp_path)
    nested = repository / "nested"
    nested.mkdir()

    with pytest.raises(ValueError, match="own Git checkout"):
        _validate_target_checkout(nested, sha)


@pytest.mark.parametrize("dirty_kind", ["tracked", "staged", "untracked", "ignored"])
def test_validate_target_checkout_rejects_all_dirty_files(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    repository, sha = _make_git_repository(tmp_path)
    subprocess.run(
        ["git", "config", "status.showUntrackedFiles", "no"],
        cwd=repository,
        check=True,
    )
    if dirty_kind == "tracked":
        (repository / "tracked.py").write_text("value = 2\n", encoding="utf-8")
    elif dirty_kind == "staged":
        staged = repository / "staged.py"
        staged.write_text("value = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", staged.name], cwd=repository, check=True)
    elif dirty_kind == "untracked":
        (repository / "untracked.py").write_text("value = 2\n", encoding="utf-8")
    else:
        (repository / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=repository, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=NuriLab Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit",
                "-m",
                "ignore generated Python",
            ],
            cwd=repository,
            check=True,
            capture_output=True,
        )
        sha = _git_output(repository, "rev-parse", "HEAD")
        (repository / "ignored.py").write_text("value = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be clean"):
        _validate_target_checkout(repository, sha)


def test_normalize_report_is_pure_and_respects_path_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "외부 root"
    actual_path = root / "nested.py"
    sibling = Path(f"{root}-sibling") / "nested.py"
    report = {
        "generated_at": "volatile",
        "analysis": {
            "path": str(actual_path),
            "windows_path": str(actual_path).replace("/", "\\"),
            "sibling": str(sibling),
            "generated_at": "preserved nested value",
        },
    }
    original = copy.deepcopy(report)

    normalized = normalize_report(report, root)

    assert report == original
    assert normalized["analysis"]["path"] == "<ROOT>/nested.py"
    assert normalized["analysis"]["windows_path"] == "<ROOT>\\nested.py"
    assert normalized["analysis"]["sibling"] == str(sibling)
    assert normalized["analysis"]["generated_at"] == "preserved nested value"
    assert "generated_at" not in normalized


class _RecordingRuffCollector(RuffToolCollector):
    def __init__(self, findings: list[RuffFinding] | None = None) -> None:
        super().__init__()
        self.calls: list[Path] = []
        self.findings = findings or []

    def collect(self, target: str | Path) -> list[RuffFinding]:
        self.calls.append(Path(target).resolve())
        return self.findings


@pytest.mark.parametrize("use_ruff", [False, True])
def test_pipeline_only_invokes_ruff_when_enabled(
    tmp_path: Path, use_ruff: bool
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "sample.py").write_text("value = 1\n", encoding="utf-8")
    collector = _RecordingRuffCollector()

    Phase1Pipeline(
        ruff_collector=collector,
        review_client=MockReviewClient(),
        use_ruff=use_ruff,
    ).run(target, tmp_path / "reports")

    assert collector.calls == ([target.resolve()] if use_ruff else [])


def test_read_only_ruff_collector_fails_for_invalid_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=2, stdout="", stderr="bad Ruff configuration"
        ),
    )

    with pytest.raises(pytest.fail.Exception, match="exit code 2"):
        _ReadOnlyRuffCollector().collect(target)


def test_read_only_ruff_collector_rejects_empty_success_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="", stderr=""
        ),
    )

    with pytest.raises(pytest.fail.Exception, match="empty JSON output"):
        _ReadOnlyRuffCollector().collect(target)


def test_read_only_ruff_collector_does_not_honor_target_fix_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "sample.py"
    source.write_text("import os\n", encoding="utf-8")
    (target / "pyproject.toml").write_text(
        "[tool.ruff]\nfix = true\n", encoding="utf-8"
    )
    monkeypatch.setenv("RUFF_NO_CACHE", "1")

    findings = _ReadOnlyRuffCollector().collect(target)

    assert findings
    assert source.read_text(encoding="utf-8") == "import os\n"
    assert not (target / ".ruff_cache").exists()
