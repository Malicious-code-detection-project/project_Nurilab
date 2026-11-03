"""Application-level configuration constants."""

from __future__ import annotations

DEFAULT_REPORT_DIR = "reports"
SUPPORTED_EXTENSION = ".py"
DEFAULT_LLM_BASE_URL = "http://localhost:8000/v1"
DEFAULT_LLM_MODEL = "openai/gpt-oss-20b"
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
# GET /models only lists loaded models, so a short wait is enough.
DEFAULT_LLM_STATUS_TIMEOUT_SECONDS = 5.0
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_INPUT_BUDGET_BYTES = 64 * 1024  # 64 KiB
MIN_LLM_INPUT_BUDGET_BYTES = (
    1024  # 1 KiB: minimum viable budget for payload skeleton, metadata, and signals
)
# jadx-ai-mcp external tool contract (THE-151).
JADX_MCP_CLASS_SOURCE_TOOL = "get_class_source"
JADX_MCP_ALLOWED_TOOLS = frozenset({JADX_MCP_CLASS_SOURCE_TOOL})
JADX_MCP_EXPECTED_RELEASE = "jadx-ai-mcp V6.4.1"
JADX_MCP_CLASS_NAME_MAX_LENGTH = 512
# 256 KiB: the MCP SDK drops any SSE event over 1 MiB, and fastmcp 3.0.2 sends the
# source twice with JSON escaping, so Java-like sources fail from about 381 KiB.
JADX_MCP_MAX_CONTENT_BYTES = 256 * 1024
# Reasons are diagnostics; long server error text is cut before it reaches reports.
JADX_MCP_MAX_REASON_BYTES = 4 * 1024
# serverInfo name/version are server-controlled; real values are about 45 bytes.
JADX_MCP_MAX_SERVER_INFO_BYTES = 256
DEFAULT_JADX_MCP_URL = "http://127.0.0.1:8651/mcp"
JADX_MCP_CONNECT_TIMEOUT_SECONDS = 10.0  # connect + initialize + list_tools
JADX_MCP_CALL_TIMEOUT_SECONDS = 15.0
# Web MVP (THE-160); each value can be overridden by a NURILAB_WEB_* variable.
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8080
# Outside the repository so uploaded in-house sources are never committed.
DEFAULT_WEB_DATA_DIR = "~/.local/share/nurilab-web"
DEFAULT_WEB_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MiB request body
DEFAULT_WEB_MAX_PYTHON_FILES = 500
# Starlette's default max_files; the form file limit may not exceed it.
WEB_MAX_FORM_FILES_CEILING = 1000
# Above the .py limit so files the browser did not filter out still parse and
# are dropped by the server.
DEFAULT_WEB_MAX_FORM_FILES = WEB_MAX_FORM_FILES_CEILING
DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "reports",
    }
)
