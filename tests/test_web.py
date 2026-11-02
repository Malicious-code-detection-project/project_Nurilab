from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient

from project_nurilab import __version__
from project_nurilab.aggregation.result_aggregator import file_risk_level
from project_nurilab.config import DEFAULT_LLM_MODEL
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.reports.generator import MOCK_BADGE_TEXT
from project_nurilab.schemas import PythonAnalysis, RuffFinding
from project_nurilab.web.app import create_app
from project_nurilab.web.errors import ApiError
from project_nurilab.web.results import LLM_FAILURE_MESSAGES
from project_nurilab.web.settings import WebSettings
from project_nurilab.web.store import JobRecord, JobStore
from project_nurilab.web.uploads import plan_upload


STATIC_DIR = Path(__file__).parents[1] / "project_nurilab" / "web" / "static"
DANGEROUS_SOURCE = b"import os\n\n\ndef run(command):\n    return os.system(command)\n"
CLEAN_SOURCE = b"VALUE = 1\n"
MARKUP = "<script>alert(1)</script>"
JOB_FIELDS = {
    "id",
    "status",
    "created_at",
    "finished_at",
    "upload_name",
    "file_count",
    "review",
    "risk_level",
    "static_risk_level",
    "error",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NURILAB_LLM_BASE_URL",
        "NURILAB_LLM_MODEL",
        "NURILAB_LLM_TIMEOUT",
        "NURILAB_WEB_DATA_DIR",
        "NURILAB_WEB_HOST",
        "NURILAB_WEB_PORT",
        "NURILAB_WEB_MAX_UPLOAD_BYTES",
        "NURILAB_WEB_MAX_PYTHON_FILES",
        "NURILAB_WEB_MAX_FORM_FILES",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> WebSettings:
    return WebSettings(data_dir=tmp_path / "data")


@contextmanager
def web_client(settings: WebSettings, **kwargs: Any) -> Iterator[TestClient]:
    with TestClient(create_app(settings), **kwargs) as client:
        yield client


def upload(
    client: TestClient,
    files: dict[str, bytes],
    review_mode: str | None = None,
) -> Any:
    multipart = [
        ("files", (name, content, "application/octet-stream"))
        for name, content in files.items()
    ]
    data = {"review_mode": review_mode} if review_mode is not None else {}
    return client.post("/api/analyses", files=multipart, data=data)


def wait_for_job(client: TestClient, job_id: str, timeout: float = 15.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/analyses/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def wait_for_status(
    client: TestClient, job_id: str, status: str, timeout: float = 15.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get(f"/api/analyses/{job_id}").json()["status"] == status:
            return
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {status}")


def analyze(client: TestClient, files: dict[str, bytes], **kwargs: Any) -> Any:
    response = upload(client, files, **kwargs)
    assert response.status_code == 202, response.json()
    return wait_for_job(client, response.json()["id"])


def assert_error(response: Any, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert body["message"]


def job_ids(settings: WebSettings) -> list[str]:
    with sqlite3.connect(settings.database_path) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM jobs")]


def job_dirs(settings: WebSettings) -> list[Path]:
    return [path for path in settings.data_dir.iterdir() if path.is_dir()]


class _Response:
    text = ""

    def __init__(
        self,
        payload: Any = None,
        status_code: int = 200,
        json_error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)  # type: ignore[arg-type]

    def json(self) -> Any:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


def _models(*model_ids: str) -> _Response:
    return _Response({"data": [{"id": model_id} for model_id in model_ids]})


def _review(content: dict[str, Any]) -> _Response:
    return _Response({"choices": [{"message": {"content": json.dumps(content)}}]})


def fake_llm(
    monkeypatch: pytest.MonkeyPatch,
    models: _Response | Exception | None = None,
    review: Any = None,
) -> list[str]:
    """Patch requests for a fake LLM endpoint; return the URLs it was asked for."""

    calls: list[str] = []

    def fake_get(url: str, **kwargs: Any) -> _Response:
        calls.append(url)
        outcome = models if models is not None else _models(DEFAULT_LLM_MODEL)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def fake_post(url: str, **kwargs: Any) -> _Response:
        calls.append(url)
        if callable(review):
            return review(url, **kwargs)
        return _review(
            review or {"summary": "LLM summary", "risk_level": "low", "findings": []}
        )

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    return calls


# Settings


def test_settings_resolve_relative_and_symlinked_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NURILAB_WEB_DATA_DIR", "link/data")

    settings = WebSettings.from_env()

    assert settings.data_dir == real.resolve() / "data"
    assert settings.data_dir.is_absolute()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    settings = WebSettings.from_env()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8080
    assert settings.data_dir == tmp_path.resolve() / ".local/share/nurilab-web"
    assert settings.max_upload_bytes == 50 * 1024 * 1024
    assert settings.max_python_files == 500
    assert settings.max_form_files == 1000


def test_app_does_not_start_when_data_dir_has_backslash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NURILAB_WEB_DATA_DIR", str(tmp_path / "web\\data"))

    with pytest.raises(ValueError, match="backslash"):
        create_app()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NURILAB_WEB_PORT", "http"),
        ("NURILAB_WEB_PORT", "0"),
        ("NURILAB_WEB_MAX_UPLOAD_BYTES", "-1"),
        ("NURILAB_WEB_MAX_FORM_FILES", "1001"),
        ("NURILAB_WEB_MAX_FORM_FILES", "500"),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, value: str
) -> None:
    monkeypatch.setenv("NURILAB_WEB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        WebSettings.from_env()


# Upload rules and filtering


def test_upload_rules_match_server_settings(tmp_path: Path) -> None:
    settings = WebSettings(
        data_dir=tmp_path, max_upload_bytes=1234, max_python_files=7, max_form_files=9
    )
    with web_client(settings) as client:
        rules = client.get("/api/upload-rules").json()

    assert rules == {
        "extensions": [".py"],
        "excluded_dirs": [
            ".git",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "reports",
        ],
        "max_upload_bytes": 1234,
        "max_python_files": 7,
        "max_form_files": 9,
    }


def test_plan_upload_keeps_python_files_outside_excluded_dirs() -> None:
    plan = plan_upload(
        [
            "build/src/b.py",
            "build/README.md",
            "build/a.py",
            "build/build/c.py",
            "build/pkg/__pycache__/d.py",
            "build/.py",
        ]
    )

    assert plan.upload_name == "build"
    assert plan.is_folder
    assert plan.python_files == ["build/a.py", "build/src/b.py"]


@pytest.mark.parametrize(
    "names",
    [
        ["../a.py"],
        ["myproj/../a.py"],
        ["/abs/a.py"],
        ["C:/a.py"],
        ["myproj\\a.py"],
        ["a\x00.py"],
        ["<outside>/a.py"],
        ["myproj/a>.py"],
        [""],
        ["myproj//a.py"],
        ["myproj/./a.py"],
        ["myproj/"],
        ["myproj/a.py", "myproj/a.py"],
        ["one/a.py", "two/b.py"],
        ["a.py", "myproj/b.py"],
        ["a.py", "b.py"],
        ["myproj/a.py", "myproj/a.py/b.py"],
        ["myproj/x/../a.txt", "myproj/b.py"],
        ["myproj/Evil.py", "myproj/evil.py"],
        ["myproj/caf\u00e9.py", "myproj/cafe\u0301.py"],
        ["myproj/Pkg/a.py", "myproj/pkg/a.py"],
        ["myproj/X.py", "myproj/x.py/b.py"],
    ],
)
def test_plan_upload_rejects_path_tricks_and_layout_errors(names: list[str]) -> None:
    with pytest.raises(ApiError) as excinfo:
        plan_upload(names)

    assert (excinfo.value.status_code, excinfo.value.code) == (400, "invalid_path")


# Normal uploads


def test_single_file_upload_completes_with_static_risk(settings: WebSettings) -> None:
    with web_client(settings) as client:
        job = analyze(client, {"danger.py": DANGEROUS_SOURCE})
        result = client.get(f"/api/analyses/{job['id']}/result").json()
        report = client.get(f"/api/analyses/{job['id']}/report.json")
        html = client.get(f"/api/analyses/{job['id']}/report.html")

    assert set(job) == JOB_FIELDS
    assert job["status"] == "completed"
    assert job["upload_name"] == "danger.py"
    assert job["file_count"] == 1
    assert job["review"] == {
        "client": "mock",
        "model": None,
        "status": "ok",
        "failure_code": None,
    }
    assert job["risk_level"] == "high"
    assert job["error"] is None
    single = Phase1Pipeline(use_ruff=False).analyze(
        _write(settings.data_dir.parent / "copy" / "danger.py", DANGEROUS_SOURCE)
    )
    assert job["static_risk_level"] == file_risk_level(single.analysis)  # type: ignore[arg-type]

    payload = report.json()
    assert payload["analysis"]["path"] == "danger.py"
    assert "static_risk_level" not in report.text
    assert "static_risk_level" not in html.text
    assert report.headers["content-disposition"].startswith("attachment")
    assert html.headers["content-disposition"].startswith("attachment")
    assert 'filename="danger.analysis.json"' in report.headers["content-disposition"]

    assert set(result) == {
        "analyzer_version",
        "generated_at",
        "summary",
        "review_failure_message",
        "findings",
        "static_signals",
        "skipped_files",
    }
    assert result["summary"] == payload["review"]["summary"]
    assert result["review_failure_message"] is None
    assert result["findings"][0]["file"] == "danger.py"
    assert set(result["findings"][0]) == {
        "title",
        "severity",
        "file",
        "line",
        "column",
        "source",
        "rule_id",
        "reason",
        "recommendation",
    }
    assert result["static_signals"] == [
        {
            "file": "danger.py",
            "suspicious_calls": [
                {
                    "name": "os.system",
                    "line": 5,
                    "category": "command_execution",
                    "severity": "high",
                }
            ],
            "secrets": [],
            "syntax_error": None,
        }
    ]


def test_file_risk_level_counts_the_file_own_ruff_findings() -> None:
    # A single-file run keeps Ruff findings on the analysis itself; a failed
    # Ruff run is recorded as medium.
    failed_ruff = RuffFinding(
        file="a.py",
        line=1,
        column=1,
        rule_id="RUFF_COMMAND_FAILED",
        message="Ruff command failed",
        severity="medium",
    )
    analysis = PythonAnalysis(path="a.py", line_count=1, ruff_findings=[failed_ruff])

    assert file_risk_level(analysis) == "medium"
    assert file_risk_level(analysis, []) == "low"


def test_single_file_static_risk_matches_folder_file_risk(
    settings: WebSettings,
) -> None:
    sources = {
        "danger.py": DANGEROUS_SOURCE,
        "clean.py": CLEAN_SOURCE,
        "broken.py": b"def broken(:\n",
        "unreadable.py": b"\xff\xfe\x00",
    }
    with web_client(settings) as client:
        folder_job = analyze(
            client, {f"proj/{name}": content for name, content in sources.items()}
        )
        folder_report = client.get(
            f"/api/analyses/{folder_job['id']}/report.json"
        ).json()
        single_risks = {
            name: analyze(client, {name: content})["static_risk_level"]
            for name, content in sources.items()
        }

    folder_risks = {
        summary["path"]: summary["risk_level"]
        for summary in folder_report["analysis"]["summary"]["file_summaries"]
    }
    assert single_risks == folder_risks
    assert folder_job["static_risk_level"] == "high"
    assert set(single_risks.values()) == {"high", "medium", "low", "unknown"}


def test_nested_folder_upload_keeps_relative_paths_and_filters(
    settings: WebSettings,
) -> None:
    files = {
        "build/src/pkg/runner.py": DANGEROUS_SOURCE,
        "build/src/pkg/__init__.py": b"",
        "build/README.md": b"not python",
        "build/dist/skipped.py": DANGEROUS_SOURCE,
        "build/src/__pycache__/cached.py": DANGEROUS_SOURCE,
    }
    with web_client(settings) as client:
        job = analyze(client, files)
        report = client.get(f"/api/analyses/{job['id']}/report.json").json()

    assert job["upload_name"] == "build"
    assert job["file_count"] == 2
    assert report["analysis"]["root_path"] == "build"
    assert [result["path"] for result in report["analysis"]["file_results"]] == [
        "build/src/pkg/__init__.py",
        "build/src/pkg/runner.py",
    ]
    assert job["static_risk_level"] == report["analysis"]["summary"]["risk_level"]


def test_upload_is_deleted_after_analysis(settings: WebSettings) -> None:
    with web_client(settings) as client:
        job = analyze(client, {"proj/a.py": CLEAN_SOURCE})

    job_root = settings.data_dir / job["id"]
    assert not (job_root / "upload").exists()
    assert sorted(path.name for path in job_root.iterdir()) == [
        "proj.analysis.html",
        "proj.analysis.json",
    ]


# Rejected uploads


@pytest.mark.parametrize(
    "files",
    [
        {"../a.py": CLEAN_SOURCE},
        {"one/a.py": CLEAN_SOURCE, "two/b.py": CLEAN_SOURCE},
        {"a.py": CLEAN_SOURCE, "proj/b.py": CLEAN_SOURCE},
        {"proj\\a.py": CLEAN_SOURCE},
    ],
)
def test_path_tricks_are_rejected_without_a_job(
    settings: WebSettings, files: dict[str, bytes]
) -> None:
    with web_client(settings) as client:
        assert_error(upload(client, files), 400, "invalid_path")

    assert job_ids(settings) == []
    assert job_dirs(settings) == []


def test_duplicate_upload_paths_are_rejected(settings: WebSettings) -> None:
    multipart = [
        ("files", ("proj/a.py", CLEAN_SOURCE)),
        ("files", ("proj/a.py", DANGEROUS_SOURCE)),
    ]
    with web_client(settings) as client:
        response = client.post("/api/analyses", files=multipart)

    assert_error(response, 400, "invalid_path")


def test_paths_differing_only_in_case_are_rejected_without_a_job(
    settings: WebSettings,
) -> None:
    # On a disk that ignores case, the clean file would replace the risky one.
    with web_client(settings) as client:
        response = upload(
            client, {"proj/Evil.py": DANGEROUS_SOURCE, "proj/evil.py": CLEAN_SOURCE}
        )

    assert_error(response, 400, "invalid_path")
    assert job_dirs(settings) == []


def test_windows_absolute_names_are_cut_to_file_names(settings: WebSettings) -> None:
    with web_client(settings) as client:
        job = analyze(client, {"C:\\evil\\x.py": CLEAN_SOURCE})
        mixed = upload(
            client, {"\\\\host\\share\\x.py": CLEAN_SOURCE, "proj/a.py": CLEAN_SOURCE}
        )

    assert job["upload_name"] == "x.py"
    assert_error(mixed, 400, "invalid_path")


def test_non_multipart_request_is_rejected(settings: WebSettings) -> None:
    with web_client(settings) as client:
        as_json = client.post("/api/analyses", json={"files": ["a.py"]})
        as_form = client.post("/api/analyses", data={"review_mode": "mock"})

    assert_error(as_json, 400, "invalid_upload")
    assert_error(as_form, 400, "invalid_upload")


def test_broken_multipart_is_rejected(settings: WebSettings) -> None:
    with web_client(settings) as client:
        response = client.post(
            "/api/analyses",
            content=b"--x\r\nnot a part header\r\n\r\nbody",
            headers={"content-type": "multipart/form-data; boundary=x"},
        )
        missing_boundary = client.post(
            "/api/analyses",
            content=b"body",
            headers={"content-type": "multipart/form-data"},
        )

    assert_error(response, 400, "invalid_upload")
    assert_error(missing_boundary, 400, "invalid_upload")


def test_form_file_safety_limit_is_rejected(tmp_path: Path) -> None:
    settings = WebSettings(data_dir=tmp_path, max_python_files=2, max_form_files=3)
    files = {f"proj/{index}.txt": b"x" for index in range(4)}
    with web_client(settings) as client:
        assert_error(upload(client, files), 400, "invalid_upload")


def test_missing_content_length_is_rejected(settings: WebSettings) -> None:
    def body() -> Iterator[bytes]:
        yield b"--x\r\n"

    with web_client(settings) as client:
        response = client.post(
            "/api/analyses",
            content=body(),
            headers={"content-type": "multipart/form-data; boundary=x"},
        )

    assert_error(response, 411, "length_required")


def test_transfer_encoding_with_content_length_is_rejected(
    settings: WebSettings,
) -> None:
    # uvicorn reads a chunked body past Content-Length, so a small Content-Length
    # must not let a large chunked body through the size check.
    body = (
        b'--x\r\nContent-Disposition: form-data; name="files"; filename="a.py"'
        b"\r\n\r\nx = 1\n\r\n--x--\r\n"
    )
    with web_client(settings) as client:
        response = client.post(
            "/api/analyses",
            content=body,
            headers={
                "content-type": "multipart/form-data; boundary=x",
                "content-length": "10",
                "transfer-encoding": "chunked",
            },
        )

    assert_error(response, 400, "invalid_upload")
    assert job_ids(settings) == []


@pytest.mark.parametrize(
    "files",
    [
        # Single file whose report name "<stem>.analysis.html" would pass 255 bytes.
        {"가" * 90 + ".py": CLEAN_SOURCE},
        {"a" * 242 + ".py": CLEAN_SOURCE},
        {"c" * 242 + "/a.py": CLEAN_SOURCE},
        # A name or a whole path longer than the file system allows; about 4 KB
        # stays under the multipart header limit and fails only when saving.
        {"proj/" + "b" * 256 + ".py": CLEAN_SOURCE},
        {"proj/" + ("d" * 200 + "/") * 20 + "a.py": CLEAN_SOURCE},
    ],
)
def test_too_long_names_are_rejected_without_a_job(
    settings: WebSettings, files: dict[str, bytes]
) -> None:
    with web_client(settings) as client:
        assert_error(upload(client, files), 400, "invalid_path")

    assert job_ids(settings) == []
    assert job_dirs(settings) == []


def test_longest_report_name_still_completes(settings: WebSettings) -> None:
    with web_client(settings) as client:
        single = analyze(client, {"a" * 241 + ".py": CLEAN_SOURCE})
        folder = analyze(client, {"c" * 241 + "/a.py": CLEAN_SOURCE})

    assert single["status"] == "completed"
    assert folder["status"] == "completed"


def _path_of_depth(depth: int) -> str:
    """Return an upload path with ``depth`` parts, the file name included."""

    return "proj/" + "d/" * (depth - 2) + "a.py"


@pytest.mark.parametrize(
    "files",
    [
        {_path_of_depth(65): CLEAN_SOURCE},
        {_path_of_depth(1200): CLEAN_SOURCE},
        # Each step alone is shallow enough for mkdir(parents=True) to recurse,
        # but the finished tree is too deep for shutil.rmtree() to delete.
        {_path_of_depth(depth): CLEAN_SOURCE for depth in range(100, 1601, 100)},
        # Paths are checked before filtering, so a dropped file counts too.
        {_path_of_depth(65)[:-3] + ".txt": b"x", "proj/a.py": CLEAN_SOURCE},
    ],
)
def test_too_deep_paths_are_rejected_without_a_job(
    settings: WebSettings, files: dict[str, bytes]
) -> None:
    with web_client(settings) as client:
        assert_error(upload(client, files), 400, "invalid_path")

    assert job_ids(settings) == []
    assert job_dirs(settings) == []


def test_deepest_allowed_path_completes_and_server_restarts(
    settings: WebSettings,
) -> None:
    with web_client(settings) as client:
        job = analyze(client, {_path_of_depth(64): DANGEROUS_SOURCE})

    assert job["status"] == "completed"
    assert job["static_risk_level"] == "high"
    assert not (settings.data_dir / job["id"] / "upload").exists()
    with web_client(settings) as client:
        assert client.get("/healthz").status_code == 200


def test_upload_over_size_limit_is_rejected(tmp_path: Path) -> None:
    settings = WebSettings(data_dir=tmp_path, max_upload_bytes=1000)
    with web_client(settings) as client:
        response = upload(client, {"a.py": b"x = 1\n" * 300})

    assert_error(response, 413, "too_large")
    assert job_ids(settings) == []


def test_too_many_python_files_are_rejected(tmp_path: Path) -> None:
    settings = WebSettings(data_dir=tmp_path, max_python_files=2, max_form_files=10)
    files = {f"proj/{index}.py": CLEAN_SOURCE for index in range(3)}
    files["proj/notes.txt"] = b"dropped first"
    with web_client(settings) as client:
        response = upload(client, files)
        kept = upload(client, {"proj/a.py": CLEAN_SOURCE, "proj/notes.txt": b"x"})

    assert_error(response, 413, "too_many_files")
    assert kept.status_code == 202


@pytest.mark.parametrize(
    "files",
    [
        {"README.md": b"text"},
        {"proj/README.md": b"text", "proj/build/a.py": CLEAN_SOURCE},
        {},
    ],
)
def test_upload_without_python_files_is_rejected(
    settings: WebSettings, files: dict[str, bytes]
) -> None:
    with web_client(settings) as client:
        if files:
            response = upload(client, files)
        else:
            response = client.post(
                "/api/analyses", files=[], data={"review_mode": "mock"}
            )

    # An empty form has no multipart body, so it is not an upload at all.
    if files:
        assert_error(response, 422, "no_python_files")
    else:
        assert response.status_code == 400
    assert job_ids(settings) == []


def test_unknown_review_mode_is_rejected(settings: WebSettings) -> None:
    with web_client(settings) as client:
        response = upload(client, {"a.py": CLEAN_SOURCE}, review_mode="gpt")

    assert_error(response, 400, "invalid_request")


# Review modes


def test_mock_mode_runs_without_connection_check(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Mock mode must not call the LLM endpoint")

    monkeypatch.setattr("requests.get", forbidden)
    monkeypatch.setattr("requests.post", forbidden)
    with web_client(settings) as client:
        job = analyze(client, {"a.py": CLEAN_SOURCE}, review_mode="mock")

    assert job["status"] == "completed"
    assert job["review"]["client"] == "mock"


def test_local_mode_runs_llm_review_when_connected(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NURILAB_LLM_BASE_URL", "http://llm.test:8000/v1")
    monkeypatch.setenv("NURILAB_LLM_MODEL", "test-model")
    calls = fake_llm(monkeypatch, models=_models("test-model"))
    with web_client(settings) as client:
        job = analyze(client, {"a.py": CLEAN_SOURCE}, review_mode="local")
        result = client.get(f"/api/analyses/{job['id']}/result").json()

    assert calls == [
        "http://llm.test:8000/v1/models",
        "http://llm.test:8000/v1/chat/completions",
    ]
    assert job["status"] == "completed"
    assert job["review"] == {
        "client": "local",
        "model": "test-model",
        "status": "ok",
        "failure_code": None,
    }
    assert result["summary"] == "LLM summary"


@pytest.mark.parametrize(
    "models",
    [
        requests.exceptions.ConnectionError("refused http://10.0.0.5:8000"),
        requests.exceptions.ConnectTimeout("slow"),
        _Response(status_code=401),
        _Response(status_code=500),
        _Response(json_error=ValueError("broken")),
        _Response({"object": "list"}),
        _models("other-model"),
    ],
)
def test_local_mode_without_connection_returns_503_without_job(
    settings: WebSettings,
    monkeypatch: pytest.MonkeyPatch,
    models: _Response | Exception,
) -> None:
    calls = fake_llm(monkeypatch, models=models)
    with web_client(settings) as client:
        response = upload(client, {"a.py": CLEAN_SOURCE}, review_mode="local")

    assert_error(response, 503, "llm_unavailable")
    assert "Mock" in response.json()["message"]
    assert len(calls) == 1
    assert job_ids(settings) == []
    assert job_dirs(settings) == []


@pytest.mark.parametrize(
    ("models", "status"),
    [
        (_models(DEFAULT_LLM_MODEL), "connected"),
        (requests.exceptions.ConnectionError("refused"), "unreachable"),
        (_Response(status_code=401), "unreachable"),
        (_models("other-model"), "model_missing"),
        (requests.exceptions.ReadTimeout("slow"), "timeout"),
    ],
)
def test_llm_status_reports_status_and_model_without_url(
    settings: WebSettings,
    monkeypatch: pytest.MonkeyPatch,
    models: _Response | Exception,
    status: str,
) -> None:
    monkeypatch.setenv("NURILAB_LLM_BASE_URL", "http://10.0.0.5:8000/v1")
    fake_llm(monkeypatch, models=models)
    with web_client(settings) as client:
        response = client.get("/api/llm-status")

    assert response.json() == {"status": status, "model": DEFAULT_LLM_MODEL}
    assert "10.0.0.5" not in response.text


def test_llm_failure_reason_is_hidden_from_screen_result(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NURILAB_LLM_BASE_URL", "http://10.0.0.5:8000/v1")

    def refuse(url: str, **kwargs: Any) -> _Response:
        raise requests.exceptions.ConnectionError(f"refused {url}")

    fake_llm(monkeypatch, review=refuse)
    with web_client(settings) as client:
        job = analyze(client, {"a.py": DANGEROUS_SOURCE}, review_mode="local")
        result = client.get(f"/api/analyses/{job['id']}/result")
        report = client.get(f"/api/analyses/{job['id']}/report.json")

    assert job["status"] == "completed"
    assert job["risk_level"] == "unknown"
    assert job["static_risk_level"] == "high"
    assert job["review"]["status"] == "failed"
    assert job["review"]["failure_code"] == "connection_failed"
    llm_findings = [
        finding
        for finding in result.json()["findings"]
        if finding["source"] == "local_llm"
    ]
    assert [finding["reason"] for finding in llm_findings] == [
        LLM_FAILURE_MESSAGES["connection_failed"]
    ]
    assert (
        result.json()["review_failure_message"]
        == (LLM_FAILURE_MESSAGES["connection_failed"])
    )
    assert "10.0.0.5" not in result.text
    assert "Cause:" not in result.text
    assert "10.0.0.5" in report.text
    assert "Cause:" in report.text


def _raise(error: Exception) -> Any:
    def review(url: str, **kwargs: Any) -> _Response:
        raise error

    return review


def _respond(response: _Response) -> Any:
    return lambda url, **kwargs: response


@pytest.mark.parametrize(
    ("review", "failure_code"),
    [
        (_raise(requests.exceptions.Timeout("slow 10.0.0.5")), "timeout"),
        (_respond(_Response(status_code=500)), "http_error"),
        (_raise(requests.exceptions.ConnectionError("gone")), "connection_failed"),
        (_respond(_Response(json_error=ValueError("bad body"))), "invalid_response"),
        (
            _respond(_Response({"choices": [{"message": {"content": "not json"}}]})),
            "json_parse_failed",
        ),
    ],
    ids=["timeout", "http-error", "connection", "bad-body", "bad-json"],
)
def test_llm_failure_during_review_keeps_static_result_and_warns(
    settings: WebSettings,
    monkeypatch: pytest.MonkeyPatch,
    review: Any,
    failure_code: str,
) -> None:
    monkeypatch.setenv("NURILAB_LLM_BASE_URL", "http://10.0.0.5:8000/v1")
    # The connection check passes; the review request is what fails.
    fake_llm(monkeypatch, review=review)
    with web_client(settings) as client:
        job = analyze(client, {"a.py": DANGEROUS_SOURCE}, review_mode="local")
        result = client.get(f"/api/analyses/{job['id']}/result")
        html = client.get(f"/api/analyses/{job['id']}/report.html")

    assert job["status"] == "completed"
    assert job["review"]["status"] == "failed"
    assert job["review"]["failure_code"] == failure_code
    assert job["risk_level"] == "unknown"
    assert job["static_risk_level"] == "high"
    body = result.json()
    assert body["review_failure_message"] == LLM_FAILURE_MESSAGES[failure_code]
    assert [signal["file"] for signal in body["static_signals"]] == ["a.py"]
    assert "10.0.0.5" not in result.text
    assert "Cause:" not in result.text
    assert MOCK_BADGE_TEXT not in html.text


# Result provenance


def test_mock_result_shows_provenance_and_badge(settings: WebSettings) -> None:
    with web_client(settings) as client:
        job = analyze(
            client, {"proj/a.py": DANGEROUS_SOURCE, "proj/pkg/b.py": CLEAN_SOURCE}
        )
        result = client.get(f"/api/analyses/{job['id']}/result").json()
        report = client.get(f"/api/analyses/{job['id']}/report.json")
        html = client.get(f"/api/analyses/{job['id']}/report.html")

    assert job["review"] == {
        "client": "mock",
        "model": None,
        "status": "ok",
        "failure_code": None,
    }
    assert job["upload_name"] == "proj"
    assert job["file_count"] == 2
    assert result["analyzer_version"] == __version__
    assert result["generated_at"] == report.json()["generated_at"]
    assert result["review_failure_message"] is None
    assert result["skipped_files"] == []
    assert MOCK_BADGE_TEXT in html.text
    assert MOCK_BADGE_TEXT not in report.text


def test_llm_result_shows_model_without_mock_badge(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_llm(monkeypatch)
    with web_client(settings) as client:
        job = analyze(client, {"a.py": DANGEROUS_SOURCE}, review_mode="local")
        result = client.get(f"/api/analyses/{job['id']}/result").json()
        html = client.get(f"/api/analyses/{job['id']}/report.html")

    assert job["review"] == {
        "client": "local",
        "model": DEFAULT_LLM_MODEL,
        "status": "ok",
        "failure_code": None,
    }
    assert result["analyzer_version"] == __version__
    assert result["review_failure_message"] is None
    assert result["summary"] == "LLM summary"
    assert [signal["file"] for signal in result["static_signals"]] == ["a.py"]
    assert MOCK_BADGE_TEXT not in html.text


def test_unreadable_file_is_listed_without_llm_warning(settings: WebSettings) -> None:
    with web_client(settings) as client:
        job = analyze(client, {"bad.py": b"\xff\xfe\x00"})
        result = client.get(f"/api/analyses/{job['id']}/result").json()

    # Mock also reports unknown here, so only review.status marks an LLM failure.
    assert job["risk_level"] == "unknown"
    assert job["review"]["status"] == "ok"
    assert result["review_failure_message"] is None
    assert result["skipped_files"] == ["bad.py"]


# Markup in results


@pytest.mark.parametrize(
    "files",
    [{"a.py": DANGEROUS_SOURCE}, {"proj/a.py": DANGEROUS_SOURCE}],
    ids=["file", "folder"],
)
def test_markup_from_llm_review_is_escaped_in_report(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch, files: dict[str, bytes]
) -> None:
    # Uploads reject "<" and ">" and Mock masks secrets, so LLM text is how a
    # whole tag reaches a report.
    fake_llm(
        monkeypatch,
        review={
            "summary": MARKUP,
            "risk_level": "high",
            "findings": [
                {
                    "title": MARKUP,
                    "severity": "high",
                    "file": f"{MARKUP}.py",
                    "line": 1,
                    "reason": MARKUP,
                    "recommendation": MARKUP,
                }
            ],
        },
    )
    with web_client(settings) as client:
        job = analyze(client, files, review_mode="local")
        result = client.get(f"/api/analyses/{job['id']}/result")
        html = client.get(f"/api/analyses/{job['id']}/report.html")

    assert job["status"] == "completed"
    assert "<script" not in html.text.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html.text
    assert html.headers["content-disposition"].startswith("attachment")
    # JSON keeps the text as data; app.js renders it with textContent only.
    assert result.headers["content-type"].startswith("application/json")
    assert result.json()["summary"] == MARKUP


def test_special_characters_in_upload_name_are_escaped_in_report(
    settings: WebSettings,
) -> None:
    with web_client(settings) as client:
        job = analyze(client, {"a&b'c.py": DANGEROUS_SOURCE})
        html = client.get(f"/api/analyses/{job['id']}/report.html")

    assert job["upload_name"] == "a&b'c.py"
    assert "a&amp;b&#x27;c.py" in html.text
    assert "a&b'c.py" not in html.text


def test_file_name_with_markup_cannot_be_uploaded(settings: WebSettings) -> None:
    with web_client(settings) as client:
        response = upload(client, {"<script>.py": CLEAN_SOURCE})

    assert_error(response, 400, "invalid_path")


# Report paths


def test_reports_hold_no_server_data_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    monkeypatch.chdir(tmp_path)
    settings = WebSettings(data_dir=Path("link/data"))
    data_dir = str(settings.data_dir)
    # A data-dir path outside the job folder, quoted from user code, stays as is.
    other_job_path = f"{data_dir}/other-job/x.py"

    def review(url: str, json: dict[str, Any], **kwargs: Any) -> _Response:
        prompt = json["messages"][-1]["content"]
        match = re.search(re.escape(data_dir) + r"/[0-9a-f-]{36}", prompt)
        assert match is not None
        job = match.group(0)
        files = [
            f"{job}/upload/../../outside.py",
            "/etc/passwd",
            "C:\\Users\\me\\secret.py",
            ".",
            "..",
            "../..",
            f"{job}\\upload\\..\\..",
            "a.py",
        ]
        return _review(
            {
                "summary": f"Checked {job}. Code mentions {other_job_path}",
                "risk_level": "medium",
                "findings": [
                    {
                        "title": f"Finding {index}",
                        "severity": "low",
                        "file": file,
                        "line": 1,
                        "reason": f"See {job}/upload/myproj/a.py, and {job}.",
                        "recommendation": "Review.",
                    }
                    for index, file in enumerate(files)
                ],
            }
        )

    fake_llm(monkeypatch, review=review)
    with web_client(settings) as client:
        job = analyze(
            client,
            {"myproj/a.py": CLEAN_SOURCE, "myproj/bad.py": b"\xff\xfe\x00"},
            review_mode="local",
        )
        report_text = client.get(f"/api/analyses/{job['id']}/report.json").text
        html_text = client.get(f"/api/analyses/{job['id']}/report.html").text
        result = client.get(f"/api/analyses/{job['id']}/result").json()

    assert job["review"]["status"] == "ok"
    for text in (report_text, html_text):
        assert other_job_path in text
        assert data_dir not in text.replace(other_job_path, "")
        assert str(real) not in text.replace(other_job_path, "")
    report = json.loads(report_text)
    assert [finding["file"] for finding in report["review"]["findings"]] == [
        "<outside>/outside.py",
        "<outside>/passwd",
        "<outside>/secret.py",
        "myproj",
        None,
        None,
        None,
        "myproj/a.py",
    ]
    assert report["review"]["summary"].startswith("Checked <data>. ")
    assert report["review"]["findings"][0]["reason"] == ("See myproj/a.py, and <data>.")
    assert result["skipped_files"] == ["myproj/bad.py"]


# Job status, reports, and errors


def test_failed_analysis_has_no_report_and_removes_upload(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(self: Phase1Pipeline, input_path: Any, **kwargs: Any) -> None:
        raise RuntimeError(f"boom at {input_path}")

    monkeypatch.setattr(Phase1Pipeline, "analyze", explode)
    with web_client(settings) as client:
        job = analyze(client, {"a.py": CLEAN_SOURCE})
        responses = [
            client.get(f"/api/analyses/{job['id']}{suffix}")
            for suffix in ("/result", "/report.json", "/report.html")
        ]

    assert job["status"] == "failed"
    assert job["error"]["code"] == "analysis_error"
    assert "boom" not in job["error"]["message"]
    assert job["risk_level"] is None
    for response in responses:
        assert_error(response, 409, "report_unavailable")
    assert not (settings.data_dir / job["id"] / "upload").exists()


def _fail_store_update_once(
    monkeypatch: pytest.MonkeyPatch, matches: Any
) -> dict[str, bool]:
    original = JobStore.update
    state = {"failed": False}

    def flaky(self: JobStore, job_id: str, **values: Any) -> None:
        if matches(values) and not state["failed"]:
            state["failed"] = True
            raise sqlite3.OperationalError("database or disk is full")
        original(self, job_id, **values)

    monkeypatch.setattr(JobStore, "update", flaky)
    return state


def test_failed_running_write_fails_the_job_and_removes_upload(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _fail_store_update_once(
        monkeypatch, lambda values: values.get("status") == "running"
    )
    with web_client(settings) as client:
        job = analyze(client, {"a.py": CLEAN_SOURCE})

    assert state["failed"]
    assert job["status"] == "failed"
    assert job["error"]["code"] == "analysis_error"
    assert not (settings.data_dir / job["id"] / "upload").exists()


def test_failed_final_write_is_retried(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _fail_store_update_once(monkeypatch, lambda values: "finished_at" in values)
    with web_client(settings) as client:
        job = analyze(client, {"a.py": CLEAN_SOURCE})
        report = client.get(f"/api/analyses/{job['id']}/report.json")

    assert state["failed"]
    assert job["status"] == "completed"
    assert report.status_code == 200
    assert not (settings.data_dir / job["id"] / "upload").exists()


def test_restart_fails_unfinished_jobs_and_removes_uploads(
    settings: WebSettings,
) -> None:
    settings.data_dir.mkdir(parents=True)
    store = JobStore(settings.database_path)
    store.initialize()
    ids = {
        "queued": "11111111-1111-4111-8111-111111111111",
        "running": "22222222-2222-4222-8222-222222222222",
        "completed": "33333333-3333-4333-8333-333333333333",
    }
    for status, job_id in ids.items():
        store.create(
            JobRecord(
                id=job_id,
                status=status,
                created_at="2026-10-30T00:00:00+00:00",
                upload_name="a.py",
                file_count=1,
                review_client="mock",
            )
        )
        leftover = settings.data_dir / job_id / "upload"
        leftover.mkdir(parents=True)
        (leftover / "a.py").write_bytes(CLEAN_SOURCE)

    with web_client(settings) as client:
        jobs = {
            status: client.get(f"/api/analyses/{job_id}").json()
            for status, job_id in ids.items()
        }
        report = client.get(f"/api/analyses/{ids['queued']}/report.json")

    for status in ("queued", "running"):
        assert jobs[status]["status"] == "failed"
        assert jobs[status]["error"]["code"] == "interrupted"
        assert jobs[status]["finished_at"] is not None
    assert jobs["completed"]["status"] == "completed"
    assert_error(report, 409, "report_unavailable")
    for job_id in ids.values():
        assert not (settings.data_dir / job_id / "upload").exists()


def test_reports_wait_while_job_runs_and_analysis_stays_sequential(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    active = 0
    max_active = 0
    lock = threading.Lock()

    def slow_review(url: str, **kwargs: Any) -> _Response:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            assert release.wait(15)
        finally:
            with lock:
                active -= 1
        return _review({"summary": "slow", "risk_level": "low", "findings": []})

    fake_llm(monkeypatch, review=slow_review)
    with web_client(settings) as client:
        first = upload(client, {"a.py": CLEAN_SOURCE}, review_mode="local").json()
        second = upload(client, {"b.py": CLEAN_SOURCE}, review_mode="local").json()
        wait_for_status(client, first["id"], "running")

        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get(f"/api/analyses/{second['id']}").json()["status"] == (
            "queued"
        )
        for job_id in (first["id"], second["id"]):
            assert_error(
                client.get(f"/api/analyses/{job_id}/report.json"),
                409,
                "report_not_ready",
            )
            assert_error(
                client.get(f"/api/analyses/{job_id}/result"), 409, "report_not_ready"
            )

        release.set()
        finished = [wait_for_job(client, job["id"]) for job in (first, second)]

    assert [job["status"] for job in finished] == ["completed", "completed"]
    assert max_active == 1


@pytest.mark.parametrize(
    ("method", "path", "status_code", "code"),
    [
        ("get", "/missing", 404, "not_found"),
        ("get", "/static/missing.js", 404, "not_found"),
        ("get", "/api/analyses/not-a-uuid", 404, "not_found"),
        ("get", "/api/analyses/{unknown}/result", 404, "not_found"),
        ("get", "/api/analyses/{upper}", 404, "not_found"),
        ("delete", "/api/analyses/{unknown}", 405, "method_not_allowed"),
        ("get", "/api/analyses", 405, "method_not_allowed"),
    ],
)
def test_errors_use_code_and_message(
    settings: WebSettings, method: str, path: str, status_code: int, code: str
) -> None:
    unknown = "44444444-4444-4444-8444-444444444444"
    with web_client(settings) as client:
        response = getattr(client, method)(
            path.format(unknown=unknown, upper=unknown.upper().replace("-", ""))
        )

    assert_error(response, status_code, code)


def test_unexpected_errors_use_code_and_message(
    settings: WebSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: JobStore, job_id: str) -> None:
        raise sqlite3.OperationalError("disk I/O error at /srv/data")

    monkeypatch.setattr(JobStore, "get", broken)
    with web_client(settings, raise_server_exceptions=False) as client:
        response = client.get("/api/analyses/44444444-4444-4444-8444-444444444444")

    assert_error(response, 500, "internal_error")
    assert "/srv/data" not in response.text


# Static page


def test_index_and_assets_are_served_from_this_server(settings: WebSettings) -> None:
    with web_client(settings) as client:
        index = client.get("/")
        script = client.get("/static/app.js")

    assert index.status_code == 200
    assert 'src="/static/app.js"' in index.text
    assert script.status_code == 200
    for path in STATIC_DIR.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
        assert "innerHTML" not in text


def _js_function(script: str, name: str) -> str:
    start = script.index(f"function {name}(")
    return script[start : script.index("\n}\n", start)]


def test_llm_check_ignores_stale_answers_and_network_errors() -> None:
    # pytest cannot run the page, so the guards stay pinned as text.
    check = _js_function(
        (STATIC_DIR / "app.js").read_text(encoding="utf-8"), "checkLlm"
    )

    assert "const version = ++state.llmCheckVersion;" in check
    assert check.index('requestJson("/api/llm-status")') < check.index(
        "if (version !== state.llmCheckVersion)"
    )
    assert "} catch {" in check
    assert "LLM 연결 상태를 확인하지 못했습니다." in check


def test_init_checks_llm_when_the_toggle_is_already_on() -> None:
    init = _js_function((STATIC_DIR / "app.js").read_text(encoding="utf-8"), "init")

    assert 'if (byId("llm-toggle").checked) {\n    checkLlm();' in init


def test_index_has_fixed_notes_warning_and_badge() -> None:
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert MOCK_BADGE_TEXT in index
    assert "LLM 리뷰 실패, 정적 분석 결과만 유효" in index
    assert "Mock 리뷰는 AI 리뷰가 아니라 규칙 기반 요약입니다." in index
    assert "위험도 low는 안전하다는 뜻이 아닙니다." in index
    assert "Python 정적 분석만 수행했습니다." in index


def test_every_element_used_by_app_js_exists_in_index() -> None:
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    used = set(re.findall(r'byId\("([a-z-]+)"\)', script))
    for id_list in re.findall(r"for \(const id of \[(.*?)\]\)", script, re.DOTALL):
        used.update(re.findall(r'"([a-z-]+)"', id_list))

    assert {"review-warning", "provenance", "static-signals", "skipped-files"} <= used
    assert not [name for name in used if f'id="{name}"' not in index]


@pytest.mark.parametrize(
    "pattern",
    [
        r"\binnerHTML\b",
        r"\bouterHTML\b",
        r"\binsertAdjacentHTML\b",
        r"\bdocument\.write",
        r"\beval\s*\(",
        r"\bnew\s+Function\b",
        r"""setAttribute\(\s*["'](?:href|src|on)""",
    ],
)
def test_app_js_has_no_html_or_code_string_api(pattern: str) -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert re.search(pattern, script) is None


def test_app_js_sets_href_only_for_report_links() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert re.findall(r"\.href\s*=[^=].*", script) == [
        ".href = apiPath(jobId, `/report.${kind}`);"
    ]


def test_index_has_no_inline_script_or_event_handler() -> None:
    index = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert re.search(r"\son[a-z]+\s*=", index, re.IGNORECASE) is None
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", index, re.DOTALL)
    assert scripts == [(' src="/static/app.js" defer', "")]


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path
