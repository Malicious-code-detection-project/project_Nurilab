from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

import anyio
import pytest
import httpx2
from mcp import ClientSession, MCPError, types
from mcp.client.streamable_http import streamable_http_client

from project_nurilab.config import (
    DEFAULT_JADX_MCP_URL,
    JADX_MCP_CLASS_NAME_MAX_LENGTH,
    JADX_MCP_EXPECTED_RELEASE,
    JADX_MCP_MAX_CONTENT_BYTES,
    JADX_MCP_MAX_REASON_BYTES,
    JADX_MCP_MAX_SERVER_INFO_BYTES,
)
from project_nurilab.external.jadx_mcp import (
    MCP_TOOL_ERROR_PREFIX,
    cap_reason,
    check_tool_allowed,
    classify_is_error,
    classify_payload,
    extract_payload,
    validate_class_name,
)
from project_nurilab.external.jadx_mcp_client import (
    TRANSPORT_LIMIT_NOTE,
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
    assert call.target_verified is False
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
        "target_verified",
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
    """A lone surrogate becomes "?" so the source can later be written as UTF-8."""

    result = classify_payload({"response": "class A {} \ud800"})

    assert result.status == "success"
    assert result.content == "class A {} ?"
    assert result.content is not None
    result.content.encode("utf-8")


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
        initialize_error: Exception | None = None,
        call_delay: float = 0.0,
        call_error: Exception | None = None,
        server_name: str = SERVER_NAME,
        server_version: str = "3.0.2",
    ) -> None:
        self.result = result
        self.server_name = server_name
        self.server_version = server_version
        self.tool_pages = tool_pages
        self.initialize_delay = initialize_delay
        self.initialize_error = initialize_error
        self.call_delay = call_delay
        self.call_error = call_error
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def initialize(self) -> types.InitializeResult:
        await anyio.sleep(self.initialize_delay)
        if self.initialize_error is not None:
            raise self.initialize_error
        return types.InitializeResult(
            protocol_version="2025-11-25",
            capabilities=types.ServerCapabilities(),
            server_info=types.Implementation(
                name=self.server_name, version=self.server_version
            ),
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


def test_client_records_malformed_when_classification_raises() -> None:
    """Deeply nested JSON text makes json.loads raise; it is malformed, not a crash."""

    nested = "[" * 10_000 + "0" + "]" * 10_000
    result = types.CallToolResult(content=[types.TextContent(type="text", text=nested)])

    call = _client(FakeSession(result), []).call_tool("get_class_source", "A")

    assert call.status == "malformed"
    assert call.reason is not None
    assert call.reason.startswith("classify failed: RecursionError")
    assert call.server_name == SERVER_NAME
    assert call.server_version == "3.0.2"


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


@pytest.mark.parametrize("error", [None, {"detail": "x"}, 404])
def test_classify_payload_treats_non_string_error_as_malformed(error: object) -> None:
    """An 'error' that is not a string is an unexpected shape, like 'response'."""

    result = classify_payload({"error": error})

    assert result.status == "malformed"
    assert result.reason == "Tool result 'error' is not a string."


def test_cap_reason_keeps_short_reasons_and_cuts_long_ones() -> None:
    """Reasons over the byte limit keep their head and record the original size."""

    long_reason = "x" * 300_000

    capped = cap_reason(long_reason)

    assert cap_reason(None) is None
    assert cap_reason("short") == "short"
    assert capped is not None
    assert capped.startswith("x" * JADX_MCP_MAX_REASON_BYTES)
    assert capped.endswith("... (truncated, 300000 bytes)")
    assert len(capped.encode("utf-8")) < JADX_MCP_MAX_REASON_BYTES + 64


def test_client_caps_long_server_error_reason() -> None:
    """A huge jadx error is stored and printed only up to the reason limit."""

    session = FakeSession(_text_result({"error": "E" * 300_000}))

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "tool_error"
    assert call.reason is not None
    assert call.reason.endswith("(truncated, 300000 bytes)")
    assert len(call.reason.encode("utf-8")) < JADX_MCP_MAX_REASON_BYTES + 64


def test_client_keeps_success_when_session_close_fails() -> None:
    """An error while closing the session after the call must not drop the result."""

    session = FakeSession(_text_result({"response": "class A {}"}))

    @asynccontextmanager
    async def closing_fails(url: str) -> AsyncGenerator[McpSession, None]:
        yield session
        raise RuntimeError("terminate request failed")

    client = JadxMcpClient(url=SERVER_URL, session_factory=closing_fails)

    call = client.call_tool("get_class_source", "A")

    assert call.status == "success"
    assert call.content == "class A {}"


def test_client_maps_timeout_error_from_call_to_timeout() -> None:
    """A TimeoutError raised inside the call is recorded as timeout, not tool_error."""

    session = FakeSession(call_error=TimeoutError("read timed out"))

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "timeout"
    assert call.reason == "call failed: TimeoutError: read timed out"


def test_cap_reason_cleans_lone_surrogate_in_short_reason() -> None:
    """A short reason is not cut but still loses lone surrogates."""

    capped = cap_reason("bad \ud800 data")

    assert capped == "bad ? data"
    assert capped is not None
    capped.encode("utf-8")


def test_cap_reason_cuts_by_bytes_not_characters() -> None:
    """Korean text (3 bytes each) is cut at the byte limit on a character boundary."""

    reason = "가" * 2000  # 6000 UTF-8 bytes, 2000 characters

    capped = cap_reason(reason)

    kept_chars = JADX_MCP_MAX_REASON_BYTES // 3
    assert capped == "가" * kept_chars + "... (truncated, 6000 bytes)"


def test_external_tool_call_replaces_lone_surrogates_in_every_text_field() -> None:
    """Any producer's record can be written as UTF-8, whatever text it was given."""

    bad = "x\udcffy"
    call = ExternalToolCall(
        server_url=f"http://127.0.0.1:8651/{bad}",
        tool="get_class_source",
        status="invalid_input",
        called_at=CALLED_AT,
        arguments={f"key{bad}": f"Bad{bad}"},
        target=f"app{bad}.apk",
        reason=bad,
        server_name=bad,
        server_version=bad,
        expected_release=bad,
        client_sdk=bad,
        content=bad,
    )

    payload = call.to_dict()

    json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert payload["server_url"] == "http://127.0.0.1:8651/x?y"
    assert payload["arguments"] == {"keyx?y": "Badx?y"}
    assert payload["target"] == "appx?y.apk"
    for key in (
        "reason",
        "server_name",
        "server_version",
        "expected_release",
        "client_sdk",
        "content",
    ):
        assert payload[key] == "x?y"


def test_client_records_surrogate_class_name_as_invalid_input() -> None:
    """Undecodable argv bytes are rejected and recorded with "?" in their place."""

    opened: list[str] = []

    call = _client(FakeSession(), opened).call_tool("get_class_source", "Bad\udcff")

    assert opened == []
    assert call.status == "invalid_input"
    assert call.arguments == {"class_name": "Bad?"}


def test_client_cleans_and_caps_server_info() -> None:
    """serverInfo is server-controlled, so it is cleaned and cut like a reason."""

    session = FakeSession(
        _text_result({"response": "class A {}"}),
        server_name="jadx\ud800",
        server_version="9" * 300,
    )

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "success"
    assert call.server_name == "jadx?"
    assert call.server_version == (
        "9" * JADX_MCP_MAX_SERVER_INFO_BYTES + "... (truncated, 300 bytes)"
    )


STREAM_ENDED = "SSE stream ended without a response"


def _stream_ends_on_call(request: httpx2.Request) -> httpx2.Response:
    """MCP over HTTP whose tools/call SSE stream closes before any event."""

    if request.method != "POST":
        return httpx2.Response(200)
    message = json.loads(request.content)
    headers = {"mcp-session-id": "test-session"}
    if "id" not in message:
        return httpx2.Response(202, headers=headers)
    if message["method"] == "initialize":
        result: dict[str, object] = {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": "3.0.2"},
        }
    elif message["method"] == "tools/list":
        result = {
            "tools": [{"name": "get_class_source", "inputSchema": {"type": "object"}}]
        }
    else:
        # What the SDK sees after dropping an SSE event over its 1 MiB limit.
        return httpx2.Response(
            200, headers={**headers, "content-type": "text/event-stream"}, content=b""
        )
    return httpx2.Response(
        200,
        headers=headers,
        json={"jsonrpc": "2.0", "id": message["id"], "result": result},
    )


@asynccontextmanager
async def _offline_sdk_session(url: str) -> AsyncGenerator[McpSession, None]:
    """Real SDK transport and session over an in-memory HTTP handler."""

    transport = httpx2.MockTransport(_stream_ends_on_call)
    async with httpx2.AsyncClient(transport=transport) as http_client:
        async with streamable_http_client(url, http_client=http_client) as streams:
            async with ClientSession(*streams) as session:
                yield session


def test_client_notes_transport_limit_for_real_sdk_stream_end() -> None:
    """The SDK's own stream-end failure gets the note; this breaks if the SDK
    changes its message or error code."""

    client = JadxMcpClient(url=SERVER_URL, session_factory=_offline_sdk_session)

    call = client.call_tool("get_class_source", "A")

    assert call.status == "tool_error"
    assert call.reason == f"call failed: MCPError: {STREAM_ENDED}{TRANSPORT_LIMIT_NOTE}"


def test_client_never_notes_transport_limit_for_server_error_text() -> None:
    """A payload 'error' that copies the client reason stays the server's text."""

    server_text = f"call failed: MCPError: {STREAM_ENDED}"
    session = FakeSession(_text_result({"error": server_text}))

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "tool_error"
    assert call.reason == server_text


@pytest.mark.parametrize(
    "error",
    [
        MCPError(types.CONNECTION_CLOSED, "Connection closed"),
        MCPError(types.INTERNAL_ERROR, STREAM_ENDED),
    ],
    ids=["other-message", "other-code"],
)
def test_client_notes_transport_limit_only_for_exact_sdk_error(
    error: MCPError,
) -> None:
    """Both the SDK error code and message must match before the note is added."""

    session = FakeSession(call_error=error)

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "tool_error"
    assert call.reason is not None
    assert not call.reason.endswith(TRANSPORT_LIMIT_NOTE)


def test_client_notes_transport_limit_only_in_call_phase() -> None:
    """A stream end during connect is a connection failure, not a large response."""

    session = FakeSession(
        initialize_error=MCPError(types.CONNECTION_CLOSED, STREAM_ENDED)
    )

    call = _client(session, []).call_tool("get_class_source", "A")

    assert call.status == "unavailable"
    assert call.reason == f"connect failed: MCPError: {STREAM_ENDED}"
