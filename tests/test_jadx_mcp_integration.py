from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import anyio
import pytest
from mcp import types

from project_nurilab.external.jadx_mcp_client import JadxMcpClient, McpSession
from project_nurilab.schemas import ExternalToolCall


RUN_JADX_MCP = os.getenv("NURILAB_RUN_JADX_MCP") == "1"
# Default is a class that never exists; set a real class once an APK is loaded.
CLASS_NAME = os.getenv("NURILAB_JADX_MCP_CLASS", "com.nurilab.dummy.TestClass")
SERVER_NAME = "JADX-AI-MCP Plugin Reverse Engineering Server"
# Statuses that only come from a jadx payload returned by a real tool call.
JADX_PAYLOAD_STATUSES = {"success", "empty", "not_found"}
# `unavailable` is a jadx payload only when the plugin itself is unreachable;
# client-side connect and capability failures carry other reasons.
PLUGIN_UNAVAILABLE_PREFIX = "Cannot connect to JADX plugin"

requires_real_server = pytest.mark.skipif(
    not RUN_JADX_MCP,
    reason="set NURILAB_RUN_JADX_MCP=1 to call an existing jadx-mcp-server",
)


def answered_by_jadx(call: ExternalToolCall) -> bool:
    """Whether get_class_source was really called and jadx answered per contract.

    jadx's own error payloads (``tool_error``) are real calls too, but they are not
    an expected answer, so they count as failures here.
    """

    if call.status in JADX_PAYLOAD_STATUSES:
        return True
    return call.status == "unavailable" and (call.reason or "").startswith(
        PLUGIN_UNAVAILABLE_PREFIX
    )


# Reason prefixes mapped to category names, so failures stay diagnosable
# without printing the raw reason (it can carry URLs or server text).
_REASON_CATEGORIES = (
    (PLUGIN_UNAVAILABLE_PREFIX, "plugin_unreachable"),
    ("HTTP error 404", "class_not_found"),
    ("Request to JADX plugin timed out", "jadx_timeout"),
    ("connect failed", "connect_failed"),
    ("connect exceeded", "connect_timeout"),
    ("call failed", "call_failed"),
    ("call exceeded", "call_timeout"),
    ("Server does not provide tool", "tool_missing"),
    ("Cannot call MCP from inside a running event loop", "event_loop"),
    ("MCP tool error", "mcp_tool_error"),
)


def reason_category(call: ExternalToolCall) -> str:
    """Classify the reason into a fixed name; the raw text is never returned."""

    if not call.reason:
        return "none"
    for prefix, category in _REASON_CATEGORIES:
        if call.reason.startswith(prefix):
            return category
    return "other"


def diagnostic_summary(call: ExternalToolCall) -> str:
    """Metadata-only line for -s runs: no source, URL, arguments, or raw reason."""

    return (
        f"status={call.status} reason_category={reason_category(call)} "
        f"server_version={call.server_version} "
        f"response_size_bytes={call.response_size_bytes} "
        f"truncated={call.truncated} duration_ms={call.duration_ms}"
    )


# --- Real server tests (opt-in) ----------------------------------------------
# Assertions use extracted values so a failure never prints the whole record.


@pytest.mark.jadx_mcp_integration
@requires_real_server
def test_real_jadx_mcp_server_initializes_and_answers_get_class_source() -> None:
    """A real server completes the handshake and jadx answers the allowlisted tool."""

    call = JadxMcpClient().call_tool("get_class_source", CLASS_NAME)
    summary = diagnostic_summary(call)
    print(summary)

    server_name = call.server_name
    answered = answered_by_jadx(call)
    assert server_name == SERVER_NAME
    assert answered, summary


@pytest.mark.jadx_mcp_integration
@requires_real_server
def test_real_jadx_mcp_connect_timeout_cancels_transport_cleanly() -> None:
    """A tiny connect limit ends the real SDK transport as a recorded timeout."""

    # Without this precondition the test passes with no server at all, because the
    # tiny limit fires before a refused connection is even reported.
    reachable_server = JadxMcpClient().call_tool("get_class_source", CLASS_NAME)
    server_name = reachable_server.server_name
    assert server_name == SERVER_NAME

    call = JadxMcpClient(connect_timeout=0.001).call_tool(
        "get_class_source", CLASS_NAME
    )

    status, reason = call.status, call.reason or ""
    assert status == "timeout"
    assert reason.startswith("connect exceeded")


@pytest.mark.jadx_mcp_integration
@requires_real_server
def test_real_jadx_mcp_call_timeout_cancels_transport_cleanly() -> None:
    """A tiny call limit times out after the real handshake was recorded."""

    call = JadxMcpClient(call_timeout=0.0001).call_tool("get_class_source", CLASS_NAME)

    status, reason = call.status, call.reason or ""
    has_server_version = call.server_version is not None
    assert status == "timeout"
    assert reason.startswith("call exceeded")
    assert has_server_version


# --- Guards for the real-server judgement (always run) -------------------------


def _record(status: str, reason: str | None = None) -> ExternalToolCall:
    return ExternalToolCall(
        server_url="http://127.0.0.1:8651/mcp",
        tool="get_class_source",
        status=status,
        called_at="2026-10-08T00:00:00+00:00",
        reason=reason,
        server_name=SERVER_NAME,
        server_version="3.0.2",
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("success", None),
        ("empty", None),
        ("not_found", 'HTTP error 404: {"error":"Class A not found"}'),
        ("unavailable", "Cannot connect to JADX plugin at http://127.0.0.1:8650. ..."),
    ],
)
def test_answered_by_jadx_accepts_payloads_from_a_real_tool_call(
    status: str, reason: str | None
) -> None:
    """Statuses that only a jadx payload can produce count as answered."""

    assert answered_by_jadx(_record(status, reason))


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("unavailable", "Server does not provide tool 'get_class_source'."),
        ("unavailable", "connect failed: ConnectError: All connection attempts failed"),
        ("unavailable", "Cannot call MCP from inside a running event loop."),
        ("timeout", "call exceeded 15s limit."),
        ("tool_error", "MCP tool error: Missing required argument"),
        ("invalid_input", "class_name is empty."),
    ],
)
def test_answered_by_jadx_rejects_failures_before_a_jadx_payload(
    status: str, reason: str
) -> None:
    """Client-side and framework failures never pass as a jadx answer."""

    assert not answered_by_jadx(_record(status, reason))


def test_answered_by_jadx_fails_when_server_lacks_the_tool() -> None:
    """Reviewer case: same server identity, empty tool list, no call_tool made."""

    calls: list[str] = []

    class NoToolSession:
        async def initialize(self) -> types.InitializeResult:
            return types.InitializeResult(
                protocol_version="2025-11-25",
                capabilities=types.ServerCapabilities(),
                server_info=types.Implementation(name=SERVER_NAME, version="3.0.2"),
            )

        async def list_tools(
            self, *, params: types.PaginatedRequestParams | None = None
        ) -> types.ListToolsResult:
            return types.ListToolsResult(tools=[])

        async def call_tool(
            self, name: str, arguments: dict[str, Any] | None = None
        ) -> object:
            calls.append(name)
            return None

    @asynccontextmanager
    async def factory(url: str) -> AsyncGenerator[McpSession, None]:
        yield NoToolSession()

    call = JadxMcpClient(session_factory=factory).call_tool("get_class_source", "A")

    assert call.server_name == SERVER_NAME
    assert calls == []
    assert not answered_by_jadx(call)


def test_diagnostic_summary_excludes_source_and_connection_details() -> None:
    """The printed summary keeps metadata but drops source, URL, args, reason."""

    call = ExternalToolCall(
        server_url="http://10.9.8.7:9999/mcp",
        tool="get_class_source",
        status="success",
        called_at="2026-10-08T00:00:00+00:00",
        arguments={"class_name": "com.synthetic.SecretHolder"},
        reason="see http://10.9.8.7:8650",
        server_version="3.0.2",
        content="SYNTHETIC_SOURCE_MARKER",
        response_size_bytes=23,
    )

    summary = diagnostic_summary(call)

    assert "reason_category=other" in summary
    for leaked in (
        "SYNTHETIC_SOURCE_MARKER",
        "10.9.8.7",
        "com.synthetic.SecretHolder",
    ):
        assert leaked not in summary
    assert "status=success" in summary
    assert "response_size_bytes=23" in summary


@pytest.mark.parametrize(
    ("reason", "category"),
    [
        (None, "none"),
        (
            "Cannot connect to JADX plugin at http://127.0.0.1:8650. ...",
            "plugin_unreachable",
        ),
        ('HTTP error 404: {"error":"Class A not found"}', "class_not_found"),
        (
            "connect failed: ConnectError: All connection attempts failed",
            "connect_failed",
        ),
        ("connect exceeded 10s limit.", "connect_timeout"),
        ("call exceeded 15s limit.", "call_timeout"),
        ("Server does not provide tool 'get_class_source'.", "tool_missing"),
        ("Cannot call MCP from inside a running event loop.", "event_loop"),
        ("MCP tool error: Missing required argument", "mcp_tool_error"),
        ("call failed: RuntimeError: stream closed", "call_failed"),
        (
            "Request to JADX plugin timed out after 60.0s for endpoint 'class-source'.",
            "jadx_timeout",
        ),
    ],
)
def test_reason_category_names_failures_without_raw_text(
    reason: str | None, category: str
) -> None:
    """Each known reason maps to a category name that carries no URL or text."""

    record = _record("unavailable", reason)

    assert reason_category(record) == category
    assert "127.0.0.1" not in diagnostic_summary(record)


class _ScriptedSession:
    """Fake MCP session that fails in one configurable way."""

    def __init__(
        self,
        *,
        tools: tuple[str, ...] = ("get_class_source",),
        initialize_delay: float = 0.0,
        call_delay: float = 0.0,
        call_error: Exception | None = None,
        result: object = None,
    ) -> None:
        self.tools = tools
        self.initialize_delay = initialize_delay
        self.call_delay = call_delay
        self.call_error = call_error
        self.result = result

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
        return types.ListToolsResult(
            tools=[
                types.Tool(name=name, input_schema={"type": "object"})
                for name in self.tools
            ]
        )

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> object:
        await anyio.sleep(self.call_delay)
        if self.call_error is not None:
            raise self.call_error
        return self.result


def _client_reason(scenario: str) -> ExternalToolCall:
    """Run the real client into one failure and return the record it produced."""

    session = _ScriptedSession()
    connect_timeout, call_timeout = 10.0, 15.0
    if scenario == "connect_failed":

        @asynccontextmanager
        async def refusing(url: str) -> AsyncGenerator[McpSession, None]:
            raise ExceptionGroup("transport", [ConnectionError("refused")])
            yield session  # pragma: no cover - makes this an async generator

        return JadxMcpClient(session_factory=refusing).call_tool(
            "get_class_source", "A"
        )
    if scenario == "tool_missing":
        session = _ScriptedSession(tools=())
    elif scenario == "call_failed":
        session = _ScriptedSession(call_error=RuntimeError("stream closed"))
    elif scenario == "connect_timeout":
        session = _ScriptedSession(initialize_delay=1.0)
        connect_timeout = 0.01
    elif scenario == "call_timeout":
        session = _ScriptedSession(call_delay=1.0)
        call_timeout = 0.01
    elif scenario == "mcp_tool_error":
        session = _ScriptedSession(
            result=types.CallToolResult(
                content=[types.TextContent(type="text", text="bad argument")],
                is_error=True,
            )
        )

    @asynccontextmanager
    async def factory(url: str) -> AsyncGenerator[McpSession, None]:
        yield session

    client = JadxMcpClient(
        connect_timeout=connect_timeout,
        call_timeout=call_timeout,
        session_factory=factory,
    )
    if scenario == "event_loop":

        async def call_from_loop() -> ExternalToolCall:
            return client.call_tool("get_class_source", "A")

        return anyio.run(call_from_loop)
    return client.call_tool("get_class_source", "A")


@pytest.mark.parametrize(
    "scenario",
    [
        "connect_failed",
        "tool_missing",
        "call_failed",
        "connect_timeout",
        "call_timeout",
        "mcp_tool_error",
        "event_loop",
    ],
)
def test_reason_category_matches_reasons_the_client_produces(scenario: str) -> None:
    """Categories track the client's real wording, so a reworded reason fails here."""

    assert reason_category(_client_reason(scenario)) == scenario
