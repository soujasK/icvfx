# 🎬 Autonomous ICVFX Telemetry & Synchronization Engine
### *Agentic Cinema: Autonomous Multimodal Incident Arbiter & Real-Time Stage Mesh*

[![Live Demo](https://img.shields.io/badge/Google_Cloud_Run-Live_Mission_Control-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app)
[![Grafana Cloud](https://img.shields.io/badge/Grafana_Cloud-Telemetry_Gateway-F46800?style=for-the-badge&logo=grafana&logoColor=white)](https://nimblespruce925.grafana.net)
[![Vertex AI](https://img.shields.io/badge/Vertex_AI-Gemini_2.5_Flash-34A853?style=for-the-badge&logo=google&logoColor=white)](https://cloud.google.com/vertex-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

An end-to-end, enterprise-grade autonomous incident detection and remediation system for virtual production (**In-Camera Visual Effects / ICVFX**) LED volume stages. 

Built for the **Google Cloud Agentic Cinema Hackathon** (incorporating **Gemini Enterprise on Vertex AI** and the **Grafana Labs Track**).

---

## 🌐 Live Production Deployment

- **Mission Control Web App**: [https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app](https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app)
  - *Serverless Google Cloud Run: Auto-scales down to 0 instances when idle (₹0.00 / hour standby compute cost).*
- **Grafana Cloud Stack**: `nimblespruce925` ([https://nimblespruce925.grafana.net](https://nimblespruce925.grafana.net))
- **Open-Source GitHub Repo**: [https://github.com/soujasK/icvfx.git](https://github.com/soujasK/icvfx.git)

---

## 🏛️ System Architecture

```
                                  +-------------------------------------------------------+
                                  |              STAGE MISSION CONTROL HUD                |
                                  |       (React 18 + Vite / Google Cloud Run)            |
                                  +---------------------------+---------------------------+
                                                              |
                                               HTTPS / WebSockets / Telemetry Push
                                                              |
+--------------------------+    120Hz FreeD UDP    +----------v------------+    Prometheus    +-------------------------+
| Physical Stage Tracking  |---------------------->| Local Edge Relay      |   Remote Write   | Grafana Cloud (Mimir)   |
| (Mo-Sys / OptiTrack rig) |   UDP 0.0.0.0:5005    | (6-DoF Kalman Filter) |----------------->| 5 Real-Time Dashboards  |
+--------------------------+                       +----------+------------+   (Snappy + PB)  +-------------------------+
                                                              |
                                                    Multimodal Ingest (.mp4 / .png)
                                                              |
                                                   +----------v------------+
                                                   | Vertex AI Gemini 2.5  |
                                                   | Incident Arbiter      |
                                                   +----------+------------+
                                                              |
                                                    Prescribed Tool Call
                                                              |
                                                   +----------v------------+
                                                   | MCP Remediation       |
                                                   | (Closed-Loop Recover) |
                                                   +-----------------------+
```

---

## 🚀 Quickstart: Running the Project

### Prerequisites
- **Python 3.10+** (with pip)
- **Node.js 18+** & **npm**
- **FFmpeg** (installed and in system PATH for video transcoding)
- *(Optional)* Google Cloud CLI (`gcloud`) & Docker for Cloud Run deployment

---

### Step 1: Clone & Configure Environment

```bash
git clone https://github.com/soujasK/icvfx.git
cd icvfx

# Install Python dependencies
pip install -r requirements.txt
pip install -r incident-arbiter/requirements.txt
```

Create or verify your `.env` file in the repository root:
```ini
# Google Cloud & Vertex AI Configuration
GEMINI_BACKEND=vertex
GOOGLE_CLOUD_PROJECT=project-b97ea65d-c159-4b52-98d
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash

# Grafana Cloud Hosted Prometheus (Mimir) Telemetry Gateway
GRAFANA_CLOUD_REMOTE_WRITE_URL=https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom/push
GRAFANA_CLOUD_USER=3572064
GRAFANA_CLOUD_API_KEY=your_grafana_cloud_token_here
```

---

### Step 2: Run the Application Locally

You can run the full system using either the **FastAPI Serverless App** or the **Vite Development Server**:

#### Option A: Run Full Production App (FastAPI + Built Frontend)
```bash
# 1. Build the React frontend
cd dashboard
npm install
npm run build
cd ..

# 2. Start the unified serverless engine (serves API & Dashboard on port 8080)
python serverless_app.py
```
Open **`http://localhost:8080`** in your browser.

#### Option B: Run Hot-Reloading Vite Dev Server
```bash
cd dashboard
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

### Step 3: Run Edge 120Hz UDP Ingestion & EKF Tracker

To ingest real 120Hz FreeD tracking packets from local camera rigs (or use the built-in crane simulator) and relay live pose coordinates to Mission Control:

```bash
python scripts/edge_telemetry_relay.py --simulate
```
- Listens on `UDP 0.0.0.0:5005` (FreeD D1 protocol).
- Computes real-time 6-DoF Extended Kalman Filter (EKF) dead-reckoning.
- Streams live telemetry to the Cloud Run Mission Control HUD.
- Periodically ships Prometheus metrics directly to Grafana Cloud.

---

### Step 4: Stream Live Telemetry to Grafana Cloud

To push real-time stage health metrics (Jitter, PTP offsets, kinematic jerk breaches, and EKF state covariance) to Grafana Cloud Hosted Mimir:

```bash
# One-time test push
python scripts/push_to_grafana_cloud.py

# Continuous background streaming daemon (every 3 seconds)
python scripts/push_to_grafana_cloud.py --daemon --interval 3.0

# Check daemon status
python scripts/push_to_grafana_cloud.py --status

# Stop daemon
python scripts/push_to_grafana_cloud.py --stop
```

#### Viewing the Live Grafana Dashboard:
1. Log in to your Grafana Cloud stack (e.g., [https://nimblespruce925.grafana.net](https://nimblespruce925.grafana.net)).
2. Go to **Dashboards** > **Import**.
3. Import [`observability/dashboards/grafana_cloud_dashboard.json`](observability/dashboards/grafana_cloud_dashboard.json).
4. Set the time picker to **`Last 15 minutes`** and auto-refresh to **`5s`**. All 5 panels will display real-time live telemetry!

---

### Step 5: Test Autonomous Video Ingestion & Vertex AI Remediation

To ingest a stage witness video feed, run multimodal arbitration with Gemini 2.5 Flash on Vertex AI, and render a remediated side-by-side video HUD:

```bash
python orchestrator/video_remediator.py \
  --input_video dashboard/public/videos/stage_witness_boom_occlusion.mp4 \
  --output_video dashboard/public/videos/processed/demo_remediated.mp4 \
  --scenario occlusion \
  --camera 1 \
  --anomalies 42
```
Output:
- Remediated video generated with side-by-side compensation and real-time Stage HUD.
- Multimodal diagnosis returned in under 10 seconds via Vertex AI.
- Instant metric push to Grafana Cloud.

---

### Step 6: Deploy to Google Cloud Run (1 Command)

Deploy the entire serverless application to Google Cloud Run with scale-to-zero compute:

**On Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File deploy/deploy_to_cloud_run.ps1
```

**On Linux / macOS (Bash):**
```bash
chmod +x deploy/deploy_to_cloud_run.sh
./deploy/deploy_to_cloud_run.sh
```

---

## 🧪 Automated Test Suite (60 Test Cases)

Run the full end-to-end verification and load testing suite:

```bash
# Run end-to-end fault-injection test (occlusion, ptp_jitter, dropped_frame)
python orchestrator/run_fault_injection_test.py

# Run unit and regression test suite
pytest tests/
```

- **Classification Accuracy**: 100% (3/3 scenarios classified correctly).
- **Incident Recovery Time**: $< 3.0\text{s}$ (meeting strict broadcast SLA).
- **Remediation Tool Execution**: $< 100\text{ms}$ via MCP tool calls.
- **Closed-Loop Verification**: Validated by reading post-remediation jitter telemetry back below the $1.0\text{ms}$ target.

---

## 📊 Telemetry Metrics Exported

| Metric Name | Type | Description | Alert Threshold |
|---|---|---|---|
| `freed_packet_jitter_seconds` | Gauge | P99 FreeD UDP packet arrival jitter | $> 1.0\text{ms}$ (Warning), $> 2.5\text{ms}$ (Critical) |
| `freed_ptp_offset_nanoseconds` | Gauge | Hardware PTP grandmaster clock drift | $> \pm 500\text{ns}$ |
| `freed_kinematic_jerk_violations_total` | Counter | Impossible camera acceleration breaches | $> 10\text{ breaches}$ (Occlusion) |
| `freed_ekf_covariance_trace` | Gauge | 6-DoF Extended Kalman Filter state covariance $\Vert P \Vert$ | $> 0.05$ (Elevated), $> 0.15$ (Lost Tracking) |
| `freed_packets_total` | Counter | Total 120Hz datagrams ingested | Loss rate monitoring |

---

## ⚖️ License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
