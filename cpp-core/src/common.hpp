// common.hpp
// Lightweight W3C trace-context helpers and JSONL sink used across the ingest
// daemon and packet generator.
//
// NOTE on scope: the implementation plan specifies OpenTelemetry C++ SDK
// instrumentation exporting to Grafana Tempo. Standing up a real OTLP
// collector / Grafana Cloud tenant is outside what a sandboxed build can
// exercise, so this header generates W3C-compliant `traceparent` values
// (version-trace_id-span_id-flags) by hand and writes structured JSON lines
// that are schema-compatible with what the real OTel exporter would emit.
// Swapping this for `opentelemetry-cpp` in a real deployment only touches
// `emit_span()`; call sites are unaffected.

#pragma once

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <random>
#include <sstream>
#include <string>

namespace stagesync {

inline std::string to_hex(uint64_t hi, uint64_t lo, int hex_chars) {
    std::ostringstream oss;
    oss << std::hex << std::nouppercase;
    if (hex_chars > 16) {
        oss.width(hex_chars - 16);
        oss.fill('0');
        oss << hi;
        oss.width(16);
        oss.fill('0');
        oss << lo;
    } else {
        oss.width(hex_chars);
        oss.fill('0');
        oss << (lo & ((hex_chars == 16) ? ~0ULL : ((1ULL << (hex_chars * 4)) - 1)));
    }
    return oss.str();
}

// Generates a fresh 128-bit trace id / 64-bit span id pair and formats a
// W3C traceparent header: "00-<32 hex trace id>-<16 hex span id>-01"
class TraceContext {
public:
    TraceContext() {
        static thread_local std::mt19937_64 rng{std::random_device{}()};
        trace_hi_ = rng();
        trace_lo_ = rng();
        span_id_  = rng();
    }

    std::string traceparent() const {
        std::ostringstream oss;
        oss << "00-" << to_hex(trace_hi_, trace_lo_, 32) << "-" << to_hex(0, span_id_, 16) << "-01";
        return oss.str();
    }

private:
    uint64_t trace_hi_;
    uint64_t trace_lo_;
    uint64_t span_id_;
};

// PTP-domain-ish monotonic nanosecond clock. Falls back to CLOCK_MONOTONIC
// if CLOCK_TAI is unavailable in the runtime environment (e.g. some
// containers), so the daemon degrades gracefully rather than failing to
// start; a real stage deployment runs on a PTP-disciplined NIC/kernel where
// CLOCK_TAI tracks the grandmaster.
inline int64_t now_ns() {
    struct timespec ts{};
#ifdef CLOCK_TAI
    if (clock_gettime(CLOCK_TAI, &ts) != 0) {
        clock_gettime(CLOCK_MONOTONIC, &ts);
    }
#else
    clock_gettime(CLOCK_MONOTONIC, &ts);
#endif
    return static_cast<int64_t>(ts.tv_sec) * 1'000'000'000LL + ts.tv_nsec;
}

inline std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        if (c == '"' || c == '\\') out.push_back('\\');
        out.push_back(c);
    }
    return out;
}

} // namespace stagesync
