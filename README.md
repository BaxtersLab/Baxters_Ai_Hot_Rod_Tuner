# Baxters AI Hot Rod Tuner

Purpose: lightweight governor/tuner service to protect homelab hardware while enabling strong local AI workflows.

Goals:
- Telemetry collection (CPU/GPU temps, fan speeds, power draw, RAM, disk I/O)
- Thermal governor with cooldown/resume, hysteresis, and kill-switch
- Preflight approval for heavy jobs with scheduling and fairness
- Audit every enforcement action to the Glue audit trail

Quick start:
- This folder contains design notes, a TODO list, and example payloads.
- Next: scaffold a small Python package with telemetry ingestion and a dry-run governor API.
