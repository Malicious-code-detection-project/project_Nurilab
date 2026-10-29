"""Root path replacement for reports shown outside the analysis host.

Reports carry absolute server paths in ``root_path``, file ``path`` values,
finding files, and finding text. Replacement runs on the report object, not
on ``to_dict()`` output, because HTML is rendered straight from the dataclasses.
The web runs ``relativize_report()`` and ``name_absolute_finding_files()`` for
the upload directory, then ``relativize_report()`` for the job directory;
longer roots go first.
"""

from __future__ import annotations

import ntpath
import posixpath
from dataclasses import fields, is_dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, TypeVar

from project_nurilab.schemas import AnalysisReport, ProjectReport


ReportT = TypeVar("ReportT", bound=AnalysisReport | ProjectReport)
_SEPARATORS = frozenset({"/", "\\"})
_OUTSIDE_MARKER = "<outside>"


def replace_root(value: str, root_path: str | Path, replacement: str) -> str:
    """Replace ``root_path`` where it ends at a path boundary in ``value``.

    The root ends at a boundary unless a name character (letter, digit, ``_``,
    ``-``) or a ``.`` followed by one comes next, so ``<root>-sibling`` and
    ``<root>.bak`` stay while ``<root>.``, ``<root>,`` and ``'<root>'`` in
    free text are replaced. An empty ``replacement`` also drops a separator
    right after the root, so ``<root>/pkg/a.py`` becomes ``pkg/a.py``. The
    separator stays when the root sits inside a longer path or starts the next
    root, so ``/backup<root>/a.py`` becomes ``/backup/a.py``.
    """

    return _replace_variants(value, _root_variants(root_path), replacement)


def relativize_report(
    report: ReportT, root_path: str | Path, replacement: str
) -> ReportT:
    """Return a copy of ``report`` with ``root_path`` replaced in every string.

    The original report is left unchanged. ``root_path`` is compared after
    ``expanduser().resolve()``, the same form the pipeline writes into reports.
    """

    variants = _root_variants(root_path)
    relativized = _replace_value(report, variants, replacement)
    assert isinstance(relativized, type(report))
    return relativized


def name_absolute_finding_files(report: ReportT, root_path: str | Path) -> ReportT:
    """Return a copy of ``report`` with finding files cleaned against ``root_path``.

    Run after ``relativize_report()`` with the same ``root_path``. A Local LLM
    finding ``file`` such as ``../notes.py`` or an invented ``/etc/passwd``
    resolves outside the root and stays absolute, so only its file name is
    kept, as ``<outside>/notes.py``. A file that is ``root_path`` or one of its
    parents (``..``, ``../..``, ``//<parent>``) would name a server directory,
    so it becomes ``None``. A file that normalizes to a path inside
    ``root_path`` keeps that relative path. A relative file is resolved
    against ``root_path`` first, because ``relativize_report()`` turns
    ``<root>/../x`` into ``../x`` and ``<root>/myproj/./a.py`` into
    ``myproj/./a.py``. ``\\`` is read as a separator, as in
    ``relativize_report()``. Only ``review.findings`` are copied; the rest of
    the returned report is shared with ``report``.
    """

    resolved = Path(root_path).expanduser().resolve().as_posix()
    # Files are read with "\" as "/", so the root must be read the same way.
    root = PurePosixPath(resolved.replace("\\", "/"))
    # Only finding files change, so copy the findings and share the rest.
    findings = [replace(finding) for finding in report.review.findings]
    named = replace(report, review=replace(report.review, findings=findings))
    for finding in named.review.findings:
        if not finding.file:
            continue
        # Step 1 treats "\" as a separator too, so read it as one here.
        slashed = finding.file.replace("\\", "/")
        is_absolute = _is_absolute(finding.file)
        # review() joins a "\srv\x.py" file under the root, leaving "myproj/\srv...";
        # read the path from the "\" again. A "//" written as such stays a separator.
        anchor = finding.file.find("/\\")
        if anchor > 0 and not is_absolute:
            slashed = slashed[anchor + 1 :]
        if is_absolute or slashed.startswith("/"):
            # normpath folds "a/../a" so a parent spelled with ".." is caught too.
            normalized = posixpath.normpath(slashed)
        else:
            # Relative files are read from the root, so ".", "//" and ".." fold too.
            normalized = posixpath.normpath(f"{root}/{slashed}")
        # POSIX keeps exactly two leading slashes, but Linux reads "//a" as "/a".
        if normalized.startswith("//"):
            normalized = normalized[1:]
        posix_file = PurePosixPath(normalized)
        if posix_file.is_absolute():
            if root.is_relative_to(posix_file):
                finding.file = None
            elif posix_file.is_relative_to(root):
                finding.file = posix_file.relative_to(root).as_posix()
            else:
                finding.file = _outside_name(posix_file.name)
        else:
            # PureWindowsPath splits on both separators, so this covers both forms.
            # ntpath.normpath folds "C:\x\.." to "C:\"; bare roots have no name
            # and become None like "".
            windows_file = PureWindowsPath(ntpath.normpath(finding.file))
            finding.file = _outside_name(windows_file.name)
    return named


def _outside_name(name: str) -> str | None:
    # Mark the name so it is not mistaken for an uploaded file with the same name.
    return f"{_OUTSIDE_MARKER}/{name}" if name else None


def _is_absolute(value: str) -> bool:
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _root_variants(root_path: str | Path) -> list[str]:
    root = Path(root_path).expanduser().resolve()
    variants = {
        str(root),
        root.as_posix(),
        str(root).replace("\\", "/"),
        root.as_posix().replace("/", "\\"),
    }
    # Longest first, so a variant never cuts into a longer match.
    return sorted((variant for variant in variants if variant), key=len, reverse=True)


def _replace_variants(value: str, variants: list[str], replacement: str) -> str:
    replaced = value
    for variant in variants:
        start = 0
        while (index := replaced.find(variant, start)) != -1:
            end = index + len(variant)
            if not _continues_name(replaced, end):
                # Keep the separator when the root sits inside a longer path, so
                # "/backup<root>/a.py" does not glue into "/backupa.py", and when
                # it starts the next root, which must still match.
                if (
                    not replacement
                    and end < len(replaced)
                    and replaced[end] in _SEPARATORS
                    and _starts_path(replaced, index)
                    and not any(replaced.startswith(item, end) for item in variants)
                ):
                    end += 1
                replaced = f"{replaced[:index]}{replacement}{replaced[end:]}"
                start = index + len(replacement)
            else:
                start = end
    return replaced


def _continues_name(value: str, end: int) -> bool:
    """Return whether ``value[end:]`` extends the root's last path component."""

    if end < len(value) and _is_name_char(value[end]):
        return True
    return end + 1 < len(value) and value[end] == "." and _is_name_char(value[end + 1])


def _starts_path(value: str, index: int) -> bool:
    """Return whether ``value[index:]`` is not the tail of a longer path."""

    if index == 0:
        return True
    previous = value[index - 1]
    return not (_is_name_char(previous) or previous == "." or previous in _SEPARATORS)


def _is_name_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "-"}


def _replace_value(value: Any, variants: list[str], replacement: str) -> Any:
    if isinstance(value, str):
        return _replace_variants(value, variants, replacement)
    if isinstance(value, list):
        return [_replace_value(item, variants, replacement) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_value(item, variants, replacement)
            for key, item in value.items()
        }
    if is_dataclass(value) and not isinstance(value, type):
        # init=False fields are fixed by the class, so replace() rebuilds them.
        changes = {
            item.name: _replace_value(getattr(value, item.name), variants, replacement)
            for item in fields(value)
            if item.init
        }
        return replace(value, **changes)
    return value
