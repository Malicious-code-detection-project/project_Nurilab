"""Input validation and loading for the phase 1 Python-only MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_nurilab.config import SUPPORTED_EXTENSION


@dataclass(frozen=True, slots=True)
class LoadedPythonFile:
    """A loaded Python file plus metadata needed by downstream analyzers."""

    path: Path
    source: str
    lines: list[str]
    skipped: bool = False
    skip_reason: str | None = None


class PythonFileLoader:
    """Load exactly one Python source file."""

    def load(self, path: str | Path) -> LoadedPythonFile:
        """Validate and read a UTF-8 Python file."""

        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"Input file does not exist: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Input path must be a file: {file_path}")
        if file_path.suffix != SUPPORTED_EXTENSION:
            raise ValueError(
                f"Only {SUPPORTED_EXTENSION} files are supported in phase 1: "
                f"{file_path}"
            )

        try:
            source = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            return self._skipped_load(
                file_path,
                f"UTF-8 decode failed while reading {file_path}: {exc.reason}.",
            )
        except PermissionError as exc:
            return self._skipped_load(
                file_path,
                f"Permission denied while reading {file_path}: {exc}.",
            )
        except OSError as exc:
            return self._skipped_load(
                file_path,
                f"File could not be read from {file_path}: {exc}.",
            )

        lines = source.splitlines()

        return LoadedPythonFile(path=file_path, source=source, lines=lines)

    def _skipped_load(self, file_path: Path, reason: str) -> LoadedPythonFile:
        return LoadedPythonFile(
            path=file_path,
            source="",
            lines=[],
            skipped=True,
            skip_reason=reason,
        )
