# Roadmap & Milestone Status

This tracks the five sprints from the original implementation plan
(section 8) against what actually exists in this repository. Status legend:

- **BUILT & VERIFIED** - real code, actually compiled/run in this environment with logged output
- **BUILT, UNVERIFIED HERE** - real, complete source; needs infra/credentials this sandbox doesn't have (no Maven Central, no Docker daemon, no Google Cloud egress) to build/run
- **SIMULATED** - a deliberate stand-in for hardware or a live cloud service that doesn't exist in this scope (see the project's own scoping note below)

> Scoping note carried over from the hackathon decision this plan supports:
> the build targets **simulated/synthetic tracker and render data**, not
> real OptiTrack/Mo-Sys/Vicon hardware or a live Unreal nDisplay cluster -
> given hackathon time constraints. Everything below is built against that
> scope, not against real stage hardware.

## Sprint 1: C++20 Core & Synthetic Rig (Weeks 1-2)
**Status: BUILT & VERIFIED, HARDENED**
- `cpp-core/include/freed_packet.hpp` - bitfield-exact FreeD D1 struct + zero-copy codec. Note: the plan's own struct listing sums to 27 bytes, not the stated 29; a documented 2-byte `reserved` field reconciles this. Out-of-range values now saturate instead of silently overflowing (see `docs/TEST_REPORT.md` #4).
- `cpp-core/src/packet_generator.cpp` - synthetic 120Hz FreeD UDP emitter with `normal` / `occlusion` / `ptp_jitter` fault-injection scenarios, a `--camera-id` flag for multi-camera testing, and a `--burst N` unpaced mode for throughput stress testing.
- `cpp-core/src/kinematic_engine.cpp` - a receiver-thread/worker-thread ingest daemon (see `docs/TEST_REPORT.md` #7 for why); jerk/acceleration invariant check (>15 m/s^2, >90 deg yaw flip) and PTP-domain jitter check (2.5ms / 3-consecutive-frame alert), both correctly isolated per camera_id; checksum validation on every inbound packet.
- Verified: `normal` -> 0 anomalies/0 alerts, `occlusion` -> 31 anomalies/0 alerts, `ptp_jitter` -> 0 anomalies/1 alert event, across a 360-frame (3s @ 120Hz) run each. Load-tested to 100,000 packets/burst at 0% loss and a sustained 5000Hz stream at 100% delivery - see `docs/TEST_REPORT.md` for the full load-testing results this sprint's plan called for.
- Not built: real OpenTelemetry C++ SDK linkage (network-fetched dependency, unavailable here) - replaced with hand-rolled W3C `traceparent` generation that's schema-compatible with a real OTel exporter; see `cpp-core/src/common.hpp` docstring.

## Sprint 2: Kafka & Telemetry Mesh (Weeks 3-4)
**Status: BUILT, UNVERIFIED HERE**
- `telemetry-mesh/` - complete Spring Boot 3.x + Kafka Streams source: topic topology (`KafkaTopicConfig`), 500ms sliding-window P95/P99 jitter aggregation (`JitterAggregationTopology`), Micrometer/Prometheus metric export matching the exact names Sprint 3's dashboards read (`StageMetricsExporter`).
- Not run: needs Maven Central (unreachable from this sandbox's allow-listed network) and a live Kafka broker. `docker-compose.yml` provides one; untested here for the same reason.
- Load testing at 10,000 pkts/sec (as specified) was performed against the Sprint 1 C++ ingest path directly over UDP (see `docs/TEST_REPORT.md`) rather than through this Kafka layer, since the latter can't run in this sandbox.

## Sprint 3: Grafana Cloud Fabric (Weeks 5-6)
**Status: SIMULATED (config-as-code, not deployed)**
- `observability/dashboards/icvfx_stage_dashboard.json` - Mimir dashboard JSON model for the three named metrics.
- `observability/alerting/jitter_alert_rules.yaml` - Grafana unified alerting rule (2.5ms / 3-frame threshold) wired to a webhook contact point.
- `observability/otel-collector-config.yaml`, `observability/grafana-agent.river` - trace/log pipeline and Prometheus remote-write config.
- None of this is deployed to an actual Grafana Cloud tenant; no such tenant/credentials exist in this build.

## Sprint 4: Gemini Arbiter & MCP Execution (Weeks 7-8)
**Status: BUILT & VERIFIED (mock path + validation layer) / BUILT, UNVERIFIED HERE (live Gemini calls)**
- `incident-arbiter/arbiter.py` - `GeminiArbiter` (real `google-genai` Vertex AI backend call, written to the plan's 3-way classification protocol) and `MockArbiter` (deterministic rule-based fallback, same interface). `build_arbiter()` auto-selects based on `GOOGLE_CLOUD_PROJECT` presence. Both route their output through `parse_verdict_json()`, which validates root-cause and remediation-tool names against an explicit allow-list before anything reaches the MCP client - added after edge-case testing found the original code had no such validation (see `docs/TEST_REPORT.md` #12).
- `incident-arbiter/synthetic_frames.py` - generates placeholder witness-camera / frustum-buffer PNGs per scenario (no real stage camera or render node available).
- Verified: `MockArbiter` correctly classifies all 3 scenarios (100% match against the expected root cause) in the Sprint 5 harness run below, plus 15 dedicated edge-case tests (conflicting fault signals, empty manifests, malformed/hallucinated LLM-style JSON responses) in `tests/test_arbiter_edge_cases.py`.
- Not run: `GeminiArbiter`'s actual API call - no Google Cloud project/credentials or network egress to Google Cloud in this sandbox. Its response-parsing/validation logic (the part that doesn't need live credentials) is tested directly.
- `mcp-remediation/server.py` - real MCP server (Python `mcp` SDK), four tools matching the plan's exact function signatures. Hardened after edge-case testing found and fixed a genuine concurrent-call race condition and added input validation to all four tools - see `docs/TEST_REPORT.md` #9-11.

## Sprint 5: End-to-End Fault Injection Testing (Weeks 9-10)
**Status: BUILT & VERIFIED**
- `orchestrator/run_fault_injection_test.py` - drives all three fault scenarios through the real C++ engine (or a synthetic render-side flag for `dropped_frame`, which the tracker-only C++ engine can't observe), the arbiter, and a live MCP session.
- Verified result (last run): 3/3 correct root-cause classification, all three total-recovery times well under the 3s target, all MCP tool executions well under the 100ms target. Full JSON reports under `runs/<scenario>/incident_report.json`.
- Beyond the plan's stated scope, this build also did the throughput/load testing and concurrency stress testing the plan calls for in Sprint 2 (against the Sprint 1 C++ path directly, since Sprint 2's Kafka layer can't run here) and a dedicated MCP-server concurrency stress test - see `docs/TEST_REPORT.md` for the full account, including two real bugs (a receive-side throughput bottleneck and an MCP state-file race condition) that stress testing found and that are now fixed and regression-tested.
- Not performed: multi-hour soak testing, real network dropout injection (packet loss/reordering at the network layer, as opposed to application-level malformed packets, which *are* tested).

## Honest gaps vs. the full 10-week plan
- No real hardware-in-the-loop (tracking rig, LED wall, PTP grandmaster) anywhere - by design, per the hackathon scope.
- No live Kafka/Grafana Cloud/Vertex AI deployment - infra and credentials this sandbox doesn't have; source is complete and the seams (env vars, config files) are where you'd plug in real ones.
- No load/soak testing at the stated throughput targets.
