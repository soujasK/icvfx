"""Edge-case tests for mcp-remediation/server.py, exercised over a real MCP
stdio session against the actual server process (not a mock).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "orchestrator"))

import mcp_client  # noqa: E402
from mcp_client import RemediationClient  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_SERVER = os.path.join(REPO_ROOT, "mcp-remediation", "server.py")


def _with_isolated_state(async_fn):
    """Runs an async test against a throwaway copy of the server + state
    dir so tests never depend on / clobber each other's stage_state.json,
    and never leave the real repo's state file dirty."""
    def wrapper():
        with tempfile.TemporaryDirectory() as tmp:
            server_copy = os.path.join(tmp, "server.py")
            shutil.copy(REAL_SERVER, server_copy)
            original = mcp_client.SERVER_SCRIPT
            mcp_client.SERVER_SCRIPT = server_copy
            try:
                asyncio.run(async_fn(os.path.join(tmp, "stage_state.json")))
            finally:
                mcp_client.SERVER_SCRIPT = original
    return wrapper


async def _concurrent_hud_calls(n: int):
    async with RemediationClient() as client:
        results = await asyncio.gather(*[
            client.call("notify_stage_hud", {"message": f"concurrent-{i}"}) for i in range(n)
        ])
    return results


@_with_isolated_state
async def test_concurrent_calls_never_lose_audit_log_entries(state_path: str):
    """Regression test for the read-modify-write race found via stress
    testing: without the lock, concurrent calls silently lost entries even
    though every call reported success. This uses a realistic (no
    artificial delay) 25-way concurrent burst - see docs/TEST_REPORT.md for
    the wide-race-window diagnostic that definitively proved the mechanism."""
    n = 25
    results = await _concurrent_hud_calls(n)
    assert all(r.ok for r in results), f"not all calls succeeded: {[r.ok for r in results]}"

    assert os.path.exists(state_path), "server did not write its state file"
    with open(state_path) as f:
        state = json.load(f)
    assert len(state["actions_log"]) == n, (
        f"expected exactly {n} audit-log entries, got {len(state['actions_log'])} "
        f"(concurrent calls lost entries - the state-file lock regressed)"
    )
    messages = sorted(e["args"]["message"] for e in state["actions_log"])
    assert messages == sorted(f"concurrent-{i}" for i in range(n)), "every call's message must be present exactly once"


@_with_isolated_state
async def test_rejects_invalid_filter_mode(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("switch_tracking_estimator", {"camera_id": 1, "filter_mode": "NOT_A_REAL_MODE"})
    assert not result.ok, "server should reject an unrecognized filter_mode"


@_with_isolated_state
async def test_rejects_out_of_range_camera_id(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("switch_tracking_estimator",
                                    {"camera_id": 9999, "filter_mode": "KALMAN_DEAD_RECKONING"})
    assert not result.ok, "server should reject a camera_id outside uint8 range"


@_with_isolated_state
async def test_rejects_out_of_range_overscan_pct(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("clamp_frustum_margin", {"display_node_id": "led-wall-a", "overscan_pct": 250.0})
    assert not result.ok, "server should reject overscan_pct outside 0-100"


@_with_isolated_state
async def test_rejects_negative_overscan_pct(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("clamp_frustum_margin", {"display_node_id": "led-wall-a", "overscan_pct": -5.0})
    assert not result.ok, "server should reject a negative overscan_pct"


@_with_isolated_state
async def test_rejects_empty_display_node_id(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("clamp_frustum_margin", {"display_node_id": "", "overscan_pct": 10.0})
    assert not result.ok, "server should reject an empty display_node_id"


@_with_isolated_state
async def test_rejects_out_of_range_ptp_domain(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("recalibrate_ptp_sync_domain", {"domain_number": -1})
    assert not result.ok, "server should reject a negative PTP domain number"
    async with RemediationClient() as client:
        result2 = await client.call("recalibrate_ptp_sync_domain", {"domain_number": 300})
    assert not result2.ok, "server should reject a PTP domain number above uint8 range"


@_with_isolated_state
async def test_rejects_empty_hud_message(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("notify_stage_hud", {"message": ""})
    assert not result.ok, "server should reject an empty HUD message"


@_with_isolated_state
async def test_rejects_oversized_hud_message(state_path: str):
    async with RemediationClient() as client:
        result = await client.call("notify_stage_hud", {"message": "x" * 5000})
    assert not result.ok, "server should reject a wildly oversized HUD message"


@_with_isolated_state
async def test_valid_call_after_a_rejected_call_still_succeeds(state_path: str):
    """A malformed remediation directive (e.g. from a bad LLM response)
    must not corrupt state for the next, valid, call."""
    async with RemediationClient() as client:
        bad = await client.call("switch_tracking_estimator", {"camera_id": 1, "filter_mode": "GARBAGE"})
        assert not bad.ok
        good = await client.call("switch_tracking_estimator",
                                  {"camera_id": 1, "filter_mode": "KALMAN_DEAD_RECKONING"})
        assert good.ok, f"a valid call after a rejected one should still succeed: {good.payload}"

    with open(state_path) as f:
        state = json.load(f)
    assert len(state["actions_log"]) == 1, "only the valid call should have been recorded"
    assert state["tracking_estimators"]["1"] == "KALMAN_DEAD_RECKONING"


@_with_isolated_state
async def test_rapid_sequential_calls_all_recorded(state_path: str):
    """100 calls in a row on one persistent session (the orchestrator's
    real usage pattern) - throughput/robustness check distinct from the
    concurrency test above."""
    n = 100
    async with RemediationClient() as client:
        for i in range(n):
            result = await client.call("notify_stage_hud", {"message": f"seq-{i}"})
            assert result.ok, f"call {i} failed: {result.payload}"

    with open(state_path) as f:
        state = json.load(f)
    assert len(state["actions_log"]) == n
    assert state["last_hud_message"] == f"seq-{n - 1}"


if __name__ == "__main__":
    from _runner import main
    main(sys.modules[__name__])
