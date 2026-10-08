from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

import anyio
import pytest
from mcp import types

from project_nurilab.config import (
    DEFAULT_JADX_MCP_URL,
    JADX_MCP_CLASS_NAME_MAX_LENGTH,
    JADX_MCP_EXPECTED_RELEASE,
    JADX_MCP_MAX_CONTENT_BYTES,
)
from project_nurilab.external.jadx_mcp import (
    MCP_TOOL_ERROR_PREFIX,
    check_tool_allowed,
    classify_is_error,
    classify_payload,
    extract_payload,
    validate_class_name,
)
from project_nurilab.external.jadx_mcp_client import (
    JadxMcpClient,
    McpSession,
    SessionFactory,
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


def test_external_tool_call_repr_hides_untrusted_content() -> None:
    """repr() omits the returned source so logs and assertion output never show it."""

    call = ExternalToolCall(
        server_url=SERVER_URL,
        tool="get_class_source",
        status="success",
        called_at=CALLED_AT,
        content="SYNTHETIC_SOURCE_MARKER",
    )

    assert "SYNTHETIC_SOURCE_MARKER" not in repr(call)
    assert call.to_dict()["content"] == "SYNTHETIC_SOURCE_MARKER"


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
    """A source exactly at the content limit is not truncated."""

    source = "a" * JADX_MCP_MAX_CONTENT_BYTES

    result = classify_payload({"response": source})

    assert result.content == source
    assert result.truncated is False


def test_classify_payload_truncates_without_splitting_multibyte_char() -> None:
    """Over the limit is cut on a character boundary; the original size is kept."""

    # "가" is 3 UTF-8 bytes, so it straddles the cut and must be dropped.
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


def test_classify_is_error_prefixes_reason_with_mcp_source() -> None:
    """isError results become tool_error with a prefix marking the MCP source."""

    message = (
        "1 validation error for call[get_class_source]\n"
        "class_name\n  Missing required argument"
    )

    result = classify_is_error(message)

    assert result.status == "tool_error"
    assert result.reason == MCP_TOOL_ERROR_PREFIX + message
    assert result.content is None


@pytest.mark.parametrize("message", [None, "", "   "])
def test_classify_is_error_handles_missing_message(message: str | None) -> None:
    """An isError result without text still records a readable reason."""

    result = classify_is_error(message)

    assert result.reason == MCP_TOOL_ERROR_PREFIX + "(no message)"


def test_jadx_tool_error_payload_is_not_prefixed() -> None:
    """tool_error reported by jadx itself keeps the server message unprefixed."""

    message = "HTTP error 500: Internal error retrieving class source"

    result = classify_payload({"error": message})

    assert result.status == "tool_error"
    assert result.reason == message


# --- JadxMcpClient with fake MCP sessions -----------------------------------
# Fakes return the same SDK objects the real server produced (THE-151 6.1).

SERVER_NAME = "JADX-AI-MCP Plugin Reverse Engineering Server"


def _text_result(
    payload: dict[str, str] | None, *, text: str | None = None, is_error: bool = False
) -> types.CallToolResult:
    body = text if text is not None else json.dumps(payload)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=body)],
        structured_content=payload,
        is_error=is_error,
    )


class FakeSession:
    def __init__(
        self,
        result: object = None,
        *,
        tool_pages: Sequence[Sequence[str]] = (("get_class_source",),),
        initialize_delay: float = 0.0,
        call_delay: float = 0.0,
        call_error: Exception | None = None,
    ) -> None:
        self.result = result
        self.tool_pages = tool_pages
        self.initialize_delay = initialize_delay
        self.call_delay = call_delay
        self.call_error = call_error
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def initialize(self) -> types.InitializeResult:
        await anyio.sleep(self.initialize_delay)
        return types.InitializeResult(
            protocol_version="2025-11-25",
            capabilities=types.ServerCapabilities(),
            server_info=types.Implementation(name=SERVER_NAME, version="3.0.2"),
        )

    async def list_tools(
        self, *, params: types.PaginatedRequestParams | None = None
    ) -> types.ListToolsResult:
        page = int(params.cursor) if params and params.cursor else 0
        has_next = page + 1 < len(self.tool_pages)
        return types.ListToolsResult(
            tools=[
                types.Tool(name=name, input_schema={"type": "object"})
                for name in self.tool_pages[page]
            ],
            next_cursor=str(page + 1) if has_next else None,
        )

    async def call_tool(
        self, name: str, arguments: dict[str, object] | None = None
    ) -> object:
        self.calls.append((name, arguments))
        await anyio.sleep(self.call_delay)
        if self.call_error is not None:
            raise self.call_error
        return self.result


def _factory(session: McpSession, opened: list[str]) -> SessionFactory:
    @asynccontextmanager
    async def factory(url: str) -> AsyncGenerator[McpSession, None]:
        opened.append(url)
        yield session

    return factory


def _client(session: McpSession, opened: list[str], **kwargs: float) -> JadxMcpClient:
    return JadxMcpClient(
        url=SERVER_URL, session_factory=_factory(session, opened), **kwargs
    )


@pytest.mark.parametrize(
    ("tool", "class_name", "expected_status"),
    [
        ("rename_class", "com.example.Main", "not_allowed"),
        ("get_class_source", "com/example/Main", "invalid_input"),
    ],
)
def test_client_rejects_before_opening_a_session(
    tool: str, class_name: str, expected_status: str
) -> None:
    """Allowlist and input checks run first, so nothing reaches the server."""

    opened: list[str] = []
    session = FakeSession()

    call = _client(session, opened).call_tool(tool, class_name)

    assert call.status == expected_status
    assert call.reason
    assert opened == []
    assert session.calls == []


def test_client_records_success_with_provenance() -> None:
    """A successful call records content plus server, SDK, timing, and inputs."""

    opened: list[str] = []
    session = FakeSession(_text_result({"response": "class MainActivity {}"}))

    call = _client(session, opened).call_tool(
        "get_class_source",
        "com.nurilab.mcpprobe.MainActivity",
        target="mcpprobe-debug.apk",
    )

    assert call.status == "success"
    assert call.content == "class MainActivity {}"
    assert call.server_url == SERVER_URL
    assert call.server_name == SERVER_NAME
    assert call.server_version == "3.0.2"
    assert call.expected_release == JADX_MCP_EXPECTED_RELEASE
    assert call.client_sdk is not None and call.client_sdk.startswith("mcp ")
    assert call.duration_ms is not None and call.duration_ms >= 0
    assert call.arguments == {"class_name": "com.nurilab.mcpprobe.MainActivity"}
    assert call.target == "mcpprobe-debug.apk"
    assert opened == [SERVER_URL]
    assert session.calls == [
        ("get_class_source", {"class_name": "com.nurilab.mcpprobe.MainActivity"})
    ]


def test_client_falls_back_to_text_without_structured_content() -> None:
    """Without structuredContent the JSON text block is used instead."""

    result = _text_result(None, text=json.dumps({"error": NOT_FOUND_ERROR}))

    call = _client(FakeSession(result), []).call_tool("get_class_source", "A")

    assert call.status == "not_found"
    assert call.reason == NOT_FOUND_ERROR


def test_client_maps_is_error_result_to_prefixed_tool_error() -> None:
    """An isError result from the MCP framework becomes a prefixed tool_error."""

    result = _text_result(None, text="Missing required argument", is_error=True)

    call = _client(FakeSession(result), []).call_tool("get_class_source", "A")

    assert call.status == "tool_error"
    assert call.reason == MCP_TOOL_ERROR_PREFIX + "Missing required argument"


def test_client_reports_unavailable_when_tool_is_not_provided() -> None:
    """Capability check: a server without the tool is unavailable and not called."""

    session = FakeSession(tool_pages=(("get_all_classes",),))

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "unavailable"
    assert call.reason is not None and "does not provide" in call.reason
    assert call.server_version == "3.0.2"
    assert session.calls == []


def test_client_finds_tool_on_a_later_tools_page() -> None:
    """The capability check follows list_tools pagination."""

    session = FakeSession(
        _text_result({"response": "class A {}"}),
        tool_pages=(("get_all_classes",), ("get_class_source",)),
    )

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "success"


def test_client_reports_unavailable_on_connection_error() -> None:
    """A transport error group becomes unavailable with the leaf cause as reason."""

    @asynccontextmanager
    async def refusing_factory(url: str) -> AsyncGenerator[McpSession, None]:
        raise ExceptionGroup("transport", [ConnectionError("connection refused")])
        yield FakeSession()  # pragma: no cover - makes this an async generator

    client = JadxMcpClient(url=SERVER_URL, session_factory=refusing_factory)

    call = client.call_tool("get_class_source", "A")

    assert call.status == "unavailable"
    assert call.reason == "connect failed: ConnectionError: connection refused"
    assert call.server_name is None


def test_client_reports_tool_error_when_call_raises() -> None:
    """An exception during the tool call is a tool_error, not a crash."""

    session = FakeSession(call_error=RuntimeError("stream closed"))

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "tool_error"
    assert call.reason == "call failed: RuntimeError: stream closed"


def test_client_times_out_during_initialize() -> None:
    """A slow handshake hits the connect limit and records a timeout."""

    session = FakeSession(initialize_delay=1.0)

    call = _client(session, [], connect_timeout=0.01).call_tool("get_class_source", "A")

    assert call.status == "timeout"
    assert call.reason is not None and call.reason.startswith("connect exceeded")
    assert session.calls == []


def test_client_times_out_during_call_and_keeps_server_info() -> None:
    """A slow tool call hits the call limit after the handshake was recorded."""

    session = FakeSession(_text_result({"response": "x"}), call_delay=1.0)

    call = _client(session, [], call_timeout=0.01).call_tool("get_class_source", "A")

    assert call.status == "timeout"
    assert call.reason is not None and call.reason.startswith("call exceeded")
    assert call.server_version == "3.0.2"


def test_client_reports_malformed_for_unexpected_result_type() -> None:
    """A non-CallToolResult response is recorded as malformed."""

    session = FakeSession(types.InputRequiredResult(request_state="pending"))

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "malformed"


def test_client_url_comes_from_env_then_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint follows argument, then NURILAB_JADX_MCP_URL, then default."""

    monkeypatch.delenv("NURILAB_JADX_MCP_URL", raising=False)
    assert JadxMcpClient().url == DEFAULT_JADX_MCP_URL

    monkeypatch.setenv("NURILAB_JADX_MCP_URL", "http://127.0.0.1:9999/mcp")
    assert JadxMcpClient().url == "http://127.0.0.1:9999/mcp"
    assert JadxMcpClient(url=SERVER_URL).url == SERVER_URL


def test_client_records_unavailable_inside_running_event_loop() -> None:
    """Inside a running loop (e.g. Jupyter) the call is recorded, never raised."""

    opened: list[str] = []
    client = _client(FakeSession(), opened)

    async def call_from_loop() -> ExternalToolCall:
        return client.call_tool("get_class_source", "A")

    call = anyio.run(call_from_loop)

    assert call.status == "unavailable"
    assert call.reason is not None and "running event loop" in call.reason
    assert opened == []
