# Autonomous ICVFX Telemetry & Synchronization Engine

An implementation of the attached plan for detecting and auto-remediating
tracker-to-render desync on virtual production (ICVFX) LED volume stages:
FreeD tracking telemetry -> kinematic/PTP invariant checks -> a multimodal
incident arbiter -> deterministic remediation, end to end.

**Read `docs/ROADMAP.md` first.** It maps every piece below to the plan's
five sprints and states plainly what was actually built-and-run in this
environment versus what's real, complete source that needs infrastructure
(a Kafka broker, a Grafana Cloud tenant, Google Cloud credentials) this
sandbox doesn't have. Short version: the C++ ingest/kinematic core, the
mock incident arbiter, the MCP remediation server, and the full
fault-injection test harness all actually run and are verified below. The
Kafka/Spring Boot mesh and the Grafana Cloud config are real, complete
source that isn't executable here. The real Gemini 2.5 Pro path is wired
but untested (no Vertex AI credentials in this sandbox).

## Architecture

```
FreeD UDP (120Hz)                Kafka topics                 Grafana Cloud
      |                                |                             |
      v                                v                             v
cpp-core/           ---->    telemetry-mesh/          ---->   observability/
kinematic_engine            (Spring Boot + Kafka             (Mimir dashboards +
(zero-copy parse,            Streams; 500ms sliding           alert rules; fires
 jerk/accel + PTP             window P95/P99 jitter,          a webhook on jitter
 jitter checks)               Prometheus export)              > 2.5ms / 3 frames)
                                                                       |
                                                                       v
                                                          incident-arbiter/
                                                    (Gemini 2.5 Pro multimodal
                                                     root-cause classification,
                                                     or MockArbiter offline)
                                                                       |
                                                                       v
                                                          mcp-remediation/
                                                     (real MCP server: switches
                                                      Kalman filter profile /
                                                      recalibrates PTP / expands
                                                      frustum overscan)
```

`orchestrator/run_fault_injection_test.py` drives the whole left-to-right
path for three fault scenarios and checks the plan's own latency targets.

## Repo layout

| Path | Sprint | What it is |
|---|---|---|
| `cpp-core/` | 1 | C++20 UDP packet generator + zero-copy kinematic/PTP ingest daemon |
| `telemetry-mesh/` | 2 | Spring Boot 3.x + Kafka Streams event mesh (source only here) |
| `observability/` | 3 | Grafana Cloud dashboard/alerting/tracing config-as-code |
| `incident-arbiter/` | 4 | Gemini 2.5 Pro (Vertex AI) arbiter + offline rule-based mock |
| `mcp-remediation/` | 5 | Real MCP server executing remediation tool calls |
| `orchestrator/` | 5 | End-to-end fault-injection test harness + MCP client |
| `dashboard/` | - | Stage-crew incident-summary UI, complements Grafana (doesn't replace it) — see `dashboard/README.md` |
| `tests/` | - | Edge-case and stress-test suite (60 test cases) - see `docs/TEST_REPORT.md` |
| `docs/ROADMAP.md` | - | Honest status of every milestone in the original plan |
| `docs/TEST_REPORT.md` | - | Every bug stress/edge-case testing found, with before/after evidence |
| `runs/` | - | Output of the last test run (JSONL telemetry, PNGs, incident reports) |

## Testing

```bash
pip install -r incident-arbiter/requirements.txt -r mcp-remediation/requirements.txt
./tests/run_all_tests.sh
```

Builds the C++ core and runs all 6 suites (C++ codec unit tests, ingest
daemon edge cases, throughput/load stress tests, arbiter edge cases, MCP
server edge cases, and the full end-to-end orchestrator run) - 60 test
cases total. Read `docs/TEST_REPORT.md` for what each suite found: it
documents 12 real bugs (a multi-camera data-isolation bug, a checksum
validation gap, a silent integer-overflow bug, a receive-path throughput
bottleneck that lost 50% of a 100k-packet burst, an MCP server race
condition that silently dropped audit-log entries under concurrent calls,
and more) with before/after numbers for each, not just a pass/fail summary.

## Running it

### 1. C++ core (Sprint 1) - builds and runs standalone

```bash
cd cpp-core
./build.sh
mkdir -p /tmp/demo && ./bin/kinematic_engine --out-dir /tmp/demo &
./bin/packet_generator --scenario occlusion --duration 3
# check /tmp/demo/stage.kinematic.anomalies.jsonl
```

Scenarios: `normal`, `occlusion`, `ptp_jitter`.

### 2. Full end-to-end fault-injection test (Sprint 5)

Runs all three scenarios through the real C++ core, the arbiter, and a live
MCP session, and checks the <3s recovery / <100ms remediation targets.

```bash
pip install -r incident-arbiter/requirements.txt -r mcp-remediation/requirements.txt
cd orchestrator
python3 run_fault_injection_test.py
```

By default it uses `MockArbiter` (no cloud credentials needed). To use real
Gemini 2.5 Pro instead, set `GOOGLE_CLOUD_PROJECT` (and optionally
`GOOGLE_CLOUD_LOCATION`) and have Application Default Credentials configured
- `build_arbiter()` picks it up automatically. Force the mock explicitly
with `ICVFX_FORCE_MOCK_ARBITER=1`.

Output per scenario lands in `runs/<scenario>/incident_report.json`, plus
the raw JSONL telemetry and the synthetic witness/frustum PNGs the arbiter
reasoned over.

### 3. MCP remediation server standalone

Any MCP client can drive it directly:

```bash
python3 mcp-remediation/server.py   # stdio transport
```

State (which filter mode each camera is on, current overscan, last HUD
message, full action log) persists to `mcp-remediation/stage_state.json`.

### 4. Telemetry mesh & Grafana Cloud (Sprints 2-3) - needs real infra

These are complete source/config, not runnable in the sandbox that built
this repo (no Maven Central egress, no Kafka broker, no Grafana Cloud
tenant). To actually stand them up:

```bash
docker compose up -d          # local Kafka + Grafana/Tempo/Loki (untested here)
cd telemetry-mesh && mvn spring-boot:run
```

Then point `observability/grafana-agent.river` and
`observability/otel-collector-config.yaml` at a real Grafana Cloud stack
(fill in the `GRAFANA_CLOUD_*` env vars) and import
`observability/dashboards/icvfx_stage_dashboard.json` +
`observability/alerting/jitter_alert_rules.yaml`.

## Last verified test run

3/3 scenarios classified correctly (occlusion -> `PHYSICAL_MARKER_OCCLUSION`,
ptp_jitter -> `PTP_CLOCK_JITTER`, dropped_frame -> `RENDER_NODE_DROPPED_FRAME`),
all recovered well under the 3-second target, all MCP remediation calls
well under the 100ms target. The full stress/edge-case suite (60 test
cases across 6 suites, including a 100,000-packet burst load test at 0%
loss and an MCP-server concurrency race-condition regression test) also
passes cleanly. Full numbers in `runs/*/incident_report.json`,
`docs/ROADMAP.md`, and `docs/TEST_REPORT.md`.
