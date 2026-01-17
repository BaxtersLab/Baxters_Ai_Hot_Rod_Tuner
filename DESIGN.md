# Design — Baxters AI Hot Rod Tuner

Overview
--------
The Hot Rod Tuner is a local governor that mediates heavy AI workloads to protect hardware and maintain predictable performance.

Core components
---------------
- Telemetry Collector: polls or receives telemetry (LibreHardwareMonitor for Windows; /sys on Linux).
- Metrics Store: time-series buffer with short-term retention and rolling aggregates.
- Decision Engine: evaluates telemetry against policies and decides allow/defer/deny.
- Scheduler: enforces token-bucket fairness and cooldown windows.
- Enforcement Layer: signals job manager to throttle/pause/terminate jobs; emits audit events.

API surface
-----------
- `POST /telemetry` — ingest telemetry payload (agent/local collector)
- `GET /status` — current governor status + recent events
- `POST /preflight` — evaluate a job descriptor; returns `approved|defer|require_approval|denied`
- `POST /kill` — guarded kill switch (protected capability)

Policies
--------
- Temperature thresholds per device class with hysteresis
- Token bucket for concurrent heavy-job slots
- Priority classes with graceful backoff
- Secure mode: when enabled, certain actions require admin/secure approval

Audit
-----
- All decisions and enforcement actions must be logged via the Glue audit JSONL interface.

Integration points
------------------
- `glue.scheduler.request` / `glue.scheduler.status`
- `glue.governor.events`
- Admin chat voting via `glue.chat.admin_vote` (future)

Security
--------
- The `kill` API and tuning endpoints are protected capabilities; require `secure_mode` and explicit audit events.
- Avoid storing secrets in this folder.

Next steps
----------
1. Scaffold Python package and minimal HTTP API (FastAPI) in a `src/` folder.
2. Add telemetry sample payloads.
3. Add unit tests for policy logic (threshold/hysteresis + token bucket).
