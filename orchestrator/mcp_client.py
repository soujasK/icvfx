"""Thin async wrapper around the real MCP client SDK for calling the
Phase 5 remediation server's tools over stdio.

Kept separate from run_fault_injection_test.py so the orchestration logic
doesn't need to know anything about MCP session/transport plumbing.

Uses ONE persistent stdio session for the whole orchestrator run (opened via
`async with RemediationClient() as client:`), matching how a real stage
deployment would keep a long-lived MCP session open across many alerts
rather than paying subprocess-spawn cost per incident. Each tool's own
`latency_ms` (returned in its payload) is the number to hold against the
plan's "execution within 100ms of diagnostic verdict" target - the
end-to-end `round_trip_s` measured here also includes local IPC overhead
and is reported separately for transparency.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp-remediation", "server.py")


@dataclass
class RemediationResult:
    ok: bool
    payload: dict[str, Any]
    round_trip_s: float


class RemediationClient:
    async def __aenter__(self) -> "RemediationClient":
        params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT])
        self._stdio_ctx = stdio_client(params)
        read, write = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(read, write)
        self._session: ClientSession = await self._session_ctx.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self._session_ctx.__aexit__(*exc_info)
        await self._stdio_ctx.__aexit__(*exc_info)

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> RemediationResult:
        t0 = time.monotonic()
        result = await self._session.call_tool(tool_name, arguments)
        elapsed = time.monotonic() - t0

        payload: dict[str, Any] = {}
        structured = getattr(result, "structured_content", None)
        if structured:
            payload = structured
        elif result.content:
            first = result.content[0]
            text = getattr(first, "text", None)
            if text:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {"text": text}

        is_err = getattr(result, "isError", False) or getattr(result, "is_error", False)
        return RemediationResult(ok=not is_err, payload=payload, round_trip_s=elapsed)
