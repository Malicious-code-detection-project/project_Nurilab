"""Web settings read from NURILAB_WEB_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from project_nurilab.config import (
    DEFAULT_WEB_DATA_DIR,
    DEFAULT_WEB_HOST,
    DEFAULT_WEB_MAX_FORM_FILES,
    DEFAULT_WEB_MAX_PYTHON_FILES,
    DEFAULT_WEB_MAX_UPLOAD_BYTES,
    DEFAULT_WEB_PORT,
    WEB_MAX_FORM_FILES_CEILING,
)


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Validated web settings. ``data_dir`` is always an absolute path."""

    data_dir: Path
    host: str = DEFAULT_WEB_HOST
    port: int = DEFAULT_WEB_PORT
    max_upload_bytes: int = DEFAULT_WEB_MAX_UPLOAD_BYTES
    max_python_files: int = DEFAULT_WEB_MAX_PYTHON_FILES
    max_form_files: int = DEFAULT_WEB_MAX_FORM_FILES

    def __post_init__(self) -> None:
        resolved = self.data_dir.expanduser().resolve()
        # Path replacement reads "\" in LLM paths as a separator, so a data
        # path holding "\" would miscount ".." steps and leak parent names.
        if "\\" in str(resolved):
            raise ValueError("NURILAB_WEB_DATA_DIR must not contain a backslash.")
        object.__setattr__(self, "data_dir", resolved)
        if not 0 < self.port < 65536:
            raise ValueError("NURILAB_WEB_PORT must be between 1 and 65535.")
        if self.max_upload_bytes <= 0:
            raise ValueError("NURILAB_WEB_MAX_UPLOAD_BYTES must be positive.")
        if self.max_python_files <= 0:
            raise ValueError("NURILAB_WEB_MAX_PYTHON_FILES must be positive.")
        if (
            not self.max_python_files
            < self.max_form_files
            <= WEB_MAX_FORM_FILES_CEILING
        ):
            raise ValueError(
                "NURILAB_WEB_MAX_FORM_FILES must be above "
                f"NURILAB_WEB_MAX_PYTHON_FILES and at most {WEB_MAX_FORM_FILES_CEILING}."
            )

    @classmethod
    def from_env(cls) -> WebSettings:
        """Read settings from the environment; raise ``ValueError`` if invalid."""

        return cls(
            data_dir=Path(os.getenv("NURILAB_WEB_DATA_DIR") or DEFAULT_WEB_DATA_DIR),
            host=os.getenv("NURILAB_WEB_HOST") or DEFAULT_WEB_HOST,
            port=_int_env("NURILAB_WEB_PORT", DEFAULT_WEB_PORT),
            max_upload_bytes=_int_env(
                "NURILAB_WEB_MAX_UPLOAD_BYTES", DEFAULT_WEB_MAX_UPLOAD_BYTES
            ),
            max_python_files=_int_env(
                "NURILAB_WEB_MAX_PYTHON_FILES", DEFAULT_WEB_MAX_PYTHON_FILES
            ),
            max_form_files=_int_env(
                "NURILAB_WEB_MAX_FORM_FILES", DEFAULT_WEB_MAX_FORM_FILES
            ),
        )

    @property
    def database_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer.") from None
