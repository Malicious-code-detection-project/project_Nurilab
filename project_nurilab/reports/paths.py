"""Root path replacement for reports shown outside the analysis host.

Reports carry absolute server paths in ``root_path``, file ``path`` values,
finding files, and finding text. Replacement runs on the report object, not
on ``to_dict()`` output, because HTML is rendered straight from the dataclasses.
The web runs ``relativize_report()`` and ``name_absolute_finding_files()`` for
the upload directory, then ``relativize_report()`` for the job directory;
longer roots go first.
"""

from __future__ import annotations

import copy
import posixpath
from dataclasses import fields, is_dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, TypeVar

from project_nurilab.schemas import AnalysisReport, ProjectReport


ReportT = TypeVar("ReportT", bound=AnalysisReport | ProjectReport)
_SEPARATORS = frozenset({"/", "\\"})


def replace_root(value: str, root_path: str | Path, replacement: str) -> str:
    """Replace ``root_path`` where it ends at a path boundary in ``value``.

    The root ends at a boundary unless a name character (letter, digit, ``_``,
    ``-``) or a ``.`` followed by one comes next, so ``<root>-sibling`` and
    ``<root>.bak`` stay while ``<root>.``, ``<root>,`` and ``'<root>'`` in
    free text are replaced. An empty ``replacement`` also drops a separator
    right after the root, so ``<root>/pkg/a.py`` becomes ``pkg/a.py``.
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
    """Return a copy of ``report`` keeping only the name of absolute finding files.

    Run after ``relativize_report()`` with the same ``root_path``. A Local LLM
    finding ``file`` such as ``../notes.py`` or an invented ``/etc/passwd``
    resolves outside the root and stays absolute, so only its file name is
    kept. A file that is ``root_path`` or one of its parents (``..``,
    ``../..``, ``//<parent>``) would name a server directory, so it becomes
    ``None``.
    """

    root = PurePosixPath(Path(root_path).expanduser().resolve().as_posix())
    named = copy.deepcopy(report)
    for finding in named.review.findings:
        if not finding.file or not _is_absolute(finding.file):
            continue
        # normpath folds "a/../a" so a parent spelled with ".." is caught too.
        normalized = posixpath.normpath(finding.file)
        # POSIX keeps exactly two leading slashes, but Linux reads "//a" as "/a".
        if normalized.startswith("//"):
            normalized = normalized[1:]
        posix_file = PurePosixPath(normalized)
        if posix_file.is_absolute():
            if root.is_relative_to(posix_file):
                finding.file = None
            else:
                finding.file = posix_file.name or None
        else:
            # PureWindowsPath splits on both separators, so this covers both forms.
            # Bare roots such as "C:\" have no name and become None like "".
            finding.file = PureWindowsPath(finding.file).name or None
    return named


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
                if (
                    not replacement
                    and end < len(replaced)
                    and replaced[end] in _SEPARATORS
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
