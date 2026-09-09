// test_codec.cpp
// Standalone unit test for freed_packet.hpp - no test framework dependency,
// so it builds with a single g++ invocation and no network access. Exits
// 0 on success, non-zero (with a message identifying the failing check) on
// any assertion failure. Run via ../run_tests.sh.

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "../include/freed_packet.hpp"

static int g_failures = 0;

#define CHECK(cond, msg) \
    do { \
        if (!(cond)) { \
            std::fprintf(stderr, "[FAIL] %s (line %d): %s\n", msg, __LINE__, #cond); \
            g_failures++; \
        } else { \
            std::fprintf(stderr, "[ OK ] %s\n", msg); \
        } \
    } while (0)

static void test_wire_size() {
    CHECK(sizeof(FreeDPacket) == 29, "FreeDPacket is exactly 29 bytes on the wire");
}

static void test_round_trip_normal_values() {
    auto pkt = freed_codec::encode(/*camera_id=*/7, /*pitch=*/-12.5, /*yaw=*/45.25, /*roll=*/0.1,
                                    /*x=*/1.234, /*y=*/1.6, /*z=*/-3.5,
                                    /*zoom=*/2000, /*focus=*/1500, /*user_def=*/42);
    auto sample = freed_codec::decode(pkt, /*rx_ns=*/0);

    CHECK(sample.camera_id == 7, "camera_id round-trips exactly");
    // 24-bit fixed point at 1/32768 degree / 1/64000 m has quantization
    // error well under 1e-3 for these magnitudes; use a generous tolerance.
    CHECK(std::fabs(sample.pitch_deg - (-12.5)) < 1e-3, "pitch round-trips within quantization tolerance");
    CHECK(std::fabs(sample.yaw_deg - 45.25) < 1e-3, "yaw round-trips within quantization tolerance");
    CHECK(std::fabs(sample.pos_x_m - 1.234) < 1e-3, "pos_x round-trips within quantization tolerance");
    CHECK(std::fabs(sample.pos_y_m - 1.6) < 1e-3, "pos_y round-trips within quantization tolerance");
    CHECK(std::fabs(sample.pos_z_m - (-3.5)) < 1e-3, "pos_z round-trips within quantization tolerance");
    CHECK(sample.zoom == 2000, "zoom round-trips exactly");
    CHECK(sample.focus == 1500, "focus round-trips exactly");
}

static void test_checksum_self_consistent() {
    auto pkt = freed_codec::encode(1, 0, 0, 0, 0, 0, 0, 0, 0);
    CHECK(freed_codec::compute_checksum(pkt) == pkt.checksum,
          "compute_checksum(encode(...)) matches the packet's own checksum byte");
}

static void test_checksum_detects_single_byte_corruption() {
    auto pkt = freed_codec::encode(1, 10, 20, 0, 1, 2, 3, 0, 0);
    uint8_t original_yaw_byte = pkt.yaw[1];
    pkt.yaw[1] = static_cast<uint8_t>(original_yaw_byte ^ 0xFF); // flip every bit in one field byte
    CHECK(freed_codec::compute_checksum(pkt) != pkt.checksum,
          "a single corrupted payload byte is caught by the checksum (ingest daemon must drop this)");
}

static void test_out_of_range_saturates_instead_of_wrapping() {
    // Before the clamp_i24 fix, encoding a wildly out-of-range physical
    // value (e.g. a bad upstream sensor reading, or 1000 meters of dolly
    // travel) would silently truncate/wrap the 24-bit field, potentially
    // producing a plausible-looking but completely wrong decoded position
    // - the worst kind of bug, because nothing downstream would notice.
    // This test locks in the fix: it must saturate to the encoder's max
    // representable value instead.
    double huge_pos_x_m = 1'000'000.0; // far beyond the ~131m representable range
    auto pkt = freed_codec::encode(1, 0, 0, 0, huge_pos_x_m, 0, 0, 0, 0);
    auto sample = freed_codec::decode(pkt, 0);

    double max_representable_m = freed_codec::I24_MAX / 64000.0; // ~131.07m
    CHECK(sample.pos_x_m > 0, "saturated value stays positive (does not wrap to a negative pose)");
    CHECK(std::fabs(sample.pos_x_m - max_representable_m) < 1e-2,
          "out-of-range pos_x saturates to the encoder's max representable value, not garbage");

    double huge_negative_yaw = -999999.0;
    auto pkt2 = freed_codec::encode(1, 0, huge_negative_yaw, 0, 0, 0, 0, 0, 0);
    auto sample2 = freed_codec::decode(pkt2, 0);
    double min_representable_deg = freed_codec::I24_MIN / 32768.0;
    CHECK(std::fabs(sample2.yaw_deg - min_representable_deg) < 1e-2,
          "out-of-range negative yaw saturates to the encoder's min representable value");
}

static void test_zero_copy_view_rejects_wrong_size() {
    uint8_t small_buf[10] = {0};
    auto view = freed_codec::view_as_packet(std::span<const uint8_t>(small_buf, 10));
    CHECK(view == nullptr, "view_as_packet refuses a buffer that isn't exactly 29 bytes");
}

int main() {
    test_wire_size();
    test_round_trip_normal_values();
    test_checksum_self_consistent();
    test_checksum_detects_single_byte_corruption();
    test_out_of_range_saturates_instead_of_wrapping();
    test_zero_copy_view_rejects_wrong_size();

    if (g_failures == 0) {
        std::fprintf(stderr, "\ntest_codec: ALL CHECKS PASSED\n");
        return 0;
    }
    std::fprintf(stderr, "\ntest_codec: %d CHECK(S) FAILED\n", g_failures);
    return 1;
}
