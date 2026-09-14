#!/usr/bin/env python3
"""Generates studio-quality AI voiceover for the 150-second hackathon demo video."""

import asyncio
import edge_tts
from pathlib import Path

VOICE = "en-US-ChristopherNeural"  # Authoritative, cinematic, clear documentary voice

# Complete script with natural speech pauses
FULL_SCRIPT = """
On a virtual production LED stage, production downtime costs upwards of fifty thousand dollars an hour. Optical tracking dropouts, PTP clock jitter, and FreeD UDP spikes can instantly corrupt real-time background rendering in Unreal Engine.

To solve this, we architected the Autonomous ICVFX Sync Engine. On the data plane, raw 120Hz FreeD packets are processed on UDP port 5005. On the control plane, telemetry streams to Grafana Cloud while Gemini 2.5 on Vertex AI acts as our multimodal diagnostic brain.

The operational workflow is simple: Ingest, Reason, and Remediate in real time.

Here is our live Stage Mission Control HUD, deployed serverless on Google Cloud Run. The top banner confirms Stage 04 Volume A is active, listening on UDP 5005 with nominal genlock.

In Column 1, we monitor the live witness camera feed and Steadicam rig trajectory arc. Column 2 houses the Gemini Multimodal Arbiter, primed with a sub-100 millisecond SLA target.

In Column 3, live telemetry confirms a healthy baseline: PTP jitter at 0.18 milliseconds and zero jerk breaches. Tracking is set to Optical Primary.

Now, let's trigger an on-set fault: a physical crane obstruction event. As the video plays to second two, a physical boom arm sweeps across the tracking constellation.

Instantly, the bounding box fires: Sensor Line-of-Sight Blocked! Kinematic jerk breaches spike to 35, and optical confidence collapses.

Gemini 2.5 immediately ingests the corrupted telemetry manifest alongside the witness frame. Root cause diagnosed: Physical Marker Occlusion, with 98.4% confidence.

Through the Model Context Protocol, Gemini autonomously issues the remediation call: switch tracking estimator. Executed in just 31 milliseconds, safely beating our 100 millisecond SLA and transitioning to Kalman dead-reckoning.

Now let's examine the side-by-side A/B output verification to see the real cinematic difference.

On the left, the raw unmanaged render judders violently, tearing the perspective frustum on the LED wall. On the right, our autonomous remediated feed maintains a mathematically continuous trajectory through the occlusion window.

Parallax geometry remains flawless, completely saving the take without halting the camera crew.

In Grafana Cloud, all 35 kinematic jerk breaches align precisely with the timestamp of the boom crossing, confirming end-to-end stage observability.

As line-of-sight clears, the closed loop confirms recovery, returning tracking to nominal. Autonomous incident arbitration for virtual production, powered by Gemini on Vertex AI and Grafana Cloud.
"""

async def generate():
    out_dir = Path(__file__).resolve().parent
    out_file = out_dir / "demo_voiceover.mp3"
    print(f"Generating studio AI voiceover using {VOICE}...")
    communicate = edge_tts.Communicate(FULL_SCRIPT, VOICE, rate="+3%")
    await communicate.save(str(out_file))
    print(f"Voiceover successfully generated: {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    asyncio.run(generate())
