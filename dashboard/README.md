# Stage Mission Control

A standalone incident-summary dashboard for stage crew, built alongside
(not instead of) the Grafana Cloud observability layer in `../observability/`.
Grafana remains the system of record for metric history, P95/P99 jitter
trends, and alert routing (see `../docs/ROADMAP.md`, Sprint 3). This page
answers a narrower question at a glance: *what happened, what did the
system diagnose, and what did it do about it* — pulling from the same real
incident reports and stage state the rest of this repo produces
(`runs/*/incident_report.json`, `mcp-remediation/stage_state.json`).

## Data

All numbers in `StageMissionControl.jsx` are hand-transcribed from this
repo's last verified test run (see `docs/TEST_REPORT.md`). It's a static
snapshot, not a live feed — wiring it to live data means replacing the
`INCIDENTS` / `STAGE_STATE` / `ACTION_LOG` constants at the top of the file
with a fetch from wherever those JSON files end up served from (a small
API in front of `runs/` and `mcp-remediation/stage_state.json` would do it).

## Running it

This component was built for and verified inside an environment that
already provides React, Tailwind CSS, `recharts`, and `lucide-react`
(the Claude artifact runtime). To run it in a standalone project instead:

```bash
npm install react react-dom recharts lucide-react
npm install -D tailwindcss
npx tailwindcss init
```

Add `./StageMissionControl.jsx` to your Tailwind `content` config, import
the default export, and render it — it takes no props.

## Design notes

Dark, neutral palette (no neon, no blue/purple) inspired by broadcast/
engineering instrumentation rather than a SaaS dashboard: IBM Plex Sans for
UI text, IBM Plex Mono reserved for actual numeric telemetry readouts
(timestamps, jitter values, latencies), and three desaturated status colors
(muted green / red / amber) used functionally, not decoratively. No emoji.
