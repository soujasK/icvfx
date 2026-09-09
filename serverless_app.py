#!/usr/bin/env python3
"""Serverless Cloud Run Application for ICVFX Autonomous Stage Sync Engine.

Exposes the complete Stage Mission Control dashboard UI and backend APIs
as a serverless, event-driven web application on Google Cloud Run.
Scales to zero instances when idle (zero credit burn).
"""

import os
import sys
import json
import subprocess
import time
import re
import base64
import math
import random
import threading
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))
sys.path.insert(0, str(REPO_ROOT / "incident-arbiter"))

app = FastAPI(title="ICVFX Stage Sync Engine — Serverless Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "serverless", "cloud": "Google Cloud Run"}


@app.get("/api/data")
def get_incident_data():
    scenarios = ["occlusion", "ptp_jitter", "dropped_frame"]
    incidents = {}
    for s in scenarios:
        p = REPO_ROOT / "runs" / s / "incident_report.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    incidents[s] = json.load(f)
            except Exception:
                pass
    state_path = REPO_ROOT / "mcp-remediation" / "stage_state.json"
    stage_state = {}
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                stage_state = json.load(f)
        except Exception:
            pass
    return {"incidents": incidents, "stageState": stage_state}


# Edge telemetry relay state & live EKF trajectory buffer
_edge_lock = threading.Lock()
_latest_edge_telemetry: Optional[Dict[str, Any]] = None
_latest_edge_rx_time: float = 0.0
_sim_trajectory: deque = deque(maxlen=60)
_sim_start_time = time.monotonic()


@app.post("/api/telemetry/push")
async def push_telemetry(request: Request):
    """Ingest live 120Hz EKF telemetry pushed from local edge daemon."""
    global _latest_edge_telemetry, _latest_edge_rx_time
    try:
        body = await request.json()
        with _edge_lock:
            _latest_edge_telemetry = body
            _latest_edge_rx_time = time.monotonic()
        return {"ok": True, "source": "edge_relay"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/udp-telemetry")
def get_udp_telemetry():
    """Returns real edge UDP telemetry if active, or live mathematical EKF crane trajectory."""
    now = time.monotonic()
    with _edge_lock:
        if _latest_edge_telemetry is not None and (now - _latest_edge_rx_time) < 4.0:
            return {
                **_latest_edge_telemetry,
                "edge_relay_active": True,
                "edge_age_s": round(now - _latest_edge_rx_time, 2)
            }

    # Autonomous in-cloud EKF kinematics simulation (Dolly arc trajectory)
    t = now - _sim_start_time
    x = 2.5 * math.sin(t * 0.8)
    y = 2.2 + 1.2 * math.cos(t * 0.6)
    z = 1.5 + 0.3 * math.sin(t * 1.2)

    vx = 2.5 * 0.8 * math.cos(t * 0.8)
    vy = -1.2 * 0.6 * math.sin(t * 0.6)
    vz = 0.3 * 1.2 * math.cos(t * 1.2)

    pitch = -5.0 + 4.0 * math.sin(t * 0.8)
    yaw = 15.0 * math.cos(t * 0.8)
    roll = 1.0 * math.sin(t * 0.4)

    jitter = round(0.18 + random.uniform(-0.02, 0.03), 3)
    ptp_offset = round(34.0 + random.uniform(-2.0, 2.0), 1)

    raw_x = round(x + random.gauss(0, 0.015), 3)
    raw_yaw = round(yaw + random.gauss(0, 0.05), 2)
    frame_no = int(t * 120)

    _sim_trajectory.append({
        "idx": len(_sim_trajectory),
        "frame": frame_no,
        "raw": [raw_x, round(y, 3), round(z, 3), 0.0, raw_yaw, round(pitch, 2)],
        "filtered": [round(x, 3), round(vx, 3), 0.0, round(y, 3), round(vy, 3), 0.0, round(z, 3), round(vz, 3), 0.0, round(yaw, 2), 0.0, 0.0],
        "occluded": False,
    })

    return {
        "ok": True,
        "edge_relay_active": False,
        "socket": {
            "port": 5005,
            "rate_hz": 120.0,
            "packets_received": 144000 + frame_no,
            "jitter_ms": jitter,
            "ptp_offset_ns": ptp_offset,
            "jerk_violations": 0,
        },
        "ekf_tracker": {
            "x": round(x, 2), "y": round(y, 2), "z": round(z, 2),
            "vx": round(vx, 2), "vy": round(vy, 2), "vz": round(vz, 2),
            "pitch": round(pitch, 1), "yaw": round(yaw, 1), "roll": round(roll, 1),
            "mode": "KALMAN_STANDARD",
            "covariance_trace": 0.013,
            "consecutive_rejections": 0,
        },
        "recent_trajectory": list(_sim_trajectory),
    }


@app.post("/api/custom-diagnose")
async def custom_diagnose(request: Request):
    body = await request.json()
    scenario = body.get("scenario", "occlusion")
    camera = str(body.get("camera", 1))
    anomalies = str(body.get("anomalies", 0))
    summary = body.get("summary", "")
    prompt = body.get("prompt", "")

    args = [
        sys.executable,
        str(REPO_ROOT / "orchestrator" / "run_custom_action.py"),
        "--action", "diagnose",
        "--scenario", scenario,
        "--camera", camera,
        "--anomalies", anomalies,
        "--summary", summary,
        "--prompt", prompt,
    ]
    if body.get("jitter") is not None:
        args.extend(["--jitter", str(body["jitter"])])
    if body.get("render_frozen") is not None:
        args.extend(["--render_frozen", str(body["render_frozen"])])

    proc = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True, text=True)
    try:
        import re
        match = re.search(r"\{[\s\S]*\}", proc.stdout)
        if match:
            return json.loads(match.group(0))
        return {"stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as e:
        return {"error": str(e), "stdout": proc.stdout, "stderr": proc.stderr}


@app.post("/api/custom-action")
async def custom_action(request: Request):
    body = await request.json()
    tool = body.get("tool", "notify_stage_hud")
    args_str = json.dumps(body.get("args", {}))
    cmd = [
        sys.executable,
        str(REPO_ROOT / "orchestrator" / "run_custom_action.py"),
        "--action", "mcp",
        "--tool", tool,
        "--args", args_str,
    ]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    try:
        match = re.search(r"\{[\s\S]*\}", proc.stdout)
        if match:
            return json.loads(match.group(0))
        return {"stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as e:
        return {"error": str(e), "stdout": proc.stdout, "stderr": proc.stderr}


@app.post("/api/process-video")
async def process_video(request: Request):
    body = await request.json()
    scenario = body.get("scenario", "occlusion")
    camera = str(body.get("camera", 1))
    anomalies = str(body.get("anomalies", 35))
    summary = body.get("summary", "")
    jitter = str(body.get("jitter", 0.18))
    render_frozen = str(bool(body.get("render_frozen", False)))

    input_video_path = body.get("video_path") or "dashboard/public/videos/stage_witness_boom_occlusion.mp4"

    video_b64 = body.get("video_base64")
    if video_b64 and isinstance(video_b64, str):
        try:
            b64_data = re.sub(r"^data:video/\w+;base64,", "", video_b64)
            buf = base64.b64decode(b64_data)
            upload_dir = REPO_ROOT / "dashboard" / "public" / "videos" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / f"custom_video_{int(time.time()*1000)}.mp4"
            with open(upload_path, "wb") as f:
                f.write(buf)
            input_video_path = str(upload_path)
        except Exception as e:
            print("Video upload decode warning:", e)

    processed_dir = REPO_ROOT / "dashboard" / "public" / "videos" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    out_filename = f"remediated_{scenario}_{int(time.time()*1000)}.mp4"
    out_video_path = processed_dir / out_filename

    args = [
        sys.executable,
        str(REPO_ROOT / "orchestrator" / "video_remediator.py"),
        "--input_video", str(input_video_path),
        "--output_video", str(out_video_path),
        "--scenario", scenario,
        "--camera", camera,
        "--anomalies", anomalies,
        "--jitter", jitter,
        "--render_frozen", render_frozen,
        "--summary", summary,
    ]

    proc = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True, text=True)
    try:
        match = re.search(r"\{[\s\S]*\}", proc.stdout)
        if match:
            return json.loads(match.group(0))
        return {"ok": False, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": proc.stdout, "stderr": proc.stderr}


@app.get("/api/grafana-stream/status")
def grafana_stream_status():
    status_file = REPO_ROOT / "runs" / "grafana_shipper.json"
    if status_file.exists():
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                return {"ok": True, **json.load(f)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True, "running": False, "status": "IDLE", "pushes_sent": 0}


@app.post("/api/grafana-stream/start")
async def grafana_stream_start(request: Request):
    body = await request.json()
    interval = str(body.get("interval", 5.0))
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "push_to_grafana_cloud.py"), "--start", "--interval", interval],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return {"ok": proc.returncode == 0, "code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


@app.post("/api/grafana-stream/stop")
def grafana_stream_stop():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "push_to_grafana_cloud.py"), "--stop"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return {"ok": proc.returncode == 0, "code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


# Serve static React frontend files from dashboard/dist
dist_dir = REPO_ROOT / "dashboard" / "dist"
if dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")

    # Serve public videos & runs
    public_dir = REPO_ROOT / "dashboard" / "public"
    if public_dir.exists():
        app.mount("/videos", StaticFiles(directory=str(public_dir / "videos")), name="videos")
        runs_dir = public_dir / "runs"
        if runs_dir.exists():
            app.mount("/runs", StaticFiles(directory=str(runs_dir)), name="runs")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = dist_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(dist_dir / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("serverless_app:app", host="0.0.0.0", port=port, log_level="info")
