from __future__ import annotations

import json

import pytest

from project_nurilab.config import (
    JADX_MCP_CLASS_NAME_MAX_LENGTH,
    JADX_MCP_MAX_CONTENT_BYTES,
)
from project_nurilab.external.jadx_mcp import (
    check_tool_allowed,
    classify_payload,
    extract_payload,
    validate_class_name,
)
from project_nurilab.schemas import (
    ALLOWED_EXTERNAL_TOOL_CALL_STATUSES,
    ExternalToolCall,
)


CALLED_AT = "2026-09-27T00:00:00+00:00"
SERVER_URL = "http://127.0.0.1:8651/mcp"

# Error messages produced by jadx-mcp-server V6.4.1 (THE-151 section 3.3).
NOT_FOUND_ERROR = (
    'HTTP error 404: {"error":"Class com.nurilab.dummy.TestClass not found"}'
)
UNAVAILABLE_ERROR = (
    "Cannot connect to JADX plugin at http://127.0.0.1:8650. "
    "Ensure JADX-GUI is running and the AI MCP plugin is active."
)
TIMEOUT_ERROR = (
    "Request to JADX plugin timed out after 60.0s for endpoint 'class-source'. "
    "The operation may still be running in JADX-GUI. "
    "For large APKs, code-level searches can take several minutes."
)


def test_external_tool_call_statuses_match_the_151_contract() -> None:
    """Status values must stay in sync with THE-151 section 5.3."""

    assert ALLOWED_EXTERNAL_TOOL_CALL_STATUSES == {
        "success",
        "empty",
        "not_found",
        "unavailable",
        "timeout",
        "tool_error",
        "malformed",
        "invalid_input",
        "not_allowed",
    }


def test_external_tool_call_defaults_leave_provenance_unset() -> None:
    """A failed call can be recorded with required fields only; unknowns stay empty."""

    call = ExternalToolCall(
        server_url=SERVER_URL,
        tool="get_class_source",
        status="unavailable",
        called_at=CALLED_AT,
    )

    assert call.arguments == {}
    assert call.target is None
    assert call.reason is None
    assert call.server_name is None
    assert call.server_version is None
    assert call.expected_release is None
    assert call.client_sdk is None
    assert call.duration_ms is None
    assert call.content is None
    assert call.response_size_bytes is None
    assert call.truncated is False


def test_external_tool_call_to_dict_is_json_serializable() -> None:
    """A fully populated call converts to JSON without losing or renaming keys."""

    call = ExternalToolCall(
        server_url=SERVER_URL,
        tool="get_class_source",
        status="success",
        called_at=CALLED_AT,
        arguments={"class_name": "com.nurilab.mcpprobe.MainActivity"},
        target="mcpprobe-debug.apk",
        server_name="JADX-AI-MCP Plugin Reverse Engineering Server",
        expected_release="jadx-ai-mcp V6.4.1",
        client_sdk="mcp 2.2.0",
        duration_ms=42,
        content="package com.nurilab.mcpprobe;",
        response_size_bytes=29,
    )

    payload = call.to_dict()

    assert json.loads(json.dumps(payload)) == payload
    # Key names become the JSON report contract, so pin the full set.
    assert set(payload) == {
        "server_url",
        "tool",
        "status",
        "called_at",
        "arguments",
        "target",
        "reason",
        "server_name",
        "server_version",
        "expected_release",
        "client_sdk",
        "duration_ms",
        "content",
        "response_size_bytes",
        "truncated",
    }


def test_external_tool_call_rejects_unknown_status() -> None:
    """An unknown status is a NuriLab bug, so construction fails loudly."""

    with pytest.raises(ValueError, match="Unknown external tool call status"):
        ExternalToolCall(
            server_url=SERVER_URL,
            tool="get_class_source",
            status="ok",
            called_at=CALLED_AT,
        )


@pytest.mark.parametrize(
    "class_name",
    [
        "com.nurilab.mcpprobe.MainActivity",
        "com.example.Outer$Inner",
        "a" * JADX_MCP_CLASS_NAME_MAX_LENGTH,
    ],
)
def test_validate_class_name_accepts_contract_names(class_name: str) -> None:
    """Fully qualified names, inner classes, and the max length are accepted."""

    assert validate_class_name(class_name) is None


@pytest.mark.parametrize(
    ("class_name", "expected_reason"),
    [
        ("", "empty"),
        ("a" * (JADX_MCP_CLASS_NAME_MAX_LENGTH + 1), "exceeds"),
        ("com/example/Main", "may only contain"),
        ("com.example Main", "may only contain"),
        ("com.example.Main;rm", "may only contain"),
    ],
)
def test_validate_class_name_rejects_unsafe_names(
    class_name: str, expected_reason: str
) -> None:
    """Empty, too long, or disallowed characters are rejected before any call."""

    reason = validate_class_name(class_name)

    assert reason is not None
    assert expected_reason in reason


def test_check_tool_allowed_accepts_only_get_class_source() -> None:
    """Only the read-only allowlisted tool passes; write tools are refused."""

    assert check_tool_allowed("get_class_source") is None
    reason = check_tool_allowed("rename_class")
    assert reason is not None
    assert "rename_class" in reason


@pytest.mark.parametrize(
    ("structured", "text", "expected"),
    [
        ({"response": "a"}, '{"response": "b"}', {"response": "a"}),
        (None, '{"response": "b"}', {"response": "b"}),
        (None, "not json", None),
        (None, '["response"]', None),
        (None, None, None),
    ],
)
def test_extract_payload_prefers_structured_then_json_text(
    structured: object, text: str | None, expected: dict[str, str] | None
) -> None:
    """structuredContent wins; otherwise text is parsed; non-objects give None."""

    assert extract_payload(structured, text) == expected


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ("not a dict", "malformed"),
        ({}, "malformed"),
        ({"response": 123}, "malformed"),
        ({"response": ""}, "empty"),
        ({"response": "package com.nurilab.mcpprobe;"}, "success"),
        ({"error": NOT_FOUND_ERROR}, "not_found"),
        ({"error": UNAVAILABLE_ERROR}, "unavailable"),
        ({"error": TIMEOUT_ERROR}, "timeout"),
        (
            {"error": "HTTP error 500: Internal error retrieving class source"},
            "tool_error",
        ),
    ],
)
def test_classify_payload_maps_payloads_to_contract_status(
    payload: object, expected_status: str
) -> None:
    """Each payload shape from THE-151 section 3.3 maps to one status."""

    result = classify_payload(payload)

    assert result.status == expected_status
    assert result.status in ALLOWED_EXTERNAL_TOOL_CALL_STATUSES


def test_classify_payload_keeps_error_message_as_reason() -> None:
    """Failures keep the server's message as reason and carry no content."""

    result = classify_payload({"error": NOT_FOUND_ERROR})

    assert result.reason == NOT_FOUND_ERROR
    assert result.content is None
    assert result.response_size_bytes is None


def test_classify_payload_records_success_content_and_size() -> None:
    """A small source is kept whole with its UTF-8 byte size."""

    source = "// 한글 주석\nclass A {}"

    result = classify_payload({"response": source})

    assert result.content == source
    assert result.response_size_bytes == len(source.encode("utf-8"))
    assert result.truncated is False
    assert result.reason is None


def test_classify_payload_keeps_content_at_exact_limit() -> None:
    """A source of exactly 1 MiB is not truncated."""

    source = "a" * JADX_MCP_MAX_CONTENT_BYTES

    result = classify_payload({"response": source})

    assert result.content == source
    assert result.truncated is False


def test_classify_payload_truncates_without_splitting_multibyte_char() -> None:
    """Over 1 MiB is cut on a character boundary and the original size is kept."""

    # "가" is 3 UTF-8 bytes, so it straddles the 1 MiB cut and must be dropped.
    source = "a" * (JADX_MCP_MAX_CONTENT_BYTES - 1) + "가"

    result = classify_payload({"response": source})

    assert result.status == "success"
    assert result.truncated is True
    assert result.content == "a" * (JADX_MCP_MAX_CONTENT_BYTES - 1)
    assert result.response_size_bytes == JADX_MCP_MAX_CONTENT_BYTES + 2


def test_classify_payload_does_not_raise_on_lone_surrogate() -> None:
    """A lone surrogate from JSON decoding must not crash the pipeline."""

    result = classify_payload({"response": "class A {} \ud800"})

    assert result.status == "success"
