Saddle for Baxter's AI Hot Rod Tuner — integration & management notes

Purpose: collect telemetry from the Hot Rod Tuner API and forward for analysis.

Current config reference: `saddle/config.example.json` (subscribe HTTP poll: `http://localhost:8080/telemetry`).

Decision points for management:
- Approve polling interval and retention for telemetry.
- Decide whether to expose tuning endpoints to external agents or keep local.

Security notes:
- API endpoints should be protected if exposed; use API keys and avoid public exposure.

Verification steps:
1. `curl http://localhost:8080/telemetry` to confirm telemetry output (ops).

Owner: HRT product lead.

Functions & GUI Points:
- Primary functions: tuning controls, sound playback, policy/preflight UI.
- GUI touchpoints: web UI at `http://localhost:8080` (play, preflight, telemetry endpoints).
- Connected apps: BSR (audio control), RemoteDexter (agent orchestration), saddle collects HTTP telemetry for ops.

# Saddle — Baxters AI Hot Rod Tuner

What a saddle is:
- A non‑invasive sidecar that subscribes to the Hot Rod Tuner's telemetry endpoints or logs, applies deterministic corrections/enrichments, and forwards sanitized telemetry without changing the app.

Key components:
- Subscriber (HTTP poll or file tail), transform pipeline, forwarder, and audit logging.

Recommended workflow:
1. Use the saddle for immediate fixes (masking, sampling, short‑term enrichments).
2. Verify changes with saddle audit logs and health metrics.
3. Move permanent fixes to a git branch, run CI, merge, then remove or reduce saddle transforms.

Benefits & caveats:
- Enables fast iteration and compliance masking; however saddles introduce an operational surface to monitor and must not access secrets.

Files:
- `config.example.json` — example subscription/forward config

Deployment notes:
- Keep `saddle/config.json` versioned and enable audit logging; provide a health endpoint for the saddle runtime.

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server (default: http://localhost:8080)
python run_server.py

# 4. Verify health
curl http://localhost:8080/health
# Expected: {"status":"ok","uptime_secs":<N>}

# 5. (Optional) Generate PDF manuals
#    Requires pandoc and wkhtmltopdf installed system-wide
python generate_pdfs.py
```

