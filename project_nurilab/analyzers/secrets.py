"""Lightweight hard-coded secret detection for Python source files."""

from __future__ import annotations

import re

from project_nurilab.schemas import SecretFinding


SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*=\s*['\"]([^'\"]{8,})['\"]"
)

PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def find_potential_secrets(lines: list[str]) -> list[SecretFinding]:
    """Return potential secrets from source lines.

    The matcher is deliberately simple for phase 1. It errs on the side of
    marking suspicious assignments as review findings, not confirmed leaks.
    """

    findings: list[SecretFinding] = []

    for index, line in enumerate(lines, start=1):
        assignment = SECRET_ASSIGNMENT_RE.search(line)
        if assignment:
            secret_name = assignment.group(1)
            secret_value = assignment.group(2)
            findings.append(
                SecretFinding(
                    kind=secret_name.lower(),
                    line=index,
                    preview=_preview(secret_value),
                    severity="high",
                    reason="Potential hard-coded secret assigned in source code.",
                )
            )

        if PRIVATE_KEY_RE.search(line):
            findings.append(
                SecretFinding(
                    kind="private_key",
                    line=index,
                    preview="-----BEGIN ... PRIVATE KEY-----",
                    severity="critical",
                    reason="Private key material appears to be embedded in code.",
                )
            )

    return findings


def _preview(value: str, visible: int = 4) -> str:
    """Show enough of a secret-like value for triage without exposing it fully."""

    if len(value) <= visible:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * max(len(value) - visible, 4)}"
