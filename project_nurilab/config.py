"""Application-level configuration constants."""

from __future__ import annotations

DEFAULT_REPORT_DIR = "reports"
SUPPORTED_EXTENSION = ".py"
DEFAULT_LLM_BASE_URL = "http://localhost:8000/v1"
DEFAULT_LLM_MODEL = "openai/gpt-oss-20b"
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
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
DEFAULT_JADX_MCP_URL = "http://127.0.0.1:8651/mcp"
JADX_MCP_CONNECT_TIMEOUT_SECONDS = 10.0  # connect + initialize + list_tools
JADX_MCP_CALL_TIMEOUT_SECONDS = 15.0
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
