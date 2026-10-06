from __future__ import annotations

import os

import pytest

from project_nurilab.external.jadx_mcp_client import JadxMcpClient


RUN_JADX_MCP = os.getenv("NURILAB_RUN_JADX_MCP") == "1"
# Default is a class that never exists; set a real class once an APK is loaded.
CLASS_NAME = os.getenv("NURILAB_JADX_MCP_CLASS", "com.nurilab.dummy.TestClass")
# Statuses that prove the server answered with a jadx payload.
JADX_ANSWERED_STATUSES = {"success", "empty", "not_found", "unavailable"}

pytestmark = [
    pytest.mark.jadx_mcp_integration,
    pytest.mark.skipif(
        not RUN_JADX_MCP,
        reason="set NURILAB_RUN_JADX_MCP=1 to call an existing jadx-mcp-server",
    ),
]


def test_real_jadx_mcp_server_initializes_and_answers_get_class_source() -> None:
    """A real server completes the handshake and answers the allowlisted tool."""

    call = JadxMcpClient().call_tool("get_class_source", CLASS_NAME)

    print(call.to_dict())
    assert call.server_name == "JADX-AI-MCP Plugin Reverse Engineering Server"
    assert call.server_version is not None
    assert call.status in JADX_ANSWERED_STATUSES


def test_real_jadx_mcp_connect_timeout_cancels_transport_cleanly() -> None:
    """A tiny connect limit ends the real SDK transport as a recorded timeout."""

    call = JadxMcpClient(connect_timeout=0.001).call_tool(
        "get_class_source", CLASS_NAME
    )

    assert call.status == "timeout"
    assert call.reason is not None and call.reason.startswith("connect exceeded")


def test_real_jadx_mcp_call_timeout_cancels_transport_cleanly() -> None:
    """A tiny call limit times out after the real handshake was recorded."""

    call = JadxMcpClient(call_timeout=0.0001).call_tool("get_class_source", CLASS_NAME)

    assert call.status == "timeout"
    assert call.reason is not None and call.reason.startswith("call exceeded")
    assert call.server_version is not None
