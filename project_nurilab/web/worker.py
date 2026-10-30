"""Single analysis thread fed by a queue, one job at a time."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_nurilab.aggregation.result_aggregator import file_risk_level
from project_nurilab.llm.review import ReviewClient
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.reports.generator import ReportGenerator
from project_nurilab.reports.paths import (
    name_absolute_finding_files,
    relativize_report,
)
from project_nurilab.schemas import AnalysisReport, ProjectReport
from project_nurilab.web.store import JobStore, now_iso

logger = logging.getLogger(__name__)


def job_dir(data_dir: Path, job_id: str) -> Path:
    return data_dir / job_id


def upload_dir(data_dir: Path, job_id: str) -> Path:
    return job_dir(data_dir, job_id) / "upload"


@dataclass(frozen=True, slots=True)
class AnalysisTask:
    """A queued job: ``input_path`` is the uploaded file or top folder."""

    job_id: str
    input_path: Path
    review_client: ReviewClient


class AnalysisWorker:
    """Run queued jobs on one thread so analyses never overlap.

    LLM review is a blocking request of up to two minutes, so it must stay off
    the event loop; one thread also keeps execution strictly sequential.
    """

    def __init__(self, store: JobStore, data_dir: Path) -> None:
        self.store = store
        self.data_dir = data_dir
        self._queue: queue.Queue[AnalysisTask | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop, name="nurilab-analysis", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def submit(self, task: AnalysisTask) -> None:
        self._queue.put(task)

    def stop(self, timeout: float = 10.0) -> None:
        """Stop after the current job; jobs still queued are recovered on restart."""

        self._queue.put(None)
        self._thread.join(timeout)

    def _loop(self) -> None:
        while (task := self._queue.get()) is not None:
            try:
                self._run(task)
            except Exception:  # noqa: BLE001 - keep the thread alive for later jobs.
                logger.exception("job %s could not be recorded", task.job_id)

    def _run(self, task: AnalysisTask) -> None:
        started = time.monotonic()
        self.store.update(task.job_id, status="running")
        logger.info("job %s running", task.job_id)
        try:
            values = self._analyze(task)
        except Exception:  # noqa: BLE001 - any analysis error fails only this job.
            # Exception text and paths stay in the server log, never the API.
            logger.exception("job %s analysis error", task.job_id)
            values = {"status": "failed", "error_code": "analysis_error"}
        # The upload is removed before the final status, success or failure.
        shutil.rmtree(upload_dir(self.data_dir, task.job_id), ignore_errors=True)
        self.store.update(task.job_id, finished_at=now_iso(), **values)
        logger.info(
            "job %s %s in %.2fs",
            task.job_id,
            values["status"],
            time.monotonic() - started,
        )

    def _analyze(self, task: AnalysisTask) -> dict[str, Any]:
        pipeline = Phase1Pipeline(review_client=task.review_client, use_ruff=False)
        report = pipeline.analyze(task.input_path)

        # Longest root first; see reports/paths.py.
        uploads = upload_dir(self.data_dir, task.job_id)
        job_root = job_dir(self.data_dir, task.job_id)
        report = relativize_report(report, uploads, "")
        report = name_absolute_finding_files(report, uploads)
        report = relativize_report(report, job_root, "<data>")
        output_paths = ReportGenerator().write(
            report, job_root, formats=["json", "html"]
        )

        reviewer = report.review.reviewer
        return {
            "status": "completed",
            "review_status": reviewer.status if reviewer else None,
            "review_failure_code": reviewer.failure_code if reviewer else None,
            "risk_level": report.review.risk_level,
            "static_risk_level": static_risk_level(report),
            "report_path": output_paths["json"].relative_to(self.data_dir).as_posix(),
        }


def static_risk_level(report: AnalysisReport | ProjectReport) -> str:
    """Static-only risk: the folder card value, or the aggregator's file rule."""

    if isinstance(report, AnalysisReport):
        return file_risk_level(report.analysis)
    summary = report.analysis.summary
    return summary.risk_level if summary else "unknown"
