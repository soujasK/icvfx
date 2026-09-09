"""Synthetic witness-camera / rendered-frustum-buffer frame generation.

The real Phase 4 diagnostic bundle carries a wide physical stage photo and
the matching Unreal nDisplay render for the LED wall. Neither a real stage
camera nor a real render node is available for this build (the hackathon
scope is explicitly synthetic tracker *and* render data - see
docs/ROADMAP.md), so this module draws simple, clearly-labelled placeholder
images that encode the same signal a real frame pair would: whether a boom
mic/actor is crossing the tracking volume, whether the LED wall perspective
is shearing, and whether the render buffer is frozen.

Swap this module for real frame grabs (RTSP/NDI capture + an nDisplay
render-target dump) without touching arbiter.py - it only depends on
`generate_incident_frames()` returning two file paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont


@dataclass
class FramePair:
    witness_camera_path: str
    frustum_buffer_path: str


def _base_stage_scene(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    # LED wall backdrop
    draw.rectangle([0, 0, w, int(h * 0.6)], fill=(20, 24, 40))
    # Stage floor
    draw.rectangle([0, int(h * 0.6), w, h], fill=(35, 32, 30))
    # A simple "virtual environment" horizon line rendered on the LED wall
    draw.line([(0, int(h * 0.4)), (w, int(h * 0.4))], fill=(80, 120, 160), width=3)
    # Talent silhouette
    draw.ellipse([w * 0.45, h * 0.35, w * 0.55, h * 0.5], fill=(200, 180, 160))
    draw.rectangle([w * 0.46, h * 0.5, w * 0.54, h * 0.75], fill=(60, 60, 70))


def _label(draw: ImageDraw.ImageDraw, text: str, xy=(10, 10)) -> None:
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.rectangle([xy[0] - 4, xy[1] - 2, xy[0] + 8 * len(text), xy[1] + 14], fill=(0, 0, 0))
    draw.text(xy, text, fill=(255, 255, 0), font=font)


def generate_incident_frames(scenario: str, out_dir: str) -> FramePair:
    os.makedirs(out_dir, exist_ok=True)
    w, h = 480, 270

    witness = Image.new("RGB", (w, h), (10, 10, 10))
    wd = ImageDraw.Draw(witness)
    _base_stage_scene(wd, w, h)

    frustum = Image.new("RGB", (w, h), (10, 10, 10))
    fd = ImageDraw.Draw(frustum)
    _base_stage_scene(fd, w, h)

    if scenario == "occlusion":
        # Boom pole crossing the tracking-camera line of sight, plus the
        # LED wall perspective visibly shearing against the talent.
        wd.line([(w * 0.1, h * 0.05), (w * 0.75, h * 0.3)], fill=(120, 90, 60), width=8)
        _label(wd, "WITNESS CAM: boom pole crossing markers")
        fd.line([(0, int(h * 0.4)), (w, int(h * 0.55))], fill=(80, 120, 160), width=3)  # sheared horizon
        _label(fd, "RENDER: frustum shear vs. physical talent")

    elif scenario == "ptp_jitter":
        # Horizontal phase tearing on the wall while tracking stays smooth.
        _label(wd, "WITNESS CAM: camera move smooth")
        for y in range(int(h * 0.1), int(h * 0.55), 14):
            offset = 18 if (y // 14) % 2 == 0 else -18
            fd.line([(0, y), (w, y)], fill=(60, 90, 130), width=2)
            fd.rectangle([w * 0.3 + offset, y - 5, w * 0.7 + offset, y + 5], outline=(200, 40, 40), width=1)
        _label(fd, "RENDER: horizontal phase tearing")

    elif scenario == "dropped_frame":
        # Smooth camera movement, frozen (stale) render buffer.
        _label(wd, "WITNESS CAM: camera move smooth")
        fd.rectangle([0, 0, w, h], fill=(45, 45, 45))
        _base_stage_scene(fd, w, h)
        _label(fd, "RENDER: frame N-6 (stale/frozen)")

    else:
        _label(wd, "WITNESS CAM: nominal")
        _label(fd, "RENDER: nominal")

    witness_path = os.path.join(out_dir, f"witness_{scenario}.png")
    frustum_path = os.path.join(out_dir, f"frustum_{scenario}.png")
    witness.save(witness_path)
    frustum.save(frustum_path)
    return FramePair(witness_path, frustum_path)
