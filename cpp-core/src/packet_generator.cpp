// packet_generator.cpp
// Synthetic FreeD (0xD1) UDP packet generator standing in for a real
// OptiTrack/Mo-Sys/Vicon FreeD emitter on the stage. Emits a smooth camera
// move at the requested rate (default 120 Hz) over loopback UDP, with three
// selectable fault-injection scenarios used by the Sprint 5 test harness:
//
//   normal      - clean sinusoidal pan/dolly move, steady 8.333ms cadence
//   occlusion   - injects an implausible position/rotation jump (marker
//                 reflection / boom-mic occlusion) for a short window
//   ptp_jitter  - motion stays kinematically smooth, but packet SEND timing
//                 is perturbed for 3+ consecutive frames to simulate
//                 network buffer bloat / PTP grandmaster drift
//
// --burst N sends N valid, unpaced packets as fast as possible instead of
// the scenario/hz-paced loop, for throughput/load testing (see
// tests/stress_test_throughput.py).
//
// Usage:
//   packet_generator --port 40001 --hz 120 --duration 8 --scenario occlusion
//   packet_generator --port 40001 --burst 10000

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "../include/freed_packet.hpp"
#include "common.hpp"

namespace {

struct Args {
    int port = 40001;
    double hz = 120.0;
    double duration_s = 8.0;
    std::string scenario = "normal";
    std::string host = "127.0.0.1";
    uint8_t camera_id = 1;
    long burst = 0; // if > 0: ignore hz/duration/scenario pacing and blast this many packets back-to-back
};

const std::vector<std::string> KNOWN_SCENARIOS = {"normal", "occlusion", "ptp_jitter"};

Args parse_args(int argc, char** argv) {
    Args a;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        auto next = [&]() -> std::string { return (i + 1 < argc) ? argv[++i] : std::string{}; };
        if (arg == "--port") a.port = std::stoi(next());
        else if (arg == "--hz") a.hz = std::stod(next());
        else if (arg == "--duration") a.duration_s = std::stod(next());
        else if (arg == "--scenario") a.scenario = next();
        else if (arg == "--host") a.host = next();
        else if (arg == "--camera-id") a.camera_id = static_cast<uint8_t>(std::stoi(next()));
        else if (arg == "--burst") a.burst = std::stol(next());
        else std::fprintf(stderr, "[generator] warning: unrecognized arg '%s' ignored\n", arg.c_str());
    }
    if (a.burst == 0 &&
        std::find(KNOWN_SCENARIOS.begin(), KNOWN_SCENARIOS.end(), a.scenario) == KNOWN_SCENARIOS.end()) {
        std::fprintf(stderr, "[generator] warning: unknown scenario '%s' -> no fault will be injected "
                              "(known: normal, occlusion, ptp_jitter)\n", a.scenario.c_str());
    }
    if (a.hz <= 0.0) {
        std::fprintf(stderr, "[generator] error: --hz must be > 0 (got %.4f)\n", a.hz);
        std::exit(2);
    }
    if (a.duration_s < 0.0) {
        std::fprintf(stderr, "[generator] error: --duration must be >= 0 (got %.4f)\n", a.duration_s);
        std::exit(2);
    }
    if (a.port < 1 || a.port > 65535) {
        std::fprintf(stderr, "[generator] error: --port must be in [1,65535] (got %d)\n", a.port);
        std::exit(2);
    }
    if (a.burst < 0) {
        std::fprintf(stderr, "[generator] error: --burst must be >= 0 (got %ld)\n", a.burst);
        std::exit(2);
    }
    return a;
}

} // namespace

// Sends `count` valid, unpaced packets as fast as the loop + syscalls allow
// - a genuine max-throughput probe, as opposed to the paced loop below
// which deliberately holds to a nominal cadence and so under-reports raw
// capacity. Used by tests/stress_test_throughput.py to characterize
// sustainable pkts/sec against the plan's 10,000 pkts/sec load-test target.
static void run_burst(int sock, const sockaddr_in& dest, uint8_t camera_id, long count) {
    auto pkt = freed_codec::encode(camera_id, 0.0, 0.0, 0.0, 1.0, 1.6, 3.0, 2000, 1500);
    auto t0 = std::chrono::steady_clock::now();
    long sent_ok = 0;
    for (long i = 0; i < count; ++i) {
        ssize_t sent = sendto(sock, &pkt, sizeof(pkt), 0,
                               reinterpret_cast<const sockaddr*>(&dest), sizeof(dest));
        if (sent == static_cast<ssize_t>(sizeof(pkt))) sent_ok++;
    }
    auto t1 = std::chrono::steady_clock::now();
    double elapsed_s = std::chrono::duration<double>(t1 - t0).count();
    double rate = elapsed_s > 0 ? sent_ok / elapsed_s : 0.0;
    std::fprintf(stderr, "[generator] BURST sent_ok=%ld/%ld elapsed_s=%.4f achieved_rate_pkts_per_sec=%.1f\n",
                 sent_ok, count, elapsed_s, rate);
}

int main(int argc, char** argv) {
    Args args;
    try {
        args = parse_args(argc, argv);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "[generator] error: invalid argument value (%s)\n", e.what());
        return 2;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        std::perror("socket");
        return 1;
    }

    sockaddr_in dest{};
    dest.sin_family = AF_INET;
    dest.sin_port = htons(static_cast<uint16_t>(args.port));
    if (inet_pton(AF_INET, args.host.c_str(), &dest.sin_addr) != 1) {
        std::fprintf(stderr, "invalid host: %s\n", args.host.c_str());
        return 1;
    }

    if (args.burst > 0) {
        std::fprintf(stderr, "[generator] BURST mode: camera_id=%d count=%ld -> %s:%d\n",
                     args.camera_id, args.burst, args.host.c_str(), args.port);
        run_burst(sock, dest, args.camera_id, args.burst);
        close(sock);
        std::fprintf(stderr, "[generator] done\n");
        return 0;
    }

    const double nominal_dt_s = 1.0 / args.hz;
    const int total_frames = static_cast<int>(args.duration_s * args.hz);

    // Fault-injection windows, expressed in frame indices.
    const int occlusion_start = total_frames * 3 / 8;
    const int occlusion_len = std::max(3, static_cast<int>(args.hz * 0.25)); // ~250ms glitch
    const int jitter_start = total_frames * 3 / 8;
    const int jitter_len = 5; // 5 consecutive delayed frames, well above the 3-frame alert threshold

    std::fprintf(stderr,
                 "[generator] scenario=%s hz=%.1f duration=%.1fs frames=%d -> %s:%d\n",
                 args.scenario.c_str(), args.hz, args.duration_s, total_frames,
                 args.host.c_str(), args.port);

    for (int frame = 0; frame < total_frames; ++frame) {
        double t = frame * nominal_dt_s;

        // Baseline smooth move: slow yaw pan + gentle dolly-in on X, fixed height.
        double yaw = 15.0 * std::sin(0.15 * t);
        double pitch = -2.0 + 1.0 * std::sin(0.05 * t);
        double roll = 0.0;
        double pos_x = 0.5 * t;
        double pos_y = 1.6;
        double pos_z = 3.0 - 0.05 * t;

        bool in_occlusion = (args.scenario == "occlusion") &&
                             (frame >= occlusion_start) && (frame < occlusion_start + occlusion_len);

        if (in_occlusion) {
            // Simulate a marker-occlusion glitch: tracker briefly reports a
            // reflected/implausible pose - large yaw flip and a position
            // teleport inconsistent with the surrounding smooth trajectory.
            int k = frame - occlusion_start;
            double glitch_phase = static_cast<double>(k) / occlusion_len;
            yaw += 165.0 * std::sin(glitch_phase * M_PI); // near-180 degree flip at mid-window
            pos_x += 0.8 * std::sin(glitch_phase * M_PI * 2.0);
            pos_z += 0.6 * std::cos(glitch_phase * M_PI * 3.0);
        }

        auto pkt = freed_codec::encode(args.camera_id, pitch, yaw, roll, pos_x, pos_y, pos_z,
                                        /*zoom=*/2000, /*focus=*/1500);

        ssize_t sent = sendto(sock, &pkt, sizeof(pkt), 0,
                               reinterpret_cast<sockaddr*>(&dest), sizeof(dest));
        if (sent != static_cast<ssize_t>(sizeof(pkt))) {
            std::perror("sendto");
        }

        bool in_jitter = (args.scenario == "ptp_jitter") &&
                          (frame >= jitter_start) && (frame < jitter_start + jitter_len);

        double sleep_s = nominal_dt_s;
        if (in_jitter) {
            // Delay well past the 2.5ms alert threshold used by Grafana Alerting.
            sleep_s = nominal_dt_s + 0.004; // +4ms -> 12.3ms actual gap vs 8.33ms nominal
        }

        std::this_thread::sleep_for(std::chrono::duration<double>(sleep_s));
    }

    close(sock);
    std::fprintf(stderr, "[generator] done\n");
    return 0;
}
