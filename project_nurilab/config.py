"""Application-level configuration constants."""

from __future__ import annotations

DEFAULT_REPORT_DIR = "reports"
SUPPORTED_EXTENSION = ".py"
DEFAULT_LLM_BASE_URL = "http://localhost:8000/v1"
DEFAULT_LLM_MODEL = "openai/gpt-oss-20b"
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
DEFAULT_LLM_TEMPERATURE = 0.1
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
