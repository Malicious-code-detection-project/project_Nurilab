"""Project-level Python file collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from project_nurilab.config import DEFAULT_EXCLUDED_DIRS, SUPPORTED_EXTENSION


@dataclass(frozen=True, slots=True)
class SkippedPath:
    """A path skipped before file loading and the reason it was skipped."""

    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class CollectedInput:
    """Normalized input collection for one file or one directory."""

    root_path: Path
    python_files: list[Path] = field(default_factory=list)
    skipped_paths: list[SkippedPath] = field(default_factory=list)


class InputCollector:
    """Collect Python files from a single file or project directory."""

    def __init__(self, excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS) -> None:
        self.excluded_dirs = excluded_dirs

    def collect(self, path: str | Path) -> CollectedInput:
        """Return sorted Python files for a file or directory input."""

        root_path = Path(path).expanduser().resolve()

        if not root_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {root_path}")

        if root_path.is_file():
            if root_path.suffix != SUPPORTED_EXTENSION:
                return CollectedInput(
                    root_path=root_path,
                    skipped_paths=[
                        SkippedPath(
                            path=root_path,
                            reason=f"Only {SUPPORTED_EXTENSION} files are supported.",
                        )
                    ],
                )
            return CollectedInput(root_path=root_path, python_files=[root_path])

        if not root_path.is_dir():
            raise ValueError(f"Input path must be a file or directory: {root_path}")

        python_files: list[Path] = []
        skipped_paths: list[SkippedPath] = []

        for child in sorted(root_path.rglob("*")):
            if self._is_under_excluded_dir(child, root_path):
                continue
            if child.is_file() and child.suffix == SUPPORTED_EXTENSION:
                python_files.append(child)
            elif child.is_file():
                skipped_paths.append(
                    SkippedPath(path=child, reason="Non-Python file skipped.")
                )

        return CollectedInput(
            root_path=root_path,
            python_files=python_files,
            skipped_paths=skipped_paths,
        )

    def _is_under_excluded_dir(self, path: Path, root_path: Path) -> bool:
        """Return True if any relative path segment is excluded."""

        try:
            relative_parts = path.relative_to(root_path).parts
        except ValueError:
            relative_parts = path.parts
        return any(part in self.excluded_dirs for part in relative_parts)
