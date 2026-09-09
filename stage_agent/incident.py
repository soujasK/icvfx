"""Build a multimodal incident message for the Stage Incident Commander agent.

An incident = witness-camera frame + rendered frustum frame + a telemetry
manifest, packaged as a google.genai types.Content the ADK Runner can send.

Frames come from incident-arbiter/synthetic_frames.py for the canned
scenarios (occlusion / ptp_jitter / dropped_frame). Swap generate_incident
for a real RTSP/NDI grab + nDisplay render-target dump without touching the
agent - it only needs two image paths and a manifest dict.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_REPO, "incident-arbiter"), os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from synthetic_frames import generate_incident_frames  # noqa: E402
from google.genai import types  # noqa: E402

EXPECTED_ROOT_CAUSE = {
    "occlusion": "PHYSICAL_MARKER_OCCLUSION",
    "ptp_jitter": "PTP_CLOCK_JITTER",
    "dropped_frame": "RENDER_NODE_DROPPED_FRAME",
}


@dataclass
class Incident:
    scenario: str
    alert_summary: str
    manifest: dict[str, Any]
    witness_path: str
    frustum_path: str
    content: types.Content


def _manifest_for(scenario: str, camera_id: int = 1) -> dict[str, Any]:
    anomalies = 31 if scenario == "occlusion" else 0
    ptp_alert = scenario == "ptp_jitter"
    return {
        "window_ms": 500,
        "camera_id": camera_id,
        "kinematic_anomaly_count": anomalies,
        "ptp_alert": ptp_alert,
        "jitter_p99_ms": 4.27 if ptp_alert else 0.18,
        "render_frozen": scenario == "dropped_frame",
    }


def _mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "image/png")


def build_incident(scenario: str, out_dir: str | None = None, camera_id: int = 1) -> Incident:
    if scenario not in EXPECTED_ROOT_CAUSE:
        raise ValueError(f"unknown scenario {scenario!r}; expected one of {list(EXPECTED_ROOT_CAUSE)}")

    out_dir = out_dir or os.path.join(_REPO, "runs", scenario)
    os.makedirs(out_dir, exist_ok=True)
    frames = generate_incident_frames(scenario, out_dir)
    manifest = _manifest_for(scenario, camera_id)

    if manifest["ptp_alert"]:
        alert = f"PTP packet-jitter alert (p99={manifest['jitter_p99_ms']}ms, 3+ consecutive frames)"
    elif manifest["kinematic_anomaly_count"]:
        alert = f"kinematic invariant breach x{manifest['kinematic_anomaly_count']} in the tracking stream"
    else:
        alert = "render buffer freeze flagged by the nDisplay watchdog"

    with open(frames.witness_camera_path, "rb") as f:
        witness_bytes = f.read()
    with open(frames.frustum_buffer_path, "rb") as f:
        frustum_bytes = f.read()

    text = (
        f"INCIDENT on camera {camera_id}.\n"
        f"Alert fired: {alert}\n\n"
        f"Telemetry manifest (last {manifest['window_ms']}ms):\n"
        f"{json.dumps(manifest, indent=2)}\n\n"
        "Image 1 is the witness camera. Image 2 is the rendered frustum buffer "
        "sent to the LED wall at the same timecode. Diagnose the root cause and "
        "remediate per your instructions."
    )

    content = types.Content(
        role="user",
        parts=[
            types.Part(text=text),
            types.Part.from_bytes(data=witness_bytes, mime_type=_mime(frames.witness_camera_path)),
            types.Part.from_bytes(data=frustum_bytes, mime_type=_mime(frames.frustum_buffer_path)),
        ],
    )

    return Incident(
        scenario=scenario,
        alert_summary=alert,
        manifest=manifest,
        witness_path=frames.witness_camera_path,
        frustum_path=frames.frustum_buffer_path,
        content=content,
    )
