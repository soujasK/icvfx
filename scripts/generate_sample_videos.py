import os
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard", "public", "videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

WIDTH, HEIGHT = 640, 360
FPS = 30
DURATION_SEC = 5
TOTAL_FRAMES = FPS * DURATION_SEC

def create_video(filename, scenario_type):
    filepath = os.path.join(VIDEOS_DIR, filename)
    print(f"Generating {filepath} ({scenario_type})...")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        filepath
    ]
    
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    for f in range(TOTAL_FRAMES):
        t = f / FPS
        img = Image.new("RGB", (WIDTH, HEIGHT), color=(12, 14, 20))
        draw = ImageDraw.Draw(img)
        
        # Draw Studio Grid
        grid_color = (25, 30, 42)
        for x in range(0, WIDTH, 40):
            draw.line([(x, 0), (x, HEIGHT)], fill=grid_color, width=1)
        for y in range(0, HEIGHT, 40):
            draw.line([(0, y), (y, WIDTH)], fill=grid_color, width=1)
            
        # Draw LED Wall Arc (semi-circle at top)
        arc_bbox = [80, -100, WIDTH - 80, 180]
        draw.arc(arc_bbox, start=20, end=160, fill=(0, 240, 255), width=3)
        draw.text((WIDTH // 2 - 50, 25), "LED VOLUME WALL A", fill=(0, 240, 255))
        
        # Draw Tracking Ceiling Target Dots (matrix of small crosses)
        dot_color = (60, 80, 110)
        for row in range(4):
            for col in range(8):
                cx = 80 + col * 68
                cy = 70 + row * 45
                draw.ellipse([cx-2, cy-2, cx+2, cy+2], fill=dot_color)
                
        # Camera Rig Path (Dolly moves across screen)
        # Smooth sine motion
        cam_x = int(160 + (WIDTH - 320) * (0.5 + 0.45 * math.sin(t * 1.2)))
        cam_y = int(220 + 25 * math.cos(t * 1.5))
        
        # Optical Frustum Cone (lines from ceiling down to camera)
        frustum_color = (40, 120, 160)
        draw.line([(cam_x - 30, 0), (cam_x, cam_y)], fill=frustum_color, width=1)
        draw.line([(cam_x + 30, 0), (cam_x, cam_y)], fill=frustum_color, width=1)
        
        # Draw Camera Rig
        draw.rectangle([cam_x - 24, cam_y - 16, cam_x + 24, cam_y + 16], fill=(30, 35, 50), outline=(0, 255, 136), width=2)
        draw.text((cam_x - 18, cam_y - 7), "RIG #1", fill=(0, 255, 136))
        
        # 4 Optical Retroreflective Tracking Spheres on the Rig
        spheres = [
            (cam_x - 18, cam_y - 12),
            (cam_x + 18, cam_y - 12),
            (cam_x - 18, cam_y + 12),
            (cam_x + 18, cam_y + 12),
        ]
        for sx, sy in spheres:
            draw.ellipse([sx-3, sy-3, sx+3, sy+3], fill=(220, 255, 255), outline=(0, 240, 255))
            
        # SCENARIO SPECIFIC ANIMATIONS
        if scenario_type == "occlusion":
            # Boom mic drops in from right ceiling between t=1.5s and t=4.5s
            if 1.2 < t < 4.8:
                # Boom pole extending into the optical line of sight
                progress = min(1.0, (t - 1.2) / 0.8) if t < 3.5 else max(0.0, (4.8 - t) / 0.8)
                boom_tip_x = int(WIDTH - (WIDTH - cam_x) * progress * 0.95)
                boom_tip_y = int(40 + (cam_y - 40) * progress * 0.95)
                
                # Draw carbon fiber pole
                draw.line([(WIDTH + 20, 20), (boom_tip_x, boom_tip_y)], fill=(120, 120, 120), width=6)
                
                # Draw boom microphone foam blimp (zeppelin windscreen)
                draw.ellipse([boom_tip_x - 22, boom_tip_y - 10, boom_tip_x + 22, boom_tip_y + 10], fill=(45, 45, 55), outline=(255, 51, 102), width=2)
                
                # Red alert occlusion zone over tracking markers
                if progress > 0.6:
                    draw.text((boom_tip_x - 65, boom_tip_y + 16), "OCCLUSION DETECTED", fill=(255, 51, 102))
                    draw.rectangle([cam_x - 26, cam_y - 18, cam_x + 26, cam_y + 18], outline=(255, 51, 102), width=3)
        elif scenario_type == "ptp_jitter":
            # Glitch / jitter offset simulation
            if 1.5 < t < 4.0:
                jitter_offset = int(math.sin(t * 40) * 12)
                draw.text((WIDTH // 2 - 90, HEIGHT - 50), f"PTP PACKET JITTER: {jitter_offset}ms", fill=(255, 170, 0))
                # Shift rig slightly
                draw.rectangle([cam_x - 24 + jitter_offset, cam_y - 16, cam_x + 24 + jitter_offset, cam_y + 16], outline=(255, 170, 0), width=2)
        elif scenario_type == "dropped_frame":
            if 2.0 < t < 4.0:
                # Wall flash frozen
                draw.text((WIDTH // 2 - 80, 50), "GPU PIPELINE STALL (0 FPS)", fill=(255, 51, 102))
                draw.arc(arc_bbox, start=20, end=160, fill=(255, 51, 102), width=4)

        # Header Info HUD
        draw.rectangle([0, 0, WIDTH, 24], fill=(8, 10, 15))
        draw.text((10, 5), "WITNESS CAM 04 [OVERHEAD CEILING RIG]", fill=(180, 190, 210))
        
        # SMPTE Timecode
        smpte_frame = int(f % FPS)
        smpte_sec = int(t % 60)
        smpte_min = int((t // 60) % 60)
        timecode = f"TC 01:{smpte_min:02d}:{smpte_sec:02d}:{smpte_frame:02d} @ {FPS}fps"
        draw.text((WIDTH - 210, 5), timecode, fill=(0, 240, 255))
        
        # Footer
        draw.rectangle([0, HEIGHT - 20, WIDTH, HEIGHT], fill=(8, 10, 15))
        status_text = "STAGE STATUS: NOMINAL" if scenario_type == "nominal" or (scenario_type == "occlusion" and (t <= 1.2 or t >= 4.8)) else f"ANOMALY IN PROGRESS ({scenario_type.upper()})"
        draw.text((10, HEIGHT - 16), status_text, fill=(0, 255, 136) if "NOMINAL" in status_text else (255, 51, 102))

        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    proc.wait()
    print(f"Done: {filepath}")

if __name__ == "__main__":
    create_video("stage_witness_boom_occlusion.mp4", "occlusion")
    create_video("stage_witness_nominal_tracking.mp4", "nominal")
    create_video("stage_witness_ptp_jitter.mp4", "ptp_jitter")
    print("All sample videos generated successfully.")
