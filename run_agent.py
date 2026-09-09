#!/usr/bin/env python3
"""Scripted, multimodal driver for the Stage Incident Commander ADK agent.

Builds one incident (witness frame + frustum frame + telemetry manifest),
runs it through the agent, and prints the full step-by-step trace: every
tool call + arguments, every tool result, and the agent's final summary.

    python run_agent.py --scenario occlusion
    python run_agent.py --scenario ptp_jitter
    python run_agent.py --scenario dropped_frame
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from stage_agent.agent import root_agent
from stage_agent.incident import EXPECTED_ROOT_CAUSE, build_incident

APP = "icvfx_stage"


async def _create_session(svc: InMemorySessionService, **kw):
    res = svc.create_session(**kw)
    if asyncio.iscoroutine(res):
        return await res
    return res


async def run(scenario: str, camera: int) -> int:
    incident = build_incident(scenario, camera_id=camera)
    expected = EXPECTED_ROOT_CAUSE[scenario]

    print(f"\n=== INCIDENT: {scenario} (camera {camera}) ===")
    print(f"  alert    : {incident.alert_summary}")
    print(f"  manifest : {json.dumps(incident.manifest)}")
    print(f"  expected : {expected}")
    print(f"  frames   : {os.path.relpath(incident.witness_path, _REPO)} | "
          f"{os.path.relpath(incident.frustum_path, _REPO)}")
    print(f"  model    : {root_agent.model}\n")

    session_service = InMemorySessionService()
    runner = Runner(app_name=APP, agent=root_agent, session_service=session_service)
    await _create_session(session_service, app_name=APP, user_id="commander", session_id="s1")

    tool_calls: list[str] = []
    final_text = ""

    async for event in runner.run_async(
        user_id="commander", session_id="s1", new_message=incident.content
    ):
        parts = event.content.parts if event.content else []
        for part in parts:
            fc = getattr(part, "function_call", None)
            fr = getattr(part, "function_response", None)
            if fc:
                tool_calls.append(fc.name)
                print(f"  -> TOOL CALL   {fc.name}({dict(fc.args)})")
            if fr:
                print(f"  <- TOOL RESULT {fr.name}: {json.dumps(fr.response, default=str)}")
            if getattr(part, "text", None) and event.is_final_response():
                final_text = part.text.strip()

    print("\n=== AGENT SUMMARY ===")
    print(final_text or "(no final text)")
    print(f"\ntools called : {tool_calls}")

    state_path = os.path.join(_REPO, "mcp-remediation", "stage_state.json")
    if os.path.exists(state_path):
        with open(state_path) as f:
            log = json.load(f).get("actions_log", [])
        print("last stage actions:")
        for e in log[-4:]:
            print(f"  {e['executed_at']}  {e['action']}({e['args']})  {e['latency_ms']}ms")

    ok = any(t in ("switch_tracking_estimator", "recalibrate_ptp_sync_domain",
                   "clamp_frustum_margin") for t in tool_calls)
    print(f"\nremediation tool invoked: {'YES' if ok else 'NO'}")
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="occlusion", choices=list(EXPECTED_ROOT_CAUSE))
    ap.add_argument("--camera", type=int, default=1)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.scenario, args.camera)))


if __name__ == "__main__":
    main()
