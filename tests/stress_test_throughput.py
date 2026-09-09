"""Throughput / load stress tests for cpp-core/bin/kinematic_engine.

The plan's Sprint 2 milestone calls for "load testing at 10,000 pkts/sec".
These tests measure actual achieved throughput and packet loss against
that target using the real compiled binaries - not an estimate.

Three distinct load shapes are tested, because they stress different
things:
  1. Single-camera burst  - raw max ingestion rate, unpaced
  2. Concurrent multi-camera burst - N independent camera rigs hitting the
     same UDP port/engine process at once (tests the per-camera state map
     under real concurrency, not just correctness in isolation)
  3. Sustained paced high-rate stream - holds a fixed high Hz for several
     real-time seconds (unlike a burst, this exercises the recv loop over
     sustained wall-clock duration, closer to what "10,000 pkts/sec in
     production" actually means)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_harness import start_engine, ENGINE_BIN, GENERATOR_BIN  # noqa: E402

NEXT_PORT = [42001]


def _fresh_port() -> int:
    NEXT_PORT[0] += 1
    return NEXT_PORT[0]


def _parse_total_frames(stderr: str) -> int:
    m = re.search(r"TOTAL frames=(\d+)", stderr)
    assert m, f"could not find TOTAL frames in engine output: {stderr}"
    return int(m.group(1))


def _parse_camera_frames(stderr: str, camera_id: int) -> int:
    m = re.search(rf"camera_id={camera_id} frames=(\d+)", stderr)
    assert m, f"could not find camera_id={camera_id} frames in engine output: {stderr}"
    return int(m.group(1))


def _parse_dropped(stderr: str) -> dict[str, int]:
    out = {}
    for key in ("dropped_wrong_size", "dropped_bad_header", "dropped_checksum_failed"):
        m = re.search(rf"{key}=(\d+)", stderr)
        out[key] = int(m.group(1)) if m else -1
    return out


def test_single_camera_burst_10000_packets_zero_loss():
    """Directly targets the plan's stated 10,000 pkts/sec load test."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=2000)
        gen = subprocess.run([GENERATOR_BIN, "--port", str(port), "--burst", "10000"],
                              capture_output=True, text=True, timeout=30)
        stderr = engine.wait_and_collect(timeout=5.0)

        rate_match = re.search(r"achieved_rate_pkts_per_sec=([\d.]+)", gen.stderr)
        send_rate = float(rate_match.group(1)) if rate_match else -1
        total = _parse_total_frames(stderr)
        dropped = _parse_dropped(stderr)

        print(f"    send_rate={send_rate:.0f} pkts/sec, received={total}/10000, dropped={dropped}")
        assert total == 10000, f"expected all 10000 packets ingested, got {total} (dropped={dropped})"
        assert sum(dropped.values()) == 0, f"unexpected packet drops: {dropped}"


def test_single_camera_burst_100000_packets_loss_under_1pct():
    """An order of magnitude beyond the plan's target, to find the actual
    ceiling rather than just clearing the stated bar."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=3000)
        gen = subprocess.run([GENERATOR_BIN, "--port", str(port), "--burst", "100000"],
                              capture_output=True, text=True, timeout=30)
        stderr = engine.wait_and_collect(timeout=6.0)

        rate_match = re.search(r"achieved_rate_pkts_per_sec=([\d.]+)", gen.stderr)
        send_rate = float(rate_match.group(1)) if rate_match else -1
        total = _parse_total_frames(stderr)
        loss_pct = 100.0 * (100000 - total) / 100000.0

        print(f"    send_rate={send_rate:.0f} pkts/sec, received={total}/100000, loss={loss_pct:.3f}%")
        assert loss_pct < 1.0, f"loss {loss_pct:.2f}% exceeds the 1% tolerance at 100k packets"


def test_concurrent_multi_camera_burst_finds_the_real_limit():
    """4 simulated camera rigs each burst 10,000 unpaced packets
    *simultaneously* (40,000 packets total, sent as fast as each process
    can manage - not at any real camera's actual rate). This is a
    deliberately adversarial synthetic load, not a realistic one (see
    test_concurrent_multi_camera_realistic_paced_rate below for that) - its
    purpose is to characterize where the ceiling actually is.

    A companion diagnostic (docs/TEST_REPORT.md) isolated the cause: on
    this sandbox's single CPU core (nproc=1), N simultaneously-runnable
    sender processes starve the engine's receiver thread of scheduling
    slices, and packets pile up in the *kernel* socket buffer during those
    gaps - a ceiling no amount of user-space queueing can fix, since the
    packets are lost before recvfrom() ever sees them. Measured on this
    box: 1 sender x 40k = 0% loss, 2 concurrent x 10k = 0% loss, 3
    concurrent x 10k = ~13% loss, 4 concurrent x 10k = loss (this test).
    On real multi-core stage hardware this ceases to be a ceiling at all
    once the kernel and the receiver thread can run on different cores.

    So this test does NOT assert zero loss (that would be asserting
    something about this sandbox's core count, not about the code). It
    asserts the property that actually matters: no crash, and - critically
    - no cross-camera contamination even while lossy. A camera's received
    count must never exceed what was sent, and the TOTAL must equal the
    sum of the per-camera counts exactly (i.e. loss is real packet loss,
    never one camera's packets miscounted onto another's tally).
    """
    port = _fresh_port()
    n_cameras = 4
    per_camera = 10000
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, idle_timeout_ms=3000)
        procs = [
            subprocess.Popen([GENERATOR_BIN, "--port", str(port), "--camera-id", str(cam_id),
                               "--burst", str(per_camera)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            for cam_id in range(1, n_cameras + 1)
        ]
        for p in procs:
            p.communicate(timeout=30)
            assert p.returncode == 0

        stderr = engine.wait_and_collect(timeout=6.0)
        total = _parse_total_frames(stderr)
        expected_total = n_cameras * per_camera
        loss_pct = 100.0 * (expected_total - total) / expected_total

        per_camera_counts = {cam_id: _parse_camera_frames(stderr, cam_id) for cam_id in range(1, n_cameras + 1)}
        print(f"    {n_cameras} concurrent unpaced cameras x {per_camera} pkts each: "
              f"received={total}/{expected_total} (loss={loss_pct:.1f}%, environment-bound - see docstring), "
              f"per_camera={per_camera_counts}")

        # The property that must always hold, loss or no loss:
        assert sum(per_camera_counts.values()) == total, "per-camera counts must sum exactly to TOTAL"
        for cam_id, count in per_camera_counts.items():
            assert 0 <= count <= per_camera, (
                f"camera {cam_id} received {count} but only {per_camera} were ever sent to it - "
                f"this would indicate cross-camera contamination, not just loss"
            )
        assert engine.proc.returncode == 0, "engine must exit cleanly even when the kernel dropped packets"


def test_concurrent_multi_camera_realistic_paced_rate():
    """The scenario that actually matters for production: 4 camera rigs
    each streaming at a real-world rate (240Hz, the top of the plan's
    120-240Hz spec) *concurrently* for 2 real-time seconds - 480 pkts/sec
    combined, nowhere near the burst ceiling above. This is what Sprint 2's
    Kafka partitioning-by-camera_id design actually assumes multiple rigs
    look like on the wire, and it must be lossless."""
    port = _fresh_port()
    n_cameras = 4
    hz = 240.0
    duration_s = 2.0
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, hz=hz, idle_timeout_ms=2000)
        procs = [
            subprocess.Popen([GENERATOR_BIN, "--port", str(port), "--camera-id", str(cam_id),
                               "--hz", str(hz), "--duration", str(duration_s), "--scenario", "normal"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            for cam_id in range(1, n_cameras + 1)
        ]
        for p in procs:
            p.communicate(timeout=15)
            assert p.returncode == 0

        stderr = engine.wait_and_collect(timeout=5.0)
        total = _parse_total_frames(stderr)
        expected_per_camera = int(hz * duration_s)
        expected_total = n_cameras * expected_per_camera

        print(f"    {n_cameras} concurrent cameras @ {hz:.0f}Hz x {duration_s}s (realistic rate): "
              f"received={total}/{expected_total}")
        assert total == expected_total, (
            f"realistic-rate concurrent multi-camera streaming must be lossless: "
            f"got {total}/{expected_total}"
        )
        for cam_id in range(1, n_cameras + 1):
            cam_frames = _parse_camera_frames(stderr, cam_id)
            assert cam_frames == expected_per_camera, f"camera {cam_id}: expected {expected_per_camera}, got {cam_frames}"


def test_sustained_high_rate_stream_5000hz_for_3s():
    """Not a burst: a real-time-paced 5000Hz stream held for 3 wall-clock
    seconds (15,000 packets), exercising the recv loop over sustained
    duration rather than a sub-100ms instant blast."""
    port = _fresh_port()
    with tempfile.TemporaryDirectory() as out_dir:
        engine = start_engine(port, out_dir, hz=5000, idle_timeout_ms=2000)
        gen = subprocess.run(
            [GENERATOR_BIN, "--port", str(port), "--hz", "5000", "--duration", "3", "--scenario", "normal"],
            capture_output=True, text=True, timeout=15,
        )
        stderr = engine.wait_and_collect(timeout=5.0)
        total = _parse_total_frames(stderr)
        expected = 15000

        print(f"    sustained 5000Hz x 3s: received={total}/{expected} "
              f"({100.0 * total / expected:.2f}%)")
        assert total >= int(expected * 0.99), f"expected >=99% of {expected} packets, got {total}"


if __name__ == "__main__":
    from _runner import main
    main(sys.modules[__name__])
