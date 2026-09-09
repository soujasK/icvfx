import urllib.request
import json

url = "https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app/api/process-video"
payload = {
    "scenario": "occlusion",
    "camera": 1,
    "anomalies": 35,
    "jitter": 0.18,
    "render_frozen": False,
    "summary": "Director note test",
    "video_path": "dashboard/public/videos/stage_witness_boom_occlusion.mp4"
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("Status:", resp.status)
        data = json.loads(resp.read().decode("utf-8"))
        print("Full Data:", json.dumps(data, indent=2))
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.reason)
    print("Error Body:", e.read().decode("utf-8"))
except Exception as e:
    print("General Exception:", e)
