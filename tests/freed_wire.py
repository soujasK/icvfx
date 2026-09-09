"""Python-side mirror of cpp-core/include/freed_packet.hpp's wire format,
used only by the test suite to craft exact-bytes valid and deliberately
corrupt FreeD datagrams without going through the C++ generator (which
can't produce a malformed packet on purpose).

Wire layout (29 bytes) - must stay in lockstep with freed_packet.hpp:
  header(1) camera_id(1) pitch(3) yaw(3) roll(3) pos_z(3) pos_x(3) pos_y(3)
  zoom(2) focus(2) user_def(2) reserved(2) checksum(1)
"""

from __future__ import annotations

FREED_HEADER = 0xD1
PACKET_SIZE = 29


def _i24(value_deg_or_m: float, scale: float) -> bytes:
    raw = int(round(value_deg_or_m * scale))
    raw = max(-8_388_608, min(8_388_607, raw))  # mirror the C++ saturating clamp
    return (raw & 0xFFFFFF).to_bytes(3, "big", signed=False)


def _u16(value: int) -> bytes:
    return (value & 0xFFFF).to_bytes(2, "big", signed=False)


def compute_checksum(body_27_bytes: bytes) -> int:
    """body_27_bytes = every field except the checksum byte itself
    (header..reserved, i.e. bytes [0..27])."""
    total = sum(body_27_bytes) & 0xFF
    return (0x100 - total) & 0xFF


def build_packet(
    camera_id: int = 1,
    pitch_deg: float = 0.0,
    yaw_deg: float = 0.0,
    roll_deg: float = 0.0,
    pos_x_m: float = 0.0,
    pos_y_m: float = 0.0,
    pos_z_m: float = 0.0,
    zoom: int = 0,
    focus: int = 0,
    user_def: int = 0,
    *,
    bad_header: bool = False,
    corrupt_checksum: bool = False,
) -> bytes:
    header = bytes([0x00 if bad_header else FREED_HEADER])
    body = (
        header
        + bytes([camera_id & 0xFF])
        + _i24(pitch_deg, 32768.0)
        + _i24(yaw_deg, 32768.0)
        + _i24(roll_deg, 32768.0)
        + _i24(pos_z_m, 64000.0)
        + _i24(pos_x_m, 64000.0)
        + _i24(pos_y_m, 64000.0)
        + _u16(zoom)
        + _u16(focus)
        + _u16(user_def)
        + b"\x00\x00"  # reserved
    )
    assert len(body) == 28, f"expected 28-byte body before checksum, got {len(body)}"
    checksum = compute_checksum(body)
    if corrupt_checksum:
        checksum ^= 0xFF
    packet = body + bytes([checksum])
    assert len(packet) == PACKET_SIZE, f"expected {PACKET_SIZE}-byte packet, got {len(packet)}"
    return packet
