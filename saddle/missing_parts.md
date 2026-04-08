HRT — Missing / Unfinished Items

- `TODO.md` exists indicating outstanding work; `Missing Dependencies` section in docs notes external requirements not installed.
- Some runtime helpers and optional modules may be uninstalled (see `generate_pdfs.py` missing dependencies message).

Recommended action: enumerate required Python packages from `requirements.txt`, install and verify runtime, and resolve items listed in `TODO.md`.

---

## Quality Audit Notes (2026-03-29)

**Score: 3/5** — Solid saddle structure, needs operational polish.

### Improvements Needed

1. **Config gaps**: Add HTTP poll interval and timeout to `config.example.json` (currently just endpoint URL, no retry/backoff)
2. **Health endpoint**: Add `http://localhost:8080/health` to saddle config for liveness probing
3. **Telemetry transforms**: Define masking transforms for sensitive data (process names, timestamps with PII)
4. **Python deps**: Resolve `generate_pdfs.py` requirements — pin versions in `requirements.txt` and add `pip install -r requirements.txt` to startup checklist
5. **Missing pipe_path/metrics_bind**: Saddle config lacks standardized `pipe_path` and `metrics_bind` entries that other apps define

### Cross-Suite Alignment

- Adopt VirtualOffice's P0/P1/P2 priority model for missing items
- Add conformance test: verify telemetry actually reaches the saddle's subscribe endpoint
- Implement shared health-check protocol (`GET /health` → 200 if operational)
