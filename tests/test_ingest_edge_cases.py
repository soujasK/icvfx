"""Edge-case tests for cpp-core/bin/kinematic_engine, exercised over real
UDP against the actual compiled binary (not a mock). Uses freed_wire.py to
craft exact-bytes valid and deliberately corrupt packets.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_harness import start_engine, send_udp, EngineStartupError  # noqa: E402
from freed_wire import build_packet  # noqa: E402

NEXT_PORT = [41001]  # avoid cross-test port collisions; see test_rapid_restart for a same-port test


def _fresh_port() -> int:
    NEXT_PORT[0] += 1
    return NEXT_PORT[0]


def _count_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return sum(1 for _ in f)


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_valid_packet_from_python_wire_helper_is_accepted():
    """Cross-validates the Python test packer against the real C++ decoder:
    if these two ever drift out of sync, every other test in this file
    would be exercising the wrong bytes without anyone noticing."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=600)
        pkt = build_packet(camera_id=3, yaw_deg=12.5, pos_x_m=2.0, zoom=1234, focus=999)
        send_udp(port, pkt)
        stderr = engine.wait_and_collect()

        raw = _read_jsonl(os.path.join(out_dir, "stage.tracking.raw.jsonl"))
        assert len(raw) == 1, f"expected exactly 1 accepted frame, got {len(raw)}"
        assert raw[0]["camera_id"] == 3
        assert abs(raw[0]["yaw_deg"] - 12.5) < 1e-2
        assert abs(raw[0]["pos_x_m"] - 2.0) < 1e-2
        assert raw[0]["zoom"] == 1234
        assert "TOTAL frames=1" in stderr, stderr


def test_wrong_size_datagrams_are_dropped_not_crashed():
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=600)
        send_udp(port, b"\x00" * 10)   # too short
        send_udp(port, b"\x00" * 200)  # too long
        send_udp(port, build_packet())  # one valid packet so we can confirm processing continued
        stderr = engine.wait_and_collect()

        assert "dropped_wrong_size=2" in stderr, stderr
        assert "TOTAL frames=1" in stderr, stderr


def test_bad_header_byte_is_dropped():
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=600)
        send_udp(port, build_packet(bad_header=True))
        stderr = engine.wait_and_collect()

        assert "dropped_bad_header=1" in stderr, stderr
        assert "TOTAL frames=0" in stderr, stderr


def test_corrupted_checksum_is_dropped():
    """Locks in the checksum-validation fix: before it existed, a corrupt
    packet would flow straight into the kinematic invariant state and could
    register as a fake acceleration spike."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=600)
        send_udp(port, build_packet(pos_x_m=50.0, corrupt_checksum=True))
        stderr = engine.wait_and_collect()

        assert "dropped_checksum_failed=1" in stderr, stderr
        assert "TOTAL frames=0" in stderr, stderr
        anomalies = _count_lines(os.path.join(out_dir, "stage.kinematic.anomalies.jsonl"))
        assert anomalies == 0, "a corrupted packet must never reach the anomaly detector"


def test_garbage_interleaved_with_valid_does_not_desync_processing():
    """UDP is packet-oriented, so one bad datagram should never affect the
    next one - this pins that down explicitly rather than assuming it."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=600)
        send_udp(port, build_packet(pos_x_m=0.0))
        send_udp(port, b"garbage-not-a-freed-packet-at-all")
        send_udp(port, build_packet(bad_header=True))
        send_udp(port, build_packet(pos_x_m=1.0, corrupt_checksum=True))
        send_udp(port, build_packet(pos_x_m=2.0))
        stderr = engine.wait_and_collect()

        raw = _read_jsonl(os.path.join(out_dir, "stage.tracking.raw.jsonl"))
        assert len(raw) == 2, f"expected exactly the 2 valid packets through, got {len(raw)}"
        assert [r["pos_x_m"] for r in raw] == [0.0, 2.0]


def test_multi_camera_state_is_isolated():
    """Regression test for the pre-fix bug: a single shared ring buffer
    would compute nonsense velocities across two different cameras'
    interleaved packets and could attribute camera A's glitch to camera B
    or vice versa."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, hz=120, idle_timeout_ms=800)

        # Camera 1: smooth pan, no violations expected.
        # Camera 2: an explicit near-180-degree yaw flip every frame -
        # should trip the rotation-flip invariant every time.
        for i in range(6):
            send_udp(port, build_packet(camera_id=1, yaw_deg=i * 1.0, pos_x_m=i * 0.01))
            yaw2 = 0.0 if i % 2 == 0 else 170.0  # alternating flip, well past the 90 deg threshold
            send_udp(port, build_packet(camera_id=2, yaw_deg=yaw2, pos_x_m=0.0))

        stderr = engine.wait_and_collect()
        anomalies = _read_jsonl(os.path.join(out_dir, "stage.kinematic.anomalies.jsonl"))

        cam1_anomalies = [a for a in anomalies if a["camera_id"] == 1]
        cam2_anomalies = [a for a in anomalies if a["camera_id"] == 2]

        assert len(cam1_anomalies) == 0, f"camera 1 (smooth) must have zero anomalies, got {cam1_anomalies}"
        assert len(cam2_anomalies) >= 3, f"camera 2 (flipping) should trip the rotation-flip check repeatedly, got {len(cam2_anomalies)}"
        assert "camera_id=1 frames=6" in stderr, stderr
        assert "camera_id=2 frames=6" in stderr, stderr
        assert "cameras=2" in stderr, stderr


def test_zero_traffic_exits_cleanly_within_idle_timeout():
    """No generator ever connects; the engine must still exit on its own
    (not hang forever) once the idle timeout elapses, with well-formed
    (empty) output files rather than a crash."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=400)
        stderr = engine.wait_and_collect(timeout=3.0)
        assert "TOTAL frames=0" in stderr, stderr
        assert engine.proc.returncode == 0, f"expected clean exit, got code {engine.proc.returncode}"
        # Output files must exist (even if empty) so downstream JSONL readers don't choke.
        for fname in ("stage.tracking.raw.jsonl", "stage.ptp.drift.jsonl", "stage.kinematic.anomalies.jsonl"):
            assert os.path.exists(os.path.join(out_dir, fname))


def test_rapid_bind_restart_on_same_port():
    """SO_REUSEADDR must let the engine rebind the same port immediately
    after the previous instance exits - stage software gets restarted
    between takes far more often than a fresh port is available."""
    port = _fresh_port()
    for i in range(5):
        with tempfile.TemporaryDirectory() as out_dir:
            engine = start_engine(port, out_dir, idle_timeout_ms=300)
            engine.wait_and_collect(timeout=2.0)
            assert engine.proc.returncode == 0, f"restart #{i} failed to bind/exit cleanly"


def test_out_of_range_camera_id_and_extreme_pose_do_not_crash():
    """camera_id is a full uint8 (0-255) and pose values can be crafted
    arbitrarily large on the wire (a malfunctioning sensor, not just a
    malicious one) - the engine must saturate/handle these, never crash."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=600)
        send_udp(port, build_packet(camera_id=255, pos_x_m=1e9, yaw_deg=-1e9, pos_z_m=-1e9))
        send_udp(port, build_packet(camera_id=0, pos_x_m=0.0))
        stderr = engine.wait_and_collect()
        assert "TOTAL frames=2" in stderr, stderr
        assert engine.proc.returncode == 0


def test_engine_rejects_invalid_hz_without_hanging():
    for bad_hz in ("0", "-10"):
        port = _fresh_port()
        with tempfile.TemporaryDirectory() as out_dir:
            try:
                start_engine(port, out_dir, hz=float(bad_hz), ready_timeout=2.0)
                raise AssertionError(f"engine should have rejected --hz {bad_hz}")
            except EngineStartupError as e:
                assert "exited early" in str(e), str(e)


def test_engine_rejects_invalid_port_without_hanging():
    for bad_port in (0, 70000):
        with tempfile.TemporaryDirectory() as out_dir:
            try:
                start_engine(bad_port, out_dir, ready_timeout=2.0)
                raise AssertionError(f"engine should have rejected --port {bad_port}")
            except EngineStartupError as e:
                assert "exited early" in str(e), str(e)


if __name__ == "__main__":
    from _runner import main
    main(sys.modules[__name__])
