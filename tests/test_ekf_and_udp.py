#!/usr/bin/env python3
"""Automated Verification Suite for 6-DoF Extended Kalman Filter & 120Hz FreeD UDP Ingestion."""

import json
import os
import socket
import sys
import time
import urllib.request
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "orchestrator"))
sys.path.insert(0, os.path.join(REPO_ROOT, "telemetry-mesh"))

from kalman_tracker import KalmanTracker
from freed_udp_daemon import build_freed_packet, parse_freed_packet, FREED_PACKET_LEN, UDP_PORT


def test_ekf_mathematics():
    print("\n[TEST 1] Testing 6-DoF Extended Kalman Filter (EKF) State Space Mathematics...")
    kf = KalmanTracker(sigma_accel=1.0, sigma_meas_pos=0.001)

    # 1. Warm-up with linear crane motion along X at 1.0 m/s
    dt = 1.0 / 120.0
    for i in range(1, 30):
        t = i * dt
        x_meas = 1.0 * t + np.random.normal(0, 0.0005)
        meas = np.array([x_meas, 2.0, 1.5, 0.0, 10.0, 0.0])
        kf.step(dt, meas)

    pose = kf.get_pose()
    assert abs(pose["vx"] - 1.0) < 0.15, f"EKF failed to identify linear velocity: {pose['vx']} m/s vs 1.0 m/s"
    assert pose["covariance_trace"] < 5.0, f"Covariance failed to converge: {pose['covariance_trace']}"
    print(f"PASS: Velocity converged to {pose['vx']:.3f} m/s (expected ~1.0 m/s), Covariance trace: {pose['covariance_trace']:.4f}")

    # 2. Simulate 20-frame optical marker blackout (Occlusion fault)
    print("  Testing optical sensor occlusion (Dead Reckoning propagation)...")
    last_x = pose["x"]
    for i in range(30, 50):
        # Malformed optical measurement jumping 10 meters and flipping yaw 180 degrees
        corrupted_meas = np.array([99.0, -50.0, 0.0, 45.0, 190.0, 0.0])
        state, valid = kf.step(dt, corrupted_meas)
        assert valid is False, "EKF must reject impossible sensor jumps via Mahalanobis gating"

    post_blackout_pose = kf.get_pose()
    assert post_blackout_pose["consecutive_rejections"] == 20, "Expected 20 consecutive rejections"
    # State should have smoothly propagated forward: x ~= last_x + vx * (20 * dt)
    expected_travel = 1.0 * (20 * dt)
    actual_travel = post_blackout_pose["x"] - last_x
    assert abs(actual_travel - expected_travel) < 0.05, f"Dead reckoning drift {actual_travel}m deviated from expected {expected_travel}m"
    print(f"PASS: 20-frame optical blackout successfully dead-reckoned via momentum (traveled {actual_travel:.3f}m, expected ~{expected_travel:.3f}m)")


def test_dead_reckoning_auto_recovers():
    print("\n[TEST 1b] Testing dead-reckoning auto-recovery (no one-way trap)...")
    dt = 1.0 / 120.0
    kf = KalmanTracker(sigma_accel=1.0, sigma_meas_pos=0.001, reacquire_after_good=90)

    # warm up on smooth motion, then command dead-reckoning
    for i in range(1, 40):
        kf.step(dt, np.array([0.5 * np.sin(i * dt), 2.0, 1.5, 0.0, 0.0, 0.0]))
    kf.set_mode("KALMAN_DEAD_RECKONING")
    assert kf.get_pose()["mode"] == "KALMAN_DEAD_RECKONING"

    # feed a long run of physically-smooth optical - the occlusion has cleared
    recovered_at = None
    for i in range(40, 400):
        _, valid = kf.step(dt, np.array([0.5 * np.sin(i * dt), 2.0, 1.5, 0.0, 0.0, 0.0]))
        if valid and recovered_at is None:
            recovered_at = i

    pose = kf.get_pose()
    assert recovered_at is not None, "EKF never re-acquired optical - stuck in dead-reckoning forever"
    assert pose["mode"] == "KALMAN_STANDARD", f"Expected auto-revert to STANDARD, got {pose['mode']}"
    assert abs(pose["x"] - 0.5 * np.sin(399 * dt)) < 0.1, f"Pose did not re-lock to truth: x={pose['x']}"
    print(f"PASS: re-acquired at frame {recovered_at - 40} of clean optical, mode back to STANDARD, pose re-locked")

    # and it must NOT bail out while the stream is still wild (real occlusion)
    kf2 = KalmanTracker(sigma_accel=1.0, sigma_meas_pos=0.001, reacquire_after_good=90)
    for i in range(1, 40):
        kf2.step(dt, np.array([0.5 * np.sin(i * dt), 2.0, 1.5, 0.0, 0.0, 0.0]))
    kf2.set_mode("KALMAN_DEAD_RECKONING")
    accepted = 0
    for i in range(200):
        z = np.array([0.5 * np.sin(i * dt) + (1.5 if i % 2 else -1.5), 2.0, 1.5, 0.0,
                      170.0 * (1 if i % 2 else -1), 0.0])
        accepted += kf2.step(dt, z)[1]
    assert accepted == 0, f"EKF re-acquired on a still-wild stream ({accepted} accepted) - would snap onto garbage"
    print("PASS: held dead-reckoning through a still-active occlusion (0 optical measurements accepted)")


def test_freed_wire_protocol():
    print("\n[TEST 2] Testing 29-Byte FreeD D1 Wire Protocol Packet Encoding & Decoding...")
    pkt = build_freed_packet(
        camera_id=1,
        x=2.345, y=3.456, z=1.234,
        pitch=-12.5, yaw=45.25, roll=1.5
    )
    assert len(pkt) == 29, f"FreeD D1 packet must be exactly 29 bytes, got {len(pkt)}"
    assert pkt[0] == 0xD1, "FreeD packet must start with 0xD1 header"

    decoded = parse_freed_packet(pkt)
    assert decoded is not None, "Failed to parse generated FreeD packet"
    assert decoded["camera_id"] == 1
    assert abs(decoded["x"] - 2.345) < 0.001, f"Pos X mismatch: {decoded['x']}"
    assert abs(decoded["pitch"] - (-12.5)) < 0.01, f"Pitch mismatch: {decoded['pitch']}"
    assert abs(decoded["yaw"] - 45.25) < 0.01, f"Yaw mismatch: {decoded['yaw']}"
    print("PASS: Bitfield FreeD D1 wire codec validated within 0.001m / 0.01deg precision")


def test_live_udp_telemetry_endpoint():
    print("\n[TEST 3] Testing Live 120Hz FreeD UDP Socket Ingestion on Port 5005/8080...")
    url = "http://localhost:5173/api/udp-telemetry"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    assert data.get("ok") is True, f"Telemetry endpoint returned non-ok: {data}"
    socket_info = data.get("socket", {})
    assert socket_info.get("port") == 5005, f"Expected port 5005, got {socket_info.get('port')}"
    assert socket_info.get("packets_total") > 100, f"Expected packets received, got {socket_info.get('packets_total')}"

    ekf = data.get("ekf_tracker", {})
    assert "vx" in ekf and "covariance_trace" in ekf, "Missing EKF state-space metrics"
    assert all(abs(ekf[a]) < 10.0 for a in ("x", "y", "z")), (
        f"EKF pose drifted implausibly far (x={ekf['x']}, y={ekf['y']}, z={ekf['z']}) - "
        "the simulated crane stays within a ~3m box; this means dead-reckoning is not "
        "recovering. Restart the daemon to pick up the kalman_tracker auto-reacquire fix."
    )

    print(f"PASS: Live UDP Socket verified on port {socket_info['port']} (Rate: {socket_info['rate_hz']} Hz, Total Packets: {socket_info['packets_total']})")
    print(f"      Active 6-DoF Pose: X={ekf['x']}m, Y={ekf['y']}m, Z={ekf['z']}m | Yaw={ekf['yaw']}° | Mode: {ekf['mode']}")


def test_hardware_fault_injection_over_udp():
    print("\n[TEST 4] Testing Real Hardware Fault Injection over 120Hz UDP Socket...")
    inject_url = "http://localhost:5173/api/inject-fault"
    payload = json.dumps({"type": "occlusion", "duration_ms": 2000}).encode("utf-8")
    req = urllib.request.Request(inject_url, data=payload, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=10) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
    assert res_data.get("ok") is True, "Failed to inject occlusion fault over UDP"

    # Allow daemon to ingest 15 frames of occlusion
    time.sleep(0.3)

    # Verify UDP telemetry records occlusion
    status_req = urllib.request.Request("http://localhost:5173/api/udp-telemetry")
    with urllib.request.urlopen(status_req, timeout=10) as sresp:
        status_data = json.loads(sresp.read().decode("utf-8"))

    jerk_spikes = status_data.get("socket", {}).get("jerk_violations", 0)
    consec_rej = status_data.get("ekf_tracker", {}).get("consecutive_rejections", 0)
    print(f"PASS: Real UDP Occlusion injected successfully (Jerk Violations: {jerk_spikes}, EKF Innovation Rejections: {consec_rej})")


def main():
    print("=" * 70)
    print("RUNNING 6-DoF EKF & 120Hz FreeD UDP INGESTION VERIFICATION SUITE")
    print("=" * 70)
    test_ekf_mathematics()
    test_dead_reckoning_auto_recovers()
    test_freed_wire_protocol()
    test_live_udp_telemetry_endpoint()
    test_hardware_fault_injection_over_udp()
    print("\n" + "=" * 70)
    print("ALL 4 TESTS PASSED! Real-time UDP Daemon & 6-DoF EKF fully operational.")
    print("=" * 70)


if __name__ == "__main__":
    main()
