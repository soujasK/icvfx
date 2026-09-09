// freed_packet.hpp
// Bitfield-exact FreeD D1 (0xD1) datagram layout + zero-copy encode/decode helpers.
//
// Wire format (29 bytes, big-endian fields):
//   [0]      header      0xD1
//   [1]      camera_id   0x00-0xFF
//   [2..4]   pitch       24-bit signed fixed point, units of 1/32768 degree
//   [5..7]   yaw         24-bit signed fixed point, units of 1/32768 degree
//   [8..10]  roll        24-bit signed fixed point, units of 1/32768 degree
//   [11..13] pos_z       24-bit signed integer, units of 1/64 mm
//   [14..16] pos_x       24-bit signed integer, units of 1/64 mm
//   [17..19] pos_y       24-bit signed integer, units of 1/64 mm
//   [20..21] zoom        16-bit encoder count
//   [22..23] focus       16-bit encoder count
//   [24..25] user_def    16-bit user-defined
//   [26..27] reserved    protocol-version / spare bytes
//   [28]     checksum    two's complement of sum of bytes [0..27], mod 256
//
// NOTE: the plan's own struct listing (header + camera_id + 3x24-bit
// rotation + 3x24-bit position + 2x16-bit lens + 16-bit user_def + 1-byte
// checksum) sums to 27 bytes, one short of the "29-byte message payload"
// stated in section 1/3. This implementation adds the 2-byte `reserved`
// field below to reconcile the two and land on the stated 29-byte wire
// size, consistent with real-world FreeD D1 datagrams.

#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <span>

#pragma pack(push, 1)
struct FreeDPacket {
    uint8_t header;      // 0xD1
    uint8_t camera_id;   // 0x00 to 0xFF
    uint8_t pitch[3];    // 24-bit signed fixed point
    uint8_t yaw[3];
    uint8_t roll[3];
    uint8_t pos_z[3];    // 24-bit signed integer
    uint8_t pos_x[3];
    uint8_t pos_y[3];
    uint8_t zoom[2];     // 16-bit encoder
    uint8_t focus[2];
    uint8_t user_def[2];
    uint8_t reserved[2]; // protocol-version / spare, see NOTE above
    uint8_t checksum;
};
#pragma pack(pop)

static_assert(sizeof(FreeDPacket) == 29, "FreeD D1 packet must be exactly 29 bytes on the wire");

constexpr uint8_t FREED_HEADER = 0xD1;

// Decoded, physically-scaled kinematic sample.
struct KinematicSample {
    uint8_t  camera_id{};
    double   pitch_deg{};
    double   yaw_deg{};
    double   roll_deg{};
    double   pos_x_m{};
    double   pos_y_m{};
    double   pos_z_m{};
    uint16_t zoom{};
    uint16_t focus{};
    // Host-side receive timestamp, nanoseconds, CLOCK_TAI domain (PTP-aligned).
    int64_t  rx_ns{};
};

namespace freed_codec {

// Sign-extend a 24-bit big-endian field into a 32-bit signed integer.
inline int32_t decode_i24_be(const uint8_t b[3]) {
    uint32_t raw = (static_cast<uint32_t>(b[0]) << 16) |
                   (static_cast<uint32_t>(b[1]) << 8)  |
                    static_cast<uint32_t>(b[2]);
    // Sign-extend from bit 23.
    if (raw & 0x00800000u) {
        raw |= 0xFF000000u;
    }
    int32_t signedVal;
    std::memcpy(&signedVal, &raw, sizeof(signedVal));
    return signedVal;
}

constexpr int32_t I24_MIN = -8388608; // -2^23
constexpr int32_t I24_MAX = 8388607;  //  2^23 - 1

// Saturates a value to the representable 24-bit signed range instead of
// letting it silently wrap (e.g. a caller passing an out-of-range physical
// value would otherwise alias onto a wildly different, wrong-looking pose
// rather than an obviously-clamped one).
inline int32_t clamp_i24(double value) {
    if (value > static_cast<double>(I24_MAX)) return I24_MAX;
    if (value < static_cast<double>(I24_MIN)) return I24_MIN;
    return static_cast<int32_t>(value);
}

inline void encode_i24_be(int32_t value, uint8_t out[3]) {
    uint32_t raw = static_cast<uint32_t>(value);
    out[0] = static_cast<uint8_t>((raw >> 16) & 0xFF);
    out[1] = static_cast<uint8_t>((raw >> 8) & 0xFF);
    out[2] = static_cast<uint8_t>(raw & 0xFF);
}

inline uint16_t decode_u16_be(const uint8_t b[2]) {
    return static_cast<uint16_t>((static_cast<uint16_t>(b[0]) << 8) | b[1]);
}

inline void encode_u16_be(uint16_t value, uint8_t out[2]) {
    out[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[1] = static_cast<uint8_t>(value & 0xFF);
}

inline uint8_t compute_checksum(const FreeDPacket& p) {
    // Sum every byte up to (but excluding) the checksum byte itself.
    const uint8_t* raw = reinterpret_cast<const uint8_t*>(&p);
    uint32_t sum = 0;
    for (size_t i = 0; i < sizeof(FreeDPacket) - 1; ++i) {
        sum += raw[i];
    }
    return static_cast<uint8_t>((0x100 - (sum & 0xFF)) & 0xFF);
}

// Zero-copy cast of a raw byte span into a FreeDPacket view. Caller guarantees
// span.size() == sizeof(FreeDPacket); this performs no allocation and no copy.
inline const FreeDPacket* view_as_packet(std::span<const uint8_t> bytes) {
    if (bytes.size() != sizeof(FreeDPacket)) {
        return nullptr;
    }
    return reinterpret_cast<const FreeDPacket*>(bytes.data());
}

inline KinematicSample decode(const FreeDPacket& p, int64_t rx_ns) {
    KinematicSample s;
    s.camera_id = p.camera_id;
    s.pitch_deg = decode_i24_be(p.pitch) / 32768.0;
    s.yaw_deg   = decode_i24_be(p.yaw)   / 32768.0;
    s.roll_deg  = decode_i24_be(p.roll)  / 32768.0;
    // 1/64 mm units -> meters
    s.pos_x_m = decode_i24_be(p.pos_x) / 64000.0;
    s.pos_y_m = decode_i24_be(p.pos_y) / 64000.0;
    s.pos_z_m = decode_i24_be(p.pos_z) / 64000.0;
    s.zoom  = decode_u16_be(p.zoom);
    s.focus = decode_u16_be(p.focus);
    s.rx_ns = rx_ns;
    return s;
}

inline FreeDPacket encode(uint8_t camera_id, double pitch_deg, double yaw_deg, double roll_deg,
                           double pos_x_m, double pos_y_m, double pos_z_m,
                           uint16_t zoom, uint16_t focus, uint16_t user_def = 0) {
    FreeDPacket p{};
    p.header = FREED_HEADER;
    p.camera_id = camera_id;
    // clamp_i24 saturates rather than wraps: an out-of-range physical value
    // (e.g. a bad upstream sensor reading, or a test deliberately probing
    // the boundary) lands visibly pinned at the encoder's limit instead of
    // aliasing onto an unrelated, equally-plausible-looking pose.
    encode_i24_be(clamp_i24(pitch_deg * 32768.0), p.pitch);
    encode_i24_be(clamp_i24(yaw_deg * 32768.0), p.yaw);
    encode_i24_be(clamp_i24(roll_deg * 32768.0), p.roll);
    encode_i24_be(clamp_i24(pos_x_m * 64000.0), p.pos_x);
    encode_i24_be(clamp_i24(pos_y_m * 64000.0), p.pos_y);
    encode_i24_be(clamp_i24(pos_z_m * 64000.0), p.pos_z);
    encode_u16_be(zoom, p.zoom);
    encode_u16_be(focus, p.focus);
    encode_u16_be(user_def, p.user_def);
    p.checksum = compute_checksum(p);
    return p;
}

} // namespace freed_codec
