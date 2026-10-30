"""Upload path validation and filtering shared by the API and upload rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from project_nurilab.config import DEFAULT_EXCLUDED_DIRS, SUPPORTED_EXTENSION
from project_nurilab.web.errors import ApiError

# "<" and ">" are kept out so no upload can look like the "<outside>" marker.
_FORBIDDEN_CHARS = frozenset({"\\", "\x00", "<", ">"})
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class UploadPlan:
    """What to save from one upload.

    ``upload_name`` is the single file or the top folder, which is also the
    analysis root. ``python_files`` holds the upload paths to keep, in order.
    """

    upload_name: str
    is_folder: bool
    python_files: list[str]


def plan_upload(
    names: list[str], excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS
) -> UploadPlan:
    """Validate every upload path, then keep ``.py`` files outside excluded dirs.

    Paths are checked before filtering so a dropped file cannot hide a path
    trick. Raises ``ApiError(400, "invalid_path")`` for path tricks and layout
    errors; dropping non-Python and excluded files is silent.
    """

    split_paths = [_split_upload_path(name) for name in names]
    if len(set(names)) != len(names):
        raise ApiError(400, "invalid_path")
    upload_name, is_folder = _upload_root(split_paths)
    _reject_file_directory_clash(split_paths)

    python_files = [
        name
        for name, parts in zip(names, split_paths, strict=True)
        if PurePosixPath(name).suffix == SUPPORTED_EXTENSION
        # Like the CLI, only parts below the analysis root are checked, so a
        # top folder named "build" is still analyzed.
        and not any(part in excluded_dirs for part in parts[1:])
    ]
    return UploadPlan(
        upload_name=upload_name,
        is_folder=is_folder,
        python_files=sorted(python_files),
    )


def _split_upload_path(name: str) -> tuple[str, ...]:
    if not name or any(char in _FORBIDDEN_CHARS for char in name):
        raise ApiError(400, "invalid_path")
    if name.startswith("/") or _DRIVE_LETTER.match(name):
        raise ApiError(400, "invalid_path")
    parts = tuple(name.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ApiError(400, "invalid_path")
    return parts


def _upload_root(split_paths: list[tuple[str, ...]]) -> tuple[str, bool]:
    if not split_paths:
        return "", False
    if all(len(parts) == 1 for parts in split_paths):
        if len(split_paths) > 1:
            raise ApiError(400, "invalid_path")
        return split_paths[0][0], False
    if any(len(parts) == 1 for parts in split_paths):
        raise ApiError(400, "invalid_path")
    top_folders = {parts[0] for parts in split_paths}
    if len(top_folders) > 1:
        raise ApiError(400, "invalid_path")
    return top_folders.pop(), True


def _reject_file_directory_clash(split_paths: list[tuple[str, ...]]) -> None:
    """Reject a file whose path is also a folder of another upload path."""

    files = set(split_paths)
    for parts in split_paths:
        for end in range(1, len(parts)):
            if parts[:end] in files:
                raise ApiError(400, "invalid_path")
