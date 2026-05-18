"""Input validation and loading for the phase 1 Python-only MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_nurilab.config import DEFAULT_MAX_LINES, SUPPORTED_EXTENSION


@dataclass(frozen=True, slots=True)
class LoadedPythonFile:
    """A loaded Python file plus metadata needed by downstream analyzers."""

    path: Path
    source: str
    lines: list[str]
    skipped: bool = False
    skip_reason: str | None = None


class PythonFileLoader:
    """Load exactly one short Python source file.

    Phase 1 intentionally rejects directories, non-Python files, and files over
    the configured line limit. Returning a skipped payload instead of raising for
    long files lets the reporting layer explain why analysis did not proceed.
    """

    def __init__(self, max_lines: int = DEFAULT_MAX_LINES) -> None:
        self.max_lines = max_lines

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

        source = file_path.read_text(encoding="utf-8")
        lines = source.splitlines()

        if len(lines) > self.max_lines:
            return LoadedPythonFile(
                path=file_path,
                source=source,
                lines=lines,
                skipped=True,
                skip_reason=(
                    f"File has {len(lines)} lines, which exceeds the "
                    f"phase 1 limit of {self.max_lines} lines."
                ),
            )

        return LoadedPythonFile(path=file_path, source=source, lines=lines)
