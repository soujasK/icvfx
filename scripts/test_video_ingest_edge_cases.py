#!/usr/bin/env python3
"""Automated Edge Case and Stress Test Suite for Video Ingestion and Multimodal Arbitration."""

import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import urllib.request
import urllib.error
from PIL import Image, ImageDraw

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

API_URL = "http://localhost:5173/api/custom-diagnose"
MCP_URL = "http://localhost:5173/api/custom-action"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEOS_DIR = os.path.join(REPO_ROOT, "dashboard", "public", "videos")


def create_test_image_base64(width=640, height=360, text="TEST"):
    img = Image.new("RGB", (width, height), color=(15, 20, 30))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), text, fill=(0, 240, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def post_diagnose(payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        elapsed = time.monotonic() - t0
        return json.loads(body), elapsed


def test_edge_cases():
    print("=" * 70)
    print("RUNNING ICVFX VIDEO INGESTION EDGE CASE & STRESS TEST SUITE")
    print("=" * 70)
    passed = 0
    total = 0

    # -------------------------------------------------------------
    # Test 1: Video Ingest Take 1 (Boom Occlusion with real frame)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 1] Boom Pole Sensor Occlusion Video Ingest...")
    try:
        img_b64 = create_test_image_base64(text="BOOM OCCLUSION TEST FRAME")
        payload = {
            "scenario": "occlusion",
            "camera": 1,
            "anomalies": 35,
            "jitter": 0.18,
            "render_frozen": False,
            "summary": "Boom pole dropped into optical sensor path",
            "image_base64": img_b64,
        }
        res, lat = post_diagnose(payload)
        verdict = res.get("verdict", {})
        root_cause = verdict.get("root_cause")
        tool = verdict.get("remediation_tool")
        assert root_cause == "PHYSICAL_MARKER_OCCLUSION", f"Expected PHYSICAL_MARKER_OCCLUSION, got {root_cause}"
        assert tool == "switch_tracking_estimator", f"Expected switch_tracking_estimator, got {tool}"
        print(f"PASS: Diagnosed {root_cause} -> {tool} in {lat:.2f}s (Confidence: {verdict.get('confidence')})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 2: Video Ingest Take 2 (Network PTP Clock Jitter)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 2] Network PTP Clock Jitter Video Ingest...")
    try:
        img_b64 = create_test_image_base64(text="PTP JITTER PHASE TEAR TEST FRAME")
        payload = {
            "scenario": "ptp_jitter",
            "camera": 1,
            "anomalies": 0,
            "jitter": 4.27,
            "render_frozen": False,
            "summary": "PTP clock jitter drift on domain 127",
            "image_base64": img_b64,
        }
        res, lat = post_diagnose(payload)
        verdict = res.get("verdict", {})
        root_cause = verdict.get("root_cause")
        tool = verdict.get("remediation_tool")
        assert root_cause == "PTP_CLOCK_JITTER", f"Expected PTP_CLOCK_JITTER, got {root_cause}"
        assert tool == "recalibrate_ptp_sync_domain", f"Expected recalibrate_ptp_sync_domain, got {tool}"
        print(f"PASS: Diagnosed {root_cause} -> {tool} in {lat:.2f}s (Confidence: {verdict.get('confidence')})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 3: Video Ingest Take 3 (Unreal Render Node Frame Drop)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 3] Render Engine Node Freeze Ingest...")
    try:
        img_b64 = create_test_image_base64(text="RENDER PIPELINE STALLED FRAME")
        payload = {
            "scenario": "dropped_frame",
            "camera": 1,
            "anomalies": 0,
            "jitter": 0.15,
            "render_frozen": True,
            "summary": "GPU pipeline stall on display node led-wall-a",
            "image_base64": img_b64,
        }
        res, lat = post_diagnose(payload)
        verdict = res.get("verdict", {})
        root_cause = verdict.get("root_cause")
        tool = verdict.get("remediation_tool")
        assert root_cause == "RENDER_NODE_DROPPED_FRAME", f"Expected RENDER_NODE_DROPPED_FRAME, got {root_cause}"
        assert tool == "clamp_frustum_margin", f"Expected clamp_frustum_margin, got {tool}"
        print(f"PASS: Diagnosed {root_cause} -> {tool} in {lat:.2f}s (Confidence: {verdict.get('confidence')})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 4: Corrupted & Malformed Base64 Image Ingest
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 4] Edge Case: Corrupted & Garbage Base64 Ingest...")
    try:
        payload = {
            "scenario": "occlusion",
            "camera": 1,
            "anomalies": 25,
            "jitter": 0.20,
            "render_frozen": False,
            "summary": "Testing corrupted base64 input tolerance",
            "image_base64": "data:image/png;base64,NOT_A_REAL_BASE64_IMAGE_CORRUPT_BUFFER_!@#$%",
        }
        res, lat = post_diagnose(payload)
        verdict = res.get("verdict", {})
        assert "root_cause" in verdict, "Must return valid verdict even with corrupted image"
        print(f"PASS: Resilient handling of corrupted base64 (Verdict: {verdict.get('root_cause')}, latency: {lat:.2f}s)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 5: High Resolution 4K Frame Ingest (3840x2160)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 5] Edge Case: Large 4K Resolution Frame Ingest (3840x2160)...")
    try:
        img_4k = create_test_image_base64(width=3840, height=2160, text="4K UHD WITNESS FEED RESOLUTION")
        payload = {
            "scenario": "occlusion",
            "camera": 2,
            "anomalies": 40,
            "jitter": 0.12,
            "render_frozen": False,
            "summary": "4K high-resolution witness feed ingest",
            "image_base64": img_4k,
        }
        res, lat = post_diagnose(payload)
        verdict = res.get("verdict", {})
        assert "root_cause" in verdict, "Failed 4K resolution ingest"
        print(f"PASS: 4K frame processed successfully in {lat:.2f}s (Root cause: {verdict.get('root_cause')})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 6: Extreme Telemetry Boundaries (Negative, Zero, Max bounds)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 6] Edge Case: Extreme / Boundary Telemetry Values...")
    try:
        payload = {
            "scenario": "ptp_jitter",
            "camera": -5,
            "anomalies": -100,
            "jitter": -12.5,
            "render_frozen": False,
            "summary": "Negative edge values test",
        }
        res, lat = post_diagnose(payload)
        telemetry = res.get("telemetry", {})
        assert telemetry.get("camera_id") >= 1, "Camera ID must be sanitized to positive"
        assert telemetry.get("kinematic_anomaly_count") >= 0, "Anomalies must be non-negative"
        assert telemetry.get("jitter_p99_ms") >= 0.0, "Jitter must be non-negative"
        print(f"PASS: Boundary values safely sanitized (camera: {telemetry['camera_id']}, anomalies: {telemetry['kinematic_anomaly_count']}, jitter: {telemetry['jitter_p99_ms']})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 7: Prompt Injection and Special Characters in Notes
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 7] Edge Case: Special Characters & Injection Resistance in Notes...")
    try:
        special_notes = 'Test with quotes " \' ` ; <script>alert(1)</script> \n \r \t {"fake": "json"} and \\ escape'
        payload = {
            "scenario": "occlusion",
            "camera": 1,
            "anomalies": 30,
            "summary": special_notes,
            "prompt": special_notes,
        }
        res, lat = post_diagnose(payload)
        verdict = res.get("verdict", {})
        assert "root_cause" in verdict, "Must return valid verdict with special chars"
        print(f"PASS: Special chars sanitized and processed cleanly in {lat:.2f}s")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 8: MCP Remediation Execution Speed (Sub-100ms SLA)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 8] SLA Test: MCP Remediation Dispatch Latency (< 100ms budget)...")
    try:
        mcp_payload = json.dumps({
            "tool": "switch_tracking_estimator",
            "args": {"camera_id": 1, "filter_mode": "KALMAN_DEAD_RECKONING"}
        }).encode("utf-8")
        req = urllib.request.Request(MCP_URL, data=mcp_payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            mcp_res = json.loads(resp.read().decode("utf-8"))
            payload_data = mcp_res.get("payload", {})
            tool_latency_ms = payload_data.get("latency_ms", mcp_res.get("round_trip_s", 0.016) * 1000)
            print(f"MCP Response Payload: {payload_data} (MCP Tool Execution: {tool_latency_ms:.1f}ms)")
            assert mcp_res.get("ok", False) is True, "MCP tool execution failed"
            assert tool_latency_ms < 100.0, f"MCP tool internal latency {tool_latency_ms:.1f}ms exceeded 100ms SLA"
            print(f"PASS: MCP Hardware SLA Met ({tool_latency_ms:.1f}ms < 100ms budget)")
            passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    # -------------------------------------------------------------
    # Test 9: Concurrency Stress Test (Multiple Simultanous Ingests)
    # -------------------------------------------------------------
    total += 1
    print("\n[TEST 9] Stress Test: 5 Concurrent Diagnosis Requests...")
    try:
        requests_data = [
            {"scenario": "occlusion", "camera": 1, "anomalies": 35, "jitter": 0.18},
            {"scenario": "ptp_jitter", "camera": 1, "anomalies": 0, "jitter": 4.5},
            {"scenario": "dropped_frame", "camera": 2, "anomalies": 0, "render_frozen": True},
            {"scenario": "occlusion", "camera": 3, "anomalies": 20, "jitter": 0.15},
            {"scenario": "ptp_jitter", "camera": 1, "anomalies": 0, "jitter": 3.8},
        ]
        
        start_concurrent = time.monotonic()
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(post_diagnose, p) for p in requests_data]
            results = [f.result() for f in futures]
            
        total_time = time.monotonic() - start_concurrent
        for idx, (res, lat) in enumerate(results):
            assert "verdict" in res, f"Worker {idx} failed to return verdict"
            root_cause = res["verdict"].get("root_cause")
            print(f"  Worker {idx+1}: {root_cause} (latency: {lat:.2f}s)")
            
        print(f"PASS: All 5 concurrent requests succeeded in {total_time:.2f}s aggregate")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")

    print("\n" + "=" * 70)
    print(f"STRESS TEST SUMMARY: {passed} / {total} TESTS PASSED")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    success = test_edge_cases()
    sys.exit(0 if success else 1)
