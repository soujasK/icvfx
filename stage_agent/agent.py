"""Stage Incident Commander - the ADK agent (google-adk 2.x).

A single multimodal LlmAgent on Gemini (via Vertex AI) that:
  1. reasons over a witness-camera frame + rendered frustum frame + telemetry
     manifest for one ICVFX desync incident,
  2. classifies the root cause,
  3. executes exactly one remediation by calling the MCP remediation server
     in ../mcp-remediation over stdio,
  4. notifies the stage HUD and reports.

The Grafana Cloud MCP server is added as a second toolset in a later step.

Run:  adk run stage_agent                          (interactive, from repo root)
      python run_agent.py --scenario occlusion     (scripted, multimodal)
"""

from __future__ import annotations

import os
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StdioServerParameters,
)

try:  # class name settled as MCPToolset; McpToolset kept as a fallback
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset as _McpToolset
except ImportError:  # pragma: no cover
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset as _McpToolset

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

from .prompt import SYSTEM_INSTRUCTION

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MCP_SERVER = os.path.join(_REPO, "mcp-remediation", "server.py")

MODEL = os.environ.get("STAGE_AGENT_MODEL", "gemini-2.5-pro")

remediation_toolset = _McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[_MCP_SERVER],
            cwd=_REPO,
        ),
        timeout=30,
    ),
)

root_agent = LlmAgent(
    model=MODEL,
    name="stage_incident_commander",
    description=(
        "Diagnoses tracker/render desync on an ICVFX LED-volume stage from a "
        "witness frame, the rendered frustum, and telemetry, then executes one "
        "MCP remediation and notifies the crew."
    ),
    instruction=SYSTEM_INSTRUCTION,
    tools=[remediation_toolset],
)
