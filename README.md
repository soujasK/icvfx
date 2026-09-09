# 🎬 Autonomous ICVFX Telemetry & Synchronization Engine
### *Agentic Cinema: Autonomous Multimodal Incident Arbiter, Real-Time Stage Mesh & Closed-Loop Remediation*

[![Live Demo](https://img.shields.io/badge/Google_Cloud_Run-Live_Mission_Control-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white)](https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app)
[![Grafana Cloud](https://img.shields.io/badge/Grafana_Cloud-Telemetry_Gateway-F46800?style=for-the-badge&logo=grafana&logoColor=white)](https://nimblespruce925.grafana.net)
[![Vertex AI](https://img.shields.io/badge/Vertex_AI-Gemini_2.5_Flash-34A853?style=for-the-badge&logo=google&logoColor=white)](https://cloud.google.com/vertex-ai)
[![Google Antigravity](https://img.shields.io/badge/Engineered_With-Google_Antigravity-7B1FA2?style=for-the-badge&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)

An enterprise-grade autonomous incident detection, root-cause arbitration, and self-healing engine for virtual production (**In-Camera Visual Effects / ICVFX**) LED volume stages (*The Mandalorian*, *The Batman*).

Developed for the **Google Cloud Agentic Cinema Blockbuster Hackathon**, incorporating **Gemini on Google Cloud Vertex AI**, **Grafana Cloud Hosted Mimir**, and orchestrated using **Google Antigravity**.

---

## 🌐 Live Production Deployments

- **Mission Control Web App**: [https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app](https://icvfx-sync-engine-m6dtdp53hq-uc.a.run.app)
  - *Serverless Google Cloud Run: Auto-scales down to 0 instances when idle (₹0.00 / hour standby compute cost).*
- **Grafana Cloud Stack**: `nimblespruce925` ([https://nimblespruce925.grafana.net](https://nimblespruce925.grafana.net))
- **Open-Source GitHub Repository**: [https://github.com/soujasK/icvfx.git](https://github.com/soujasK/icvfx.git)
- **Demo Video Audio & Subtitles**: Included in [`docs/demo_voiceover.mp3`](docs/demo_voiceover.mp3) and [`docs/demo_subtitles.srt`](docs/demo_subtitles.srt).

---

## 💡 The Problem: The $50,000/Hour ICVFX Reliability Dilemma

On modern Hollywood virtual production soundstages, physical camera tracking rigs (Mo-Sys, OptiTrack, Stype) and LED wall background render nodes (Unreal Engine 5.5 nDisplay clusters) must maintain synchronization at **120Hz with sub-millisecond tolerances**:

1. **Optical Marker Occlusion**: When boom mics, actors, or camera cranes cross tracking sensor lines of sight, tracking judders violently, shearing the perspective frustum on the LED wall.
2. **PTP Clock Drift**: Precision Time Protocol (IEEE 1588) drift between network switches causes horizontal phase tearing and display genlock decoupling.
3. **Render Node Stalls**: Stalled GPU render buffers produce perspective lag relative to the physical camera move.

Traditionally, when tracking desync occurs, soundstage shoots halt while engineers manually inspect raw network logs—costing studios upwards of **$50,000 per hour in downtime**.

---

## 🧠 Core Technologies & Architectural Roles

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

### 1. 🤖 Google Gemini & Vertex AI: The Multimodal Diagnostic Brain
- **Cross-Modal Reasoning**: Correlates three disparate sensory streams simultaneously:
  1. *Physical witness camera feed* (video `.mp4` or high-resolution snapshot `.png`).
  2. *Rendered frustum buffer* sent to the LED wall.
  3. *500ms sliding-window telemetry manifest* (jerk counts, PTP offset, packet arrival jitter).
- **Incident Classification**: Distinguishes between physical obstructions (`PHYSICAL_MARKER_OCCLUSION`), digital timing faults (`PTP_CLOCK_JITTER`), and hardware render stalls (`RENDER_NODE_DROPPED_FRAME`).
- **Dynamic Confidence Calibration**: Automatically scores diagnostic certainty based on real-time signal-to-noise ratios ($73\% \to 86\% \to 97\%$).
- **Model Context Protocol (MCP)**: Employs standardized MCP tool calling to trigger hardware remediation without human intervention.

### 2. 📊 Grafana Cloud: Broadcast-Grade Telemetry & Closed-Loop Verification
- **High-Frequency Ingestion**: Utilizes native **Prometheus Remote-Write 1.0 Protobuf** with **Snappy block compression** (`cramjam`) pushing 120Hz metrics batched every 3.0s directly to **Grafana Cloud Hosted Mimir** (`prometheus-prod-43-prod-ap-south-1.grafana.net`).
- **Live 5-Panel Stage Mission Control Dashboard**:
  1. *FreeD Packet Jitter (P99)* vs. 1.0ms broadcast SLA target.
  2. *PTP Grandmaster Clock Offset* (ns) with $\pm 500\text{ns}$ alert boundaries.
  3. *Kinematic Jerk Violations* tracking cumulative sensor occlusion breaches.
  4. *Active Stage Sync Alert Status* (Stat widget tripping to red `DESYNC ALERT` on $> 2.5\text{ms}$ jitter).
  5. *6-DoF Extended Kalman Filter Covariance Trace* $\Vert P \Vert$ gauge ($0.0130$ nominal).
- **Closed-Loop AI Verification**: When Gemini prescribes a fix, the engine polls Prometheus metrics to mathematically verify that packet jitter dropped back below the $1.0\text{ms}$ SLA threshold before returning stage control.

### 3. 🚀 Google Antigravity: Advanced Agentic System Engineering & Orchestration
This system was conceptualized, architected, and continuously verified utilizing **Google Antigravity**:
- **Dual-Plane Agentic Architecture**: Engineered the separation of the *Fast Data Plane* ($< 10\text{ms}$ C++20 / EKF kinematic path) from the *Asynchronous Control Plane* (Gemini + MCP + Grafana Cloud).
- **Autonomous Stress & Edge-Case Verification**: Generated comprehensive fault-injection testing harnesses spanning 60 automated unit, load, and regression tests (including a 100,000-packet burst load test at 0% loss).
- **Serverless Cloud Run Pipeline**: Orchestrated containerization, environment variable credential injection, and deployment to Google Cloud Run with scale-to-zero capabilities.

---

## ⚡ Quickstart: Step-by-Step Running Guide

### Prerequisites
- **Python 3.10+**
- **Node.js 18+** & **npm**
- **FFmpeg** (installed and present in your system PATH)
- *(Optional)* Google Cloud SDK (`gcloud`) & Docker

---

### Step 1: Clone & Configure Credentials

```bash
git clone https://github.com/soujasK/icvfx.git
cd icvfx

# Install Python dependencies
pip install -r requirements.txt
pip install -r incident-arbiter/requirements.txt
```

Create or verify `.env` in the project root:
```ini
# Google Cloud & Vertex AI Configuration
GEMINI_BACKEND=vertex
GOOGLE_CLOUD_PROJECT=project-b97ea65d-c159-4b52-98d
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash

# Grafana Cloud Hosted Prometheus (Mimir) Telemetry Gateway
GRAFANA_CLOUD_REMOTE_WRITE_URL=https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom/push
GRAFANA_CLOUD_USER=3572064
GRAFANA_CLOUD_API_KEY=your_grafana_cloud_api_token
```

---

### Step 2: Run the Application Locally

#### Option A: Production Serverless Engine (FastAPI + Built Dashboard on Port 8080)
```bash
# 1. Build the React frontend
cd dashboard
npm install
npm run build
cd ..

# 2. Start unified serverless application
python serverless_app.py
```
Open **`http://localhost:8080`** in your browser.

#### Option B: Hot-Reloading Vite Development Server (Port 5173)
```bash
cd dashboard
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

---

### Step 3: Run Edge 120Hz UDP Ingestion & Crane Tracker

Ingests real 120Hz FreeD tracking packets from camera tracking hardware (or built-in crane simulator) and relays live pose coordinates to Mission Control:

```bash
python scripts/edge_telemetry_relay.py --simulate
```
- Listens on `UDP 0.0.0.0:5005` (FreeD D1 protocol).
- Computes real-time 6-DoF Extended Kalman Filter (EKF) state estimation.
- Relays pose coordinates to Mission Control HUD.
- Automatically pushes Prometheus telemetry batches to Grafana Cloud every 3 seconds.

---

### Step 4: Stream Real-Time Telemetry to Grafana Cloud

Push real-time stage metrics (Jitter, PTP offset, Jerk breaches, EKF covariance) to Grafana Cloud Hosted Mimir:

```bash
# Continuous background streaming loop (every 3 seconds)
python scripts/push_to_grafana_cloud.py --daemon --interval 3.0

# Check daemon status
python scripts/push_to_grafana_cloud.py --status

# Stop daemon
python scripts/push_to_grafana_cloud.py --stop
```

#### Viewing the Dashboard on Grafana Cloud:
1. Log in to [https://nimblespruce925.grafana.net](https://nimblespruce925.grafana.net).
2. Go to **Dashboards** > **New** > **Import**.
3. Import [`observability/dashboards/grafana_cloud_dashboard.json`](observability/dashboards/grafana_cloud_dashboard.json).
4. Set the time range to **`Last 15 minutes`** and auto-refresh to **`5s`**. All 5 panels will illuminate with live data!

---

### Step 5: Test Autonomous Video & Snapshot Ingestion

Ingest a stage witness video feed or snapshot, run multimodal arbitration with Gemini 2.5 Flash on Vertex AI, and render a compensated side-by-side output video:

```bash
# Video Ingest Mode
python orchestrator/video_remediator.py \
  --input_video dashboard/public/videos/stage_witness_boom_occlusion.mp4 \
  --output_video dashboard/public/videos/processed/demo_remediated.mp4 \
  --scenario occlusion \
  --camera 1 \
  --anomalies 42

# Snapshot Ingest Mode
python orchestrator/run_custom_action.py \
  --action diagnose \
  --scenario occlusion \
  --camera 1 \
  --anomalies 42
```

---

### Step 6: 1-Command Google Cloud Run Deployment

Deploy the entire serverless application to Google Cloud Run:

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File deploy/deploy_to_cloud_run.ps1
```

**Linux / macOS (Bash):**
```bash
chmod +x deploy/deploy_to_cloud_run.sh
./deploy/deploy_to_cloud_run.sh
```

---

## 🧪 Automated Testing & Validation (60 Test Cases)

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

## 📊 Telemetry Metrics Reference

| Metric Name | Type | Description | Alert SLA Threshold |
|---|---|---|---|
| `freed_packet_jitter_seconds` | Gauge | P99 FreeD UDP packet arrival jitter in seconds | $> 1.0\text{ms}$ (Warning), $> 2.5\text{ms}$ (Critical Alert) |
| `freed_ptp_offset_nanoseconds` | Gauge | Hardware PTP grandmaster clock drift | $> \pm 500\text{ns}$ |
| `freed_kinematic_jerk_violations_total` | Counter | Cumulative impossible kinematic acceleration breaches | $> 10\text{ breaches}$ (Marker Occlusion) |
| `freed_ekf_covariance_trace` | Gauge | 6-DoF Extended Kalman Filter state covariance $\Vert P \Vert$ | $> 0.05$ (Degraded), $> 0.15$ (Tracking Lost) |
| `freed_packets_total` | Counter | Total 120Hz datagrams ingested | Ingest loss rate monitoring |

---

## ⚖️ License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
