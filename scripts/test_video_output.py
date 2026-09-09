#!/usr/bin/env python3
"""Automated Verification Suite for Video Ingest and Remediated Video Output."""

import json
import os
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_standalone_video_remediator():
    print("\n[TEST 1] Testing standalone orchestrator/video_remediator.py...")
    input_video = os.path.join(REPO_ROOT, "dashboard", "public", "videos", "stage_witness_boom_occlusion.mp4")
    output_video = os.path.join(REPO_ROOT, "dashboard", "public", "videos", "processed", "verify_remediated_occlusion.mp4")

    cmd = [
        sys.executable,
        os.path.join(REPO_ROOT, "orchestrator", "video_remediator.py"),
        "--input_video", input_video,
        "--output_video", output_video,
        "--scenario", "occlusion",
        "--camera", "1",
        "--anomalies", "35",
        "--jitter", "0.18",
    ]

    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    elapsed = time.monotonic() - t0

    data = json.loads(res.stdout)
    assert data.get("ok") is True, f"Video remediator failed: {res.stdout}"
    assert os.path.exists(output_video), f"Output file does not exist: {output_video}"
    size = os.path.getsize(output_video)
    assert size > 50000, f"Output file is suspiciously small: {size} bytes"

    # Verify with ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,nb_frames",
        "-of", "json",
        output_video,
    ]
    probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(probe_res.stdout)
    stream = probe_data["streams"][0]

    assert stream["codec_name"] == "h264", f"Expected h264 codec, got {stream['codec_name']}"
    assert stream["width"] == 960, f"Expected 960 width, got {stream['width']}"
    assert stream["height"] == 360, f"Expected 360 height, got {stream['height']}"

    print(f"PASS: Video generated in {elapsed:.2f}s | Size: {size/1024:.1f} KB | Codec: {stream['codec_name']} ({stream['width']}x{stream['height']})")


def test_api_process_video_endpoint():
    print("\n[TEST 2] Testing HTTP endpoint /api/process-video...")
    url = "http://localhost:5173/api/process-video"
    payload = {
        "scenario": "ptp_jitter",
        "camera": 1,
        "anomalies": 0,
        "jitter": 4.27,
        "render_frozen": False,
        "summary": "PTP drift on domain 127 verified via video ingest test",
        "video_path": "dashboard/public/videos/stage_witness_ptp_jitter.mp4",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        elapsed = time.monotonic() - t0
        data = json.loads(body)

    assert data.get("ok") is True, f"API returned non-ok: {data}"
    video_url = data.get("output_video_url")
    assert video_url and video_url.startswith("/videos/processed/"), f"Invalid video URL: {video_url}"

    # Verify that the generated video can be fetched via HTTP from Vite
    fetch_url = f"http://localhost:5173{video_url}"
    head_req = urllib.request.Request(fetch_url, method="HEAD")
    with urllib.request.urlopen(head_req, timeout=10) as head_resp:
        assert head_resp.status == 200, f"Failed to fetch generated video from Vite: {head_resp.status}"

    verdict = data.get("verdict", {})
    assert verdict.get("root_cause") == "PTP_CLOCK_JITTER", f"Expected PTP_CLOCK_JITTER, got {verdict.get('root_cause')}"

    print(f"PASS: /api/process-video returned valid video in {elapsed:.2f}s")
    print(f"      URL: {video_url} | Verdict: {verdict.get('root_cause')} -> {verdict.get('remediation_tool')}")


def main():
    print("=" * 70)
    print("RUNNING AUTOMATED VIDEO INGEST & REMEDIATED VIDEO VERIFICATION SUITE")
    print("=" * 70)
    test_standalone_video_remediator()
    test_api_process_video_endpoint()
    print("\n" + "=" * 70)
    print("ALL TESTS PASSED CLEANLY! Video input & output pipeline verified.")
    print("=" * 70)


if __name__ == "__main__":
    main()
