"""Suspicious Python call definitions.

These rules are intentionally conservative. They do not declare code malicious;
they identify patterns worth explaining in a review report.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SuspiciousCallRule:
    """Metadata for a call pattern that deserves review attention."""

    category: str
    severity: str
    reason: str


SUSPICIOUS_CALL_RULES: dict[str, SuspiciousCallRule] = {
    "eval": SuspiciousCallRule(
        category="dynamic_execution",
        severity="high",
        reason="eval executes dynamically constructed Python expressions.",
    ),
    "exec": SuspiciousCallRule(
        category="dynamic_execution",
        severity="high",
        reason="exec can run arbitrary dynamically constructed Python code.",
    ),
    "compile": SuspiciousCallRule(
        category="dynamic_execution",
        severity="medium",
        reason="compile is often paired with dynamic execution paths.",
    ),
    "os.system": SuspiciousCallRule(
        category="command_execution",
        severity="high",
        reason="os.system executes shell commands and can expose injection risk.",
    ),
    "subprocess.run": SuspiciousCallRule(
        category="command_execution",
        severity="medium",
        reason="subprocess.run should be reviewed for shell=True and input handling.",
    ),
    "subprocess.Popen": SuspiciousCallRule(
        category="command_execution",
        severity="medium",
        reason="subprocess.Popen starts external processes and needs input review.",
    ),
    "pickle.load": SuspiciousCallRule(
        category="unsafe_deserialization",
        severity="high",
        reason="pickle.load can execute code when loading untrusted data.",
    ),
    "pickle.loads": SuspiciousCallRule(
        category="unsafe_deserialization",
        severity="high",
        reason="pickle.loads can execute code when loading untrusted data.",
    ),
    "yaml.load": SuspiciousCallRule(
        category="unsafe_deserialization",
        severity="high",
        reason="yaml.load can construct unsafe objects without SafeLoader.",
    ),
    "requests.get": SuspiciousCallRule(
        category="network_access",
        severity="low",
        reason="Outbound HTTP calls should be reviewed for URL control and timeout.",
    ),
    "requests.post": SuspiciousCallRule(
        category="network_access",
        severity="low",
        reason="Outbound HTTP calls should be reviewed for data exposure and timeout.",
    ),
    "open": SuspiciousCallRule(
        category="file_access",
        severity="low",
        reason="File access should be reviewed for path control and permissions.",
    ),
}
