"""Contract helpers for calling jadx-ai-mcp's ``get_class_source`` tool.

The functions here are pure: they validate inputs before a call and classify
the tool payload after a call, without touching the network or the MCP SDK.
Error message markers follow jadx-mcp-server V6.4.1 (see THE-151 section 3.3).
Unrecognized error messages still classify as a failure (``tool_error``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from project_nurilab.config import (
    JADX_MCP_ALLOWED_TOOLS,
    JADX_MCP_CLASS_NAME_MAX_LENGTH,
    JADX_MCP_MAX_CONTENT_BYTES,
)


_CLASS_NAME_PATTERN = re.compile(r"[A-Za-z0-9_$.]+")
_NOT_FOUND_PREFIX = "HTTP error 404"
_UNAVAILABLE_MARKER = "Cannot connect to JADX plugin"
_TIMEOUT_MARKER = "Request to JADX plugin timed out"


@dataclass(slots=True, frozen=True)
class ClassifiedPayload:
    """Call status and content derived from one ``get_class_source`` payload."""

    status: str
    reason: str | None = None
    content: str | None = None
    response_size_bytes: int | None = None
    truncated: bool = False


def validate_class_name(class_name: str) -> str | None:
    """Return a rejection reason for an unsafe class name, or None if valid."""

    if not class_name:
        return "class_name is empty."
    if len(class_name) > JADX_MCP_CLASS_NAME_MAX_LENGTH:
        return f"class_name exceeds {JADX_MCP_CLASS_NAME_MAX_LENGTH} characters."
    if not _CLASS_NAME_PATTERN.fullmatch(class_name):
        return "class_name may only contain letters, digits, '_', '$', and '.'."
    return None


def check_tool_allowed(tool: str) -> str | None:
    """Return a rejection reason for a tool outside the allowlist, or None."""

    if tool in JADX_MCP_ALLOWED_TOOLS:
        return None
    return f"Tool {tool!r} is not in the jadx-ai-mcp allowlist."


def extract_payload(structured: object, text: str | None) -> dict[str, Any] | None:
    """Return the tool payload from structuredContent, else from JSON text."""

    if isinstance(structured, dict):
        return structured
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def classify_payload(payload: object) -> ClassifiedPayload:
    """Classify a ``{"response": ...}`` or ``{"error": ...}`` tool payload."""

    if not isinstance(payload, dict):
        return ClassifiedPayload(
            status="malformed", reason="Tool result is not a JSON object."
        )

    if "error" in payload:
        message = str(payload["error"])
        if message.startswith(_NOT_FOUND_PREFIX):
            status = "not_found"
        elif _UNAVAILABLE_MARKER in message:
            status = "unavailable"
        elif _TIMEOUT_MARKER in message:
            status = "timeout"
        else:
            status = "tool_error"
        return ClassifiedPayload(status=status, reason=message)

    if "response" in payload:
        response = payload["response"]
        if not isinstance(response, str):
            return ClassifiedPayload(
                status="malformed", reason="Tool result 'response' is not a string."
            )
        if not response:
            return ClassifiedPayload(status="empty", response_size_bytes=0)
        content, size, truncated = _truncate_content(response)
        return ClassifiedPayload(
            status="success",
            content=content,
            response_size_bytes=size,
            truncated=truncated,
        )

    return ClassifiedPayload(
        status="malformed", reason="Tool result has neither 'response' nor 'error'."
    )


def _truncate_content(content: str) -> tuple[str, int, bool]:
    # Measure and cut by UTF-8 bytes. "replace" keeps lone surrogates from
    # raising, and "ignore" drops a multi-byte character split at the cut.
    encoded = content.encode("utf-8", errors="replace")
    size = len(encoded)
    if size <= JADX_MCP_MAX_CONTENT_BYTES:
        return content, size, False
    kept = encoded[:JADX_MCP_MAX_CONTENT_BYTES].decode("utf-8", errors="ignore")
    return kept, size, True
