"""FastAPI app: upload, job status, screen result, and report downloads."""

from __future__ import annotations

import errno
import json
import logging
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from project_nurilab.config import DEFAULT_EXCLUDED_DIRS, SUPPORTED_EXTENSION
from project_nurilab.llm.review import (
    LocalLLMReviewClient,
    MockReviewClient,
    ReviewClient,
)
from project_nurilab.web.errors import (
    ERROR_MESSAGES,
    JOB_ERROR_MESSAGES,
    ApiError,
    install_error_handlers,
)
from project_nurilab.web.results import build_screen_result
from project_nurilab.web.settings import WebSettings
from project_nurilab.web.store import JobRecord, JobStore, now_iso
from project_nurilab.web.uploads import UploadPlan, plan_upload
from project_nurilab.web.worker import (
    AnalysisTask,
    AnalysisWorker,
    job_dir,
    upload_dir,
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
# Canonical lowercase UUID4, the only form job ids are issued in.
JOB_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_CONTENT_LENGTH_PATTERN = re.compile(r"[0-9]+")


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Build the web app; settings default to ``WebSettings.from_env()``."""

    settings = settings or WebSettings.from_env()
    store = JobStore(settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        store.initialize()
        # The queue lived in the stopped process, so recover before starting.
        for job_id in store.interrupt_unfinished():
            logger.info("job %s failed: interrupted", job_id)
        _remove_leftover_uploads(settings.data_dir)
        worker = AnalysisWorker(store, settings.data_dir)
        worker.start()
        app.state.worker = worker
        try:
            yield
        finally:
            worker.stop()

    # The API docs pages load assets from a CDN, so they stay off.
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    install_error_handlers(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/llm-status")
    def llm_status() -> dict[str, str]:
        # No endpoint URL here: it may be a server's internal address.
        client = LocalLLMReviewClient()
        check = client.check_connection()
        if check.status != "connected":
            logger.warning("LLM connection check: %s (%s)", check.status, check.detail)
        return {"status": check.status, "model": client.model}

    @app.get("/api/upload-rules")
    def upload_rules() -> dict[str, Any]:
        return {
            "extensions": [SUPPORTED_EXTENSION],
            "excluded_dirs": sorted(DEFAULT_EXCLUDED_DIRS),
            "max_upload_bytes": settings.max_upload_bytes,
            "max_python_files": settings.max_python_files,
            "max_form_files": settings.max_form_files,
        }

    @app.post("/api/analyses", status_code=202)
    async def create_analysis(request: Request) -> JSONResponse:
        # Read the request directly: a File() parameter would parse the whole
        # body before these checks, with the default max_files.
        media_type = request.headers.get("content-type", "").split(";")[0]
        if media_type.strip().lower() != "multipart/form-data":
            raise ApiError(400, "invalid_upload")
        content_length = request.headers.get("content-length")
        if content_length is None:
            raise ApiError(411, "length_required")
        # With Transfer-Encoding the server reads the chunked body past
        # Content-Length, so the size check above would not hold.
        if "transfer-encoding" in request.headers:
            raise ApiError(400, "invalid_upload")
        if not _CONTENT_LENGTH_PATTERN.fullmatch(content_length):
            raise ApiError(400, "invalid_upload")
        if int(content_length) > settings.max_upload_bytes:
            raise ApiError(413, "too_large")
        try:
            form = await request.form(max_files=settings.max_form_files)
        except StarletteHTTPException:
            # Limit and format errors differ only in message text, so all are 400.
            raise ApiError(400, "invalid_upload") from None
        try:
            job_id = await _accept_upload(request, form)
        finally:
            await form.close()
        return JSONResponse({"id": job_id}, status_code=202)

    async def _accept_upload(request: Request, form: FormData) -> str:
        review_mode = form.get("review_mode", "mock")
        if review_mode not in ("mock", "local"):
            raise ApiError(400, "invalid_request")
        review_client: ReviewClient = MockReviewClient()
        review_model = None
        if review_mode == "local":
            # The checked client also runs the review, so both use one endpoint.
            llm_client = LocalLLMReviewClient()
            check = await run_in_threadpool(llm_client.check_connection)
            if check.status != "connected":
                logger.warning(
                    "LLM connection check: %s (%s)", check.status, check.detail
                )
                raise ApiError(503, "llm_unavailable")
            review_client, review_model = llm_client, llm_client.model

        names: list[str] = []
        files: dict[str, UploadFile] = {}
        for item in form.getlist("files"):
            if not isinstance(item, UploadFile):
                raise ApiError(400, "invalid_upload")
            names.append(item.filename or "")
            files[item.filename or ""] = item
        plan = plan_upload(names)
        if len(plan.python_files) > settings.max_python_files:
            raise ApiError(413, "too_many_files")
        if not plan.python_files:
            raise ApiError(422, "no_python_files")

        job_id = str(uuid.uuid4())
        try:
            await run_in_threadpool(
                _save_uploads, upload_dir(settings.data_dir, job_id), plan, files
            )
            store.create(
                JobRecord(
                    id=job_id,
                    status="queued",
                    created_at=now_iso(),
                    upload_name=plan.upload_name,
                    file_count=len(plan.python_files),
                    review_client=review_mode,
                    review_model=review_model,
                )
            )
        except Exception:
            shutil.rmtree(job_dir(settings.data_dir, job_id), ignore_errors=True)
            raise
        worker: AnalysisWorker = request.app.state.worker
        worker.submit(
            AnalysisTask(
                job_id=job_id,
                input_path=upload_dir(settings.data_dir, job_id) / plan.upload_name,
                review_client=review_client,
            )
        )
        logger.info("job %s queued", job_id)
        return job_id

    @app.get("/api/analyses/{job_id}")
    def get_analysis(job_id: str) -> dict[str, Any]:
        return _job_response(_get_job(store, job_id))

    @app.get("/api/analyses/{job_id}/result")
    def get_result(job_id: str) -> dict[str, Any]:
        job = _get_job(store, job_id)
        report_path = _report_path(settings.data_dir, job, "json")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return build_screen_result(report, job.review_status, job.review_failure_code)

    @app.get("/api/analyses/{job_id}/report.json")
    def get_report_json(job_id: str) -> FileResponse:
        return _download(settings.data_dir, _get_job(store, job_id), "json")

    @app.get("/api/analyses/{job_id}/report.html")
    def get_report_html(job_id: str) -> FileResponse:
        return _download(settings.data_dir, _get_job(store, job_id), "html")

    return app


def _get_job(store: JobStore, job_id: str) -> JobRecord:
    # Checked here rather than as a UUID parameter, whose error would be 422.
    job = store.get(job_id) if JOB_ID_PATTERN.fullmatch(job_id) else None
    if job is None:
        raise ApiError(404, "not_found")
    return job


def _job_response(job: JobRecord) -> dict[str, Any]:
    completed = job.status == "completed"
    error = None
    if job.status == "failed":
        message = JOB_ERROR_MESSAGES.get(
            job.error_code or "", ERROR_MESSAGES["internal_error"]
        )
        error = {"code": job.error_code, "message": message}
    return {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "upload_name": job.upload_name,
        "file_count": job.file_count,
        "review": {
            "client": job.review_client,
            "model": job.review_model,
            "status": job.review_status,
            "failure_code": job.review_failure_code,
        },
        "risk_level": job.risk_level if completed else None,
        "static_risk_level": job.static_risk_level if completed else None,
        "error": error,
    }


def _report_path(data_dir: Path, job: JobRecord, kind: str) -> Path:
    if job.status in ("queued", "running"):
        raise ApiError(409, "report_not_ready")
    if job.status != "completed" or job.report_path is None:
        raise ApiError(409, "report_unavailable")
    json_path = data_dir / job.report_path
    if kind == "html":
        stem = json_path.name.removesuffix(".analysis.json")
        path = json_path.with_name(f"{stem}.analysis.html")
    else:
        path = json_path
    if not path.is_file():
        raise ApiError(404, "not_found")
    return path


def _download(data_dir: Path, job: JobRecord, kind: str) -> FileResponse:
    path = _report_path(data_dir, job, kind)
    media_type = "application/json" if kind == "json" else "text/html"
    # Attachment keeps the report from rendering on this origin.
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="attachment",
    )


def _save_uploads(target: Path, plan: UploadPlan, files: dict[str, UploadFile]) -> None:
    try:
        target.mkdir(parents=True)
        root = target.resolve()
        for name in plan.python_files:
            path = target / name
            # plan_upload() already rejected path tricks; this is a second guard.
            if not path.resolve().is_relative_to(root):
                raise ApiError(400, "invalid_path")
            path.parent.mkdir(parents=True, exist_ok=True)
            upload = files[name]
            upload.file.seek(0)
            with path.open("wb") as output:
                shutil.copyfileobj(upload.file, output)
    except OSError as exc:
        # A name or path longer than the file system allows is a path problem;
        # other errors such as a full disk stay server errors.
        if exc.errno == errno.ENAMETOOLONG:
            raise ApiError(400, "invalid_path") from None
        raise


def _remove_leftover_uploads(data_dir: Path) -> None:
    """Delete upload copies left by a stopped server; reports stay."""

    for path in data_dir.iterdir():
        if JOB_ID_PATTERN.fullmatch(path.name) and path.is_dir():
            shutil.rmtree(path / "upload", ignore_errors=True)
