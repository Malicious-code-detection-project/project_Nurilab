"""MCP client that calls jadx-ai-mcp's ``get_class_source`` tool.

NuriLab never starts the MCP server; it connects to an already-running
``jadx-mcp-server --http`` endpoint (THE-151 section 2). Every outcome,
including connection failures and timeouts, is returned as an
``ExternalToolCall`` record instead of being raised to the pipeline.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol

import anyio
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from project_nurilab.config import (
    DEFAULT_JADX_MCP_URL,
    JADX_MCP_CALL_TIMEOUT_SECONDS,
    JADX_MCP_CONNECT_TIMEOUT_SECONDS,
    JADX_MCP_EXPECTED_RELEASE,
)
from project_nurilab.external.jadx_mcp import (
    ClassifiedPayload,
    check_tool_allowed,
    classify_is_error,
    classify_payload,
    extract_payload,
    validate_class_name,
)
from project_nurilab.schemas import ExternalToolCall


class McpSession(Protocol):
    """The subset of ``mcp.ClientSession`` this client relies on."""

    async def initialize(self) -> types.InitializeResult:
        """Run the MCP handshake and return the server identity."""

    async def list_tools(
        self, *, params: types.PaginatedRequestParams | None = None
    ) -> types.ListToolsResult:
        """Return one page of the tools the server provides."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> object:
        """Invoke one tool and return the raw MCP result."""


# Opens a session for a URL; tests swap in fakes, production uses streamable HTTP.
SessionFactory = Callable[[str], AbstractAsyncContextManager[McpSession]]


@asynccontextmanager
async def open_streamable_http_session(url: str) -> AsyncGenerator[McpSession, None]:
    """Open an MCP client session over streamable HTTP."""

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            yield session


@dataclass(slots=True)
class _CallOutcome:
    """Classified result plus server identity gathered during one call."""

    classified: ClassifiedPayload
    server_name: str | None = None
    server_version: str | None = None


class JadxMcpClient:
    """Call one allowlisted jadx-ai-mcp tool and record the outcome."""

    def __init__(
        self,
        url: str | None = None,
        connect_timeout: float = JADX_MCP_CONNECT_TIMEOUT_SECONDS,
        call_timeout: float = JADX_MCP_CALL_TIMEOUT_SECONDS,
        session_factory: SessionFactory | None = None,
    ) -> None:
        """Resolve the endpoint (argument, NURILAB_JADX_MCP_URL, default) and limits."""

        self.url = url or os.getenv("NURILAB_JADX_MCP_URL") or DEFAULT_JADX_MCP_URL
        self.connect_timeout = connect_timeout
        self.call_timeout = call_timeout
        self.session_factory = session_factory or open_streamable_http_session

    def call_tool(
        self, tool: str, class_name: str, target: str | None = None
    ) -> ExternalToolCall:
        """Call ``tool`` with ``class_name`` and return the recorded outcome."""

        called_at = datetime.now(UTC).isoformat()
        started = time.perf_counter()

        rejection = check_tool_allowed(tool)
        if rejection is not None:
            outcome = _CallOutcome(ClassifiedPayload("not_allowed", reason=rejection))
        else:
            rejection = validate_class_name(class_name)
            if rejection is not None:
                outcome = _CallOutcome(
                    ClassifiedPayload("invalid_input", reason=rejection)
                )
            else:
                outcome = anyio.run(self._call_async, tool, class_name)

        classified = outcome.classified
        return ExternalToolCall(
            server_url=self.url,
            tool=tool,
            status=classified.status,
            called_at=called_at,
            arguments={"class_name": class_name},
            target=target,
            reason=classified.reason,
            server_name=outcome.server_name,
            server_version=outcome.server_version,
            expected_release=JADX_MCP_EXPECTED_RELEASE,
            client_sdk=_client_sdk(),
            duration_ms=int((time.perf_counter() - started) * 1000),
            content=classified.content,
            response_size_bytes=classified.response_size_bytes,
            truncated=classified.truncated,
        )

    async def _call_async(self, tool: str, class_name: str) -> _CallOutcome:
        """Connect, check capability, and call the tool within the time limits."""

        outcome = _CallOutcome(ClassifiedPayload("unavailable"))
        phase = "connect"
        result: object = None
        # One cancel scope whose deadline moves between phases keeps anyio's
        # scopes nested correctly around the transport's own task group.
        with anyio.CancelScope() as scope:
            scope.deadline = anyio.current_time() + self.connect_timeout
            try:
                async with self.session_factory(self.url) as session:
                    init = await session.initialize()
                    outcome.server_name = init.server_info.name
                    outcome.server_version = init.server_info.version
                    if tool not in await _list_tool_names(session):
                        outcome.classified = ClassifiedPayload(
                            "unavailable",
                            reason=f"Server does not provide tool {tool!r}.",
                        )
                        return outcome
                    phase = "call"
                    scope.deadline = anyio.current_time() + self.call_timeout
                    result = await session.call_tool(tool, {"class_name": class_name})
                    phase = "done"
            except Exception as exc:  # failures become records, never raise
                if phase != "done":
                    leaf = _leaf_exception(exc)
                    if isinstance(leaf, TimeoutError):
                        status = "timeout"
                    else:
                        status = "unavailable" if phase == "connect" else "tool_error"
                    outcome.classified = ClassifiedPayload(
                        status, reason=f"{phase} failed: {_describe(leaf)}"
                    )
                    return outcome

        if phase != "done":
            limit = self.connect_timeout if phase == "connect" else self.call_timeout
            outcome.classified = ClassifiedPayload(
                "timeout", reason=f"{phase} exceeded {limit:g}s limit."
            )
            return outcome

        outcome.classified = _classify_result(result)
        return outcome


async def _list_tool_names(session: McpSession) -> set[str]:
    """Collect tool names across every list_tools page."""

    names: set[str] = set()
    cursor: str | None = None
    while True:
        params = types.PaginatedRequestParams(cursor=cursor) if cursor else None
        page = await session.list_tools(params=params)
        names.update(tool.name for tool in page.tools)
        cursor = page.next_cursor
        if not cursor:
            return names


def _classify_result(result: object) -> ClassifiedPayload:
    """Turn a raw MCP call result into a contract status."""

    if not isinstance(result, types.CallToolResult):
        return ClassifiedPayload(
            "malformed", reason=f"Unexpected MCP result type {type(result).__name__}."
        )
    text = next(
        (
            block.text
            for block in result.content
            if isinstance(block, types.TextContent)
        ),
        None,
    )
    if result.is_error:
        return classify_is_error(text)
    return classify_payload(extract_payload(result.structured_content, text))


def _leaf_exception(exc: BaseException) -> BaseException:
    """Unwrap (nested) exception groups to the first underlying error."""

    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def _describe(exc: BaseException) -> str:
    """Format an exception as a short ``Type: message`` reason."""

    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _client_sdk() -> str:
    """Return the installed MCP client SDK version for provenance."""

    try:
        return f"mcp {version('mcp')}"
    except PackageNotFoundError:
        return "mcp (unknown version)"
