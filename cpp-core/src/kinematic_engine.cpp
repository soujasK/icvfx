// kinematic_engine.cpp
// Zero-copy FreeD ingest daemon + kinematic invariant verifier.
//
// Binds a UDP socket, casts each 29-byte datagram directly onto a
// `FreeDPacket` view via std::span (no heap allocation on the hot path),
// decodes it into physical units, and runs two independent checks per the
// implementation plan:
//
//   1. Kinematic invariant check: acceleration/jerk over a 4-frame ring
//      buffer; flags > 15 m/s^2 acceleration or a near-180-degree yaw flip
//      characteristic of tracking-marker reflection/occlusion.
//   2. PTP-domain jitter check: inter-packet arrival delta vs the
//      theoretical 1/hz cadence; 3+ consecutive frames past a 2.5ms jitter
//      threshold raises the same alert condition Grafana Alerting would
//      fire on in production.
//
// Both checks are demultiplexed per camera_id (see CameraState below), so
// multiple rigs sharing one UDP port/engine process don't cross-contaminate
// each other's derivatives. Every inbound datagram is also validated for
// exact size, the 0xD1 header byte, and the FreeD checksum before it
// reaches either check; anything that fails is dropped and counted rather
// than silently corrupting the invariant state.
//
// THREADING: a dedicated receiver thread does nothing but recvfrom() into a
// queue as fast as the kernel will hand packets over; a second thread drains
// that queue and does all the decoding/invariant-check/file-I/O work. This
// split exists because a stress test found that a single-threaded
// recv-then-process-inline loop lost ~50% of a 100,000-packet instantaneous
// burst: once per-packet processing (checksum, kinematic math, three
// buffered file writes) fell behind the arrival rate, the kernel socket
// buffer filled and started dropping packets before recvfrom ever got to
// them - independent of how large SO_RCVBUF was set. Decoupling the two
// means the *receive* side stays fast enough to drain the kernel buffer
// even when the *processing* side is momentarily behind; the queue absorbs
// the burst instead of the kernel dropping it. See
// tests/stress_test_throughput.py and docs/TEST_REPORT.md for the before/
// after numbers.
//
// Output is three JSON-lines files that are schema-compatible with the
// three Kafka topics described in Phase 2 (stage.tracking.raw,
// stage.ptp.drift, stage.kinematic.anomalies) so the Python orchestrator
// can consume them exactly as it would consume real topic reads.

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <map>
#include <mutex>
#include <span>
#include <string>
#include <thread>
#include <vector>

#include "../include/freed_packet.hpp"
#include "common.hpp"

using stagesync::TraceContext;
using stagesync::json_escape;
using stagesync::now_ns;

namespace {

struct Args {
    int port = 40001;
    double hz = 120.0;
    int idle_timeout_ms = 1500;
    std::string out_dir = "runs";
};

Args parse_args(int argc, char** argv) {
    Args a;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        auto next = [&]() -> std::string { return (i + 1 < argc) ? argv[++i] : std::string{}; };
        if (arg == "--port") a.port = std::stoi(next());
        else if (arg == "--hz") a.hz = std::stod(next());
        else if (arg == "--idle-timeout-ms") a.idle_timeout_ms = std::stoi(next());
        else if (arg == "--out-dir") a.out_dir = next();
        else std::fprintf(stderr, "[kinematic_engine] warning: unrecognized arg '%s' ignored\n", arg.c_str());
    }
    if (a.hz <= 0.0) {
        std::fprintf(stderr, "[kinematic_engine] error: --hz must be > 0 (got %.4f)\n", a.hz);
        std::exit(2);
    }
    if (a.port < 1 || a.port > 65535) {
        std::fprintf(stderr, "[kinematic_engine] error: --port must be in [1,65535] (got %d)\n", a.port);
        std::exit(2);
    }
    if (a.idle_timeout_ms <= 0) {
        std::fprintf(stderr, "[kinematic_engine] error: --idle-timeout-ms must be > 0 (got %d)\n", a.idle_timeout_ms);
        std::exit(2);
    }
    return a;
}

struct RingEntry {
    int64_t rx_ns;
    double x, y, z;
    double yaw;
};

// Per-camera rolling state. Packets are demultiplexed by camera_id before
// touching any of this, so multiple concurrent camera rigs sharing one UDP
// port never cross-contaminate each other's kinematic derivatives or PTP
// jitter counters (a single shared ring buffer would otherwise compute
// nonsense velocities across two different cameras' interleaved packets).
// Only ever touched by the worker thread - no locking needed here.
struct CameraState {
    std::deque<RingEntry> ring;
    int64_t prev_rx_ns = 0;
    bool have_prev = false;
    int consecutive_jitter = 0;
    std::vector<double> jitter_samples_ms;
    long frame_count = 0;
    long anomaly_count = 0;
    long jitter_alert_events = 0;
};

constexpr size_t RECV_SCRATCH_SIZE = 256; // generously oversized vs. the 29-byte
                                           // packet so an over-length datagram is
                                           // reliably distinguishable from a
                                           // truncated read.

// One inbound datagram, captured verbatim by the receiver thread and handed
// to the worker thread for all decoding/validation/analysis. Deliberately a
// plain fixed-size POD so pushing it onto the queue is just a memcpy - no
// allocation on the receive hot path.
struct RawItem {
    std::array<uint8_t, RECV_SCRATCH_SIZE> data{};
    size_t len = 0;
    int64_t rx_ns = 0;
};

struct SharedQueue {
    std::deque<RawItem> items;
    std::mutex mtx;
    std::condition_variable cv;
    std::atomic<bool> receiving_done{false};
    std::atomic<long> max_depth_seen{0}; // high-water mark, for stress-test visibility
};

void receiver_thread_fn(int sock, SharedQueue& q) {
    std::array<uint8_t, RECV_SCRATCH_SIZE> buf{};
    while (true) {
        sockaddr_in src{};
        socklen_t srclen = sizeof(src);
        ssize_t n = recvfrom(sock, buf.data(), buf.size(), 0,
                              reinterpret_cast<sockaddr*>(&src), &srclen);
        int64_t rx_ns = now_ns();
        if (n < 0) {
            break; // idle timeout -> the take has ended
        }
        RawItem item;
        item.len = static_cast<size_t>(n);
        item.rx_ns = rx_ns;
        std::memcpy(item.data.data(), buf.data(), std::min(item.len, RECV_SCRATCH_SIZE));
        {
            std::lock_guard<std::mutex> lock(q.mtx);
            q.items.push_back(std::move(item));
            long depth = static_cast<long>(q.items.size());
            long prev_max = q.max_depth_seen.load(std::memory_order_relaxed);
            if (depth > prev_max) q.max_depth_seen.store(depth, std::memory_order_relaxed);
        }
        q.cv.notify_one();
    }
    q.receiving_done.store(true);
    q.cv.notify_one(); // wake the worker so it can observe done + drain the rest
}

// Blocks until an item is available or the receiver is done and the queue
// is empty. Returns false only in the latter case (nothing left, ever).
bool pop_item(SharedQueue& q, RawItem& out) {
    std::unique_lock<std::mutex> lock(q.mtx);
    q.cv.wait(lock, [&] { return !q.items.empty() || q.receiving_done.load(); });
    if (q.items.empty()) return false;
    out = std::move(q.items.front());
    q.items.pop_front();
    return true;
}

} // namespace

int main(int argc, char** argv) {
    Args args;
    try {
        args = parse_args(argc, argv);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[kinematic_engine] error: invalid argument value (%s)\n", e.what());
        return 2;
    }
    const double nominal_dt_ms = 1000.0 / args.hz;
    constexpr double JITTER_ALERT_THRESHOLD_MS = 2.5;
    constexpr int JITTER_ALERT_CONSEC_FRAMES = 3;
    constexpr double ACCEL_LIMIT_MPS2 = 15.0;
    constexpr double YAW_FLIP_DEG = 90.0; // per-frame yaw delta considered a "flip"

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { std::perror("socket"); return 1; }

    timeval tv{};
    tv.tv_sec = args.idle_timeout_ms / 1000;
    tv.tv_usec = (args.idle_timeout_ms % 1000) * 1000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    int opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // Bump the kernel receive buffer well past its (often small, ~200KB)
    // default so a burst well above the nominal 120-240Hz spec - or a
    // scheduling hiccup on this process - doesn't silently drop packets at
    // the socket layer before they ever reach our own code. This helps, but
    // is not sufficient by itself against a large instantaneous burst; see
    // the threading note at the top of this file for the fix that mattered.
    // Best-effort: some sandboxed/containerized kernels cap this below what
    // we ask for, which setsockopt silently clamps to rather than failing.
    int rcvbuf_bytes = 32 * 1024 * 1024;
    setsockopt(sock, SOL_SOCKET, SO_RCVBUF, &rcvbuf_bytes, sizeof(rcvbuf_bytes));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(static_cast<uint16_t>(args.port));
    if (bind(sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::perror("bind");
        close(sock);
        return 1;
    }

    std::ofstream raw_out(args.out_dir + "/stage.tracking.raw.jsonl");
    std::ofstream drift_out(args.out_dir + "/stage.ptp.drift.jsonl");
    std::ofstream anomaly_out(args.out_dir + "/stage.kinematic.anomalies.jsonl");
    if (!raw_out || !drift_out || !anomaly_out) {
        std::fprintf(stderr, "[kinematic_engine] error: could not open output files under '%s' "
                              "(does the directory exist?)\n", args.out_dir.c_str());
        close(sock);
        return 1;
    }

    std::map<uint8_t, CameraState> cameras; // keyed by camera_id - see CameraState comment
    long total_frames = 0;
    long malformed_size_count = 0;
    long bad_header_count = 0;
    long checksum_failure_count = 0;

    std::fprintf(stderr, "[kinematic_engine] listening udp/%d (nominal_dt=%.4fms)\n",
                 args.port, nominal_dt_ms);

    SharedQueue queue;
    std::thread receiver(receiver_thread_fn, sock, std::ref(queue));

    RawItem item;
    while (pop_item(queue, item)) {
        int64_t rx_ns = item.rx_ns;

        if (item.len != sizeof(FreeDPacket)) {
            malformed_size_count++;
            continue; // wrong-size datagram (truncated, oversized, or garbage), drop
        }

        std::span<const uint8_t> bytes(item.data.data(), item.len);
        const FreeDPacket* pkt = freed_codec::view_as_packet(bytes); // zero-copy view
        if (!pkt || pkt->header != FREED_HEADER) {
            bad_header_count++;
            continue;
        }
        if (freed_codec::compute_checksum(*pkt) != pkt->checksum) {
            checksum_failure_count++;
            continue; // corrupt on the wire; do not let bad data reach the invariant checks
        }

        auto sample = freed_codec::decode(*pkt, rx_ns);
        total_frames++;
        CameraState& cam = cameras[sample.camera_id]; // demux by camera_id
        cam.frame_count++;

        TraceContext trace;
        std::string traceparent = trace.traceparent();

        // ---- PTP-domain jitter check (per camera) ------------------------
        double jitter_ms = 0.0;
        bool jitter_violation = false;
        if (cam.have_prev) {
            double actual_dt_ms = static_cast<double>(rx_ns - cam.prev_rx_ns) / 1'000'000.0;
            jitter_ms = actual_dt_ms - nominal_dt_ms;
            jitter_violation = std::fabs(jitter_ms) > JITTER_ALERT_THRESHOLD_MS;
            cam.jitter_samples_ms.push_back(std::fabs(jitter_ms));
        }
        cam.prev_rx_ns = rx_ns;
        cam.have_prev = true;

        cam.consecutive_jitter = jitter_violation ? (cam.consecutive_jitter + 1) : 0;
        bool ptp_alert = cam.consecutive_jitter >= JITTER_ALERT_CONSEC_FRAMES;
        if (ptp_alert && cam.consecutive_jitter == JITTER_ALERT_CONSEC_FRAMES) {
            cam.jitter_alert_events++;
        }

        drift_out << "{\"topic\":\"stage.ptp.drift\",\"camera_id\":" << (int)sample.camera_id
                   << ",\"rx_ns\":" << rx_ns
                   << ",\"jitter_ms\":" << jitter_ms
                   << ",\"consecutive_violations\":" << cam.consecutive_jitter
                   << ",\"alert\":" << (ptp_alert ? "true" : "false")
                   << ",\"traceparent\":\"" << traceparent << "\"}\n";

        // ---- Kinematic invariant check (per camera) -----------------------
        cam.ring.push_back({rx_ns, sample.pos_x_m, sample.pos_y_m, sample.pos_z_m, sample.yaw_deg});
        if (cam.ring.size() > 4) cam.ring.pop_front();

        bool kinematic_violation = false;
        std::string violation_reason;
        double accel_mag = 0.0;
        double yaw_delta = 0.0;

        if (cam.ring.size() >= 2) {
            const auto& a = cam.ring[cam.ring.size() - 2];
            const auto& b = cam.ring[cam.ring.size() - 1];
            yaw_delta = std::fabs(b.yaw - a.yaw);
            if (yaw_delta > 180.0) yaw_delta = 360.0 - yaw_delta; // wrap
            if (yaw_delta > YAW_FLIP_DEG) {
                kinematic_violation = true;
                violation_reason = "sudden_rotation_flip";
            }
        }
        if (cam.ring.size() >= 3) {
            const auto& a = cam.ring[cam.ring.size() - 3];
            const auto& b = cam.ring[cam.ring.size() - 2];
            const auto& c = cam.ring[cam.ring.size() - 1];
            // Derivatives use the nominal frame cadence (1/hz), not the raw
            // measured inter-arrival time. Kinematic plausibility is a
            // property of the physical camera move at the encoder's known
            // sample rate; per-packet arrival jitter (queueing, scheduler
            // noise, network buffer bloat) is a *separate* concern already
            // captured by the PTP-domain jitter check above. Feeding noisy
            // measured dt into a double finite-difference would amplify
            // timing jitter into spurious acceleration spikes.
            double dt1 = nominal_dt_ms / 1000.0;
            double dt2 = dt1;
            double vx1 = (b.x - a.x) / dt1, vy1 = (b.y - a.y) / dt1, vz1 = (b.z - a.z) / dt1;
            double vx2 = (c.x - b.x) / dt2, vy2 = (c.y - b.y) / dt2, vz2 = (c.z - b.z) / dt2;
            double dt_mid = dt1;
            double ax = (vx2 - vx1) / dt_mid, ay = (vy2 - vy1) / dt_mid, az = (vz2 - vz1) / dt_mid;
            accel_mag = std::sqrt(ax * ax + ay * ay + az * az);
            if (accel_mag > ACCEL_LIMIT_MPS2) {
                kinematic_violation = true;
                violation_reason = violation_reason.empty() ? "acceleration_limit_exceeded"
                                                              : violation_reason + "+acceleration_limit_exceeded";
            }
        }

        if (kinematic_violation) {
            cam.anomaly_count++;
            anomaly_out << "{\"topic\":\"stage.kinematic.anomalies\",\"camera_id\":" << (int)sample.camera_id
                        << ",\"rx_ns\":" << rx_ns
                        << ",\"reason\":\"" << json_escape(violation_reason) << "\""
                        << ",\"accel_mps2\":" << accel_mag
                        << ",\"yaw_delta_deg\":" << yaw_delta
                        << ",\"pos_x_m\":" << sample.pos_x_m
                        << ",\"pos_y_m\":" << sample.pos_y_m
                        << ",\"pos_z_m\":" << sample.pos_z_m
                        << ",\"traceparent\":\"" << traceparent << "\"}\n";
        }

        raw_out << "{\"topic\":\"stage.tracking.raw\",\"camera_id\":" << (int)sample.camera_id
                << ",\"rx_ns\":" << rx_ns
                << ",\"pitch_deg\":" << sample.pitch_deg
                << ",\"yaw_deg\":" << sample.yaw_deg
                << ",\"roll_deg\":" << sample.roll_deg
                << ",\"pos_x_m\":" << sample.pos_x_m
                << ",\"pos_y_m\":" << sample.pos_y_m
                << ",\"pos_z_m\":" << sample.pos_z_m
                << ",\"zoom\":" << sample.zoom
                << ",\"focus\":" << sample.focus
                << ",\"traceparent\":\"" << traceparent << "\"}\n";
    }

    receiver.join();

    // ---- Summary (stand-in for Prometheus remote-write metrics) ---------
    long anomaly_count_total = 0;
    long jitter_alert_events_total = 0;
    for (auto& [camera_id, cam] : cameras) {
        std::sort(cam.jitter_samples_ms.begin(), cam.jitter_samples_ms.end());
        auto pct = [&](double p) -> double {
            if (cam.jitter_samples_ms.empty()) return 0.0;
            size_t idx = std::min(cam.jitter_samples_ms.size() - 1,
                                   static_cast<size_t>(p * cam.jitter_samples_ms.size()));
            return cam.jitter_samples_ms[idx];
        };
        std::fprintf(stderr,
            "[kinematic_engine] camera_id=%d frames=%ld jitter_p95_ms=%.4f jitter_p99_ms=%.4f "
            "kinematic_jerk_violations_total=%ld ptp_alert_events=%ld\n",
            (int)camera_id, cam.frame_count, pct(0.95), pct(0.99), cam.anomaly_count, cam.jitter_alert_events);
        anomaly_count_total += cam.anomaly_count;
        jitter_alert_events_total += cam.jitter_alert_events;
    }

    std::fprintf(stderr,
        "[kinematic_engine] TOTAL frames=%ld cameras=%zu kinematic_jerk_violations_total=%ld "
        "ptp_alert_events=%ld dropped_wrong_size=%ld dropped_bad_header=%ld dropped_checksum_failed=%ld "
        "max_queue_depth=%ld\n",
        total_frames, cameras.size(), anomaly_count_total, jitter_alert_events_total,
        malformed_size_count, bad_header_count, checksum_failure_count,
        queue.max_depth_seen.load());

    close(sock);
    return 0;
}
