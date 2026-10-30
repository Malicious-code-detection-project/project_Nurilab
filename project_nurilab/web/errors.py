"""Web error codes and the common ``{code, message}`` error response."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Fixed user-facing text; never carries server paths or exception text.
ERROR_MESSAGES = {
    "invalid_path": (
        "업로드 경로가 올바르지 않습니다. 파일 1개 또는 최상위 폴더 하나만 "
        "올릴 수 있습니다."
    ),
    "invalid_upload": "업로드 요청 형식이 올바르지 않습니다.",
    "length_required": "요청 크기(Content-Length)가 필요합니다.",
    "too_large": "업로드 크기가 상한을 넘었습니다.",
    "too_many_files": "분석할 .py 파일 수가 상한을 넘었습니다.",
    "no_python_files": "분석할 .py 파일이 없습니다.",
    "llm_unavailable": (
        "LLM 서버에 연결할 수 없습니다. 'LLM 리뷰 사용'을 끄면 Mock으로 "
        "실행할 수 있습니다."
    ),
    "not_found": "요청한 대상을 찾을 수 없습니다.",
    "method_not_allowed": "허용하지 않는 요청 방식입니다.",
    "invalid_request": "요청 값이 올바르지 않습니다.",
    "report_not_ready": "분석이 아직 끝나지 않았습니다.",
    "report_unavailable": "분석에 실패해 보고서가 없습니다.",
    "internal_error": "서버 내부 오류가 발생했습니다.",
}
# Job failure codes shown in the job status ``error`` field.
JOB_ERROR_MESSAGES = {
    "analysis_error": "분석 중 오류가 발생했습니다.",
    "interrupted": "서버가 재시작되어 분석이 중단되었습니다. 다시 업로드하세요.",
}
_STATUS_CODES = {
    404: "not_found",
    405: "method_not_allowed",
    411: "length_required",
    413: "too_large",
}


class ApiError(Exception):
    """An error answered as ``{code, message}`` with a fixed message."""

    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def error_response(
    status_code: int, code: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {"code": code, "message": ERROR_MESSAGES[code]},
        status_code=status_code,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Answer every error, including FastAPI's own, as ``{code, message}``."""

    async def api_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return error_response(exc.status_code, exc.code)

    async def http_error(request: Request, exc: Exception) -> JSONResponse:
        # Routing 404/405 and StaticFiles raise Starlette's HTTPException.
        assert isinstance(exc, StarletteHTTPException)
        if exc.status_code >= 500:
            code = "internal_error"
        else:
            code = _STATUS_CODES.get(exc.status_code, "invalid_request")
        return error_response(exc.status_code, code, headers=exc.headers)

    async def validation_error(request: Request, exc: Exception) -> JSONResponse:
        return error_response(400, "invalid_request")

    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error")

    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
