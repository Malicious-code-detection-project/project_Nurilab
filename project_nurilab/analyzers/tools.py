"""External static analysis tool collectors."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from project_nurilab.schemas import RuffFinding


class RuffToolCollector:
    """Collect Ruff findings through its JSON output format."""

    def __init__(self, command_prefix: tuple[str, ...] = ("uv", "run")) -> None:
        self.command_prefix = command_prefix

    def collect(self, target: str | Path) -> list[RuffFinding]:
        """Run Ruff and return normalized findings.

        Ruff exits with a non-zero status when it finds issues. That is not a
        pipeline failure; the JSON stdout is the result we want to preserve.
        """

        command = [
            *self.command_prefix,
            "ruff",
            "check",
            str(Path(target).expanduser().resolve()),
            "--output-format",
            "json",
        ]
        completed = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if not completed.stdout.strip():
            return []

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return [
                RuffFinding(
                    file=str(Path(target).expanduser().resolve()),
                    line=1,
                    column=1,
                    rule_id="RUFF_PARSE_ERROR",
                    message=completed.stdout.strip(),
                    severity="medium",
                )
            ]

        return [self._from_ruff_item(item) for item in payload]

    def _from_ruff_item(self, item: dict[str, Any]) -> RuffFinding:
        location = item.get("location") or {}
        return RuffFinding(
            file=str(item.get("filename", "")),
            line=int(location.get("row") or 1),
            column=int(location.get("column") or 1),
            rule_id=str(item.get("code") or "RUFF"),
            message=str(item.get("message") or "Ruff issue"),
            severity="low",
        )
