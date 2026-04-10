# Baxter's AI Hot Rod Tuner

A real-time temperature governor for heavy resource-draw apps. HRT monitors CPU and GPU thermals via LibreHardwareMonitor and will automatically throttle or emergency-kill linked applications when temperatures breach configurable thresholds.

Built for homelab rigs running local AI workloads where thermal runaway can damage hardware.

## How It Works

1. **Launch HRT** — a compact 200×450 px dashboard docks to the bottom-right of your screen.
2. **Sensors stream in** — CPU core temps and GPU temps update every second via WMI (LibreHardwareMonitor).
3. **Thresholds trigger alerts** — three levels per sensor type:
   - **Yellow** — advisory warning
   - **Orange** — throttle signal
   - **Red** — E-STOP: linked apps are killed immediately
4. **Linked apps register themselves** — any app can `POST /link` with its name, exe path, and PID. HRT tracks them and can kill them on demand.
5. **E-STOP** — manual button or automatic threshold trigger. Kills linked apps by PID, then scans by exe name as fallback. Children processes (Tauri/Electron) are killed first.

## Features

- **Live sensor dashboard** — CPU and GPU temps, fan speeds, clocks via WebSocket
- **Three-tier threshold system** — yellow/orange/red per sensor, configurable in the UI
- **E-STOP** — emergency kill of linked apps (manual button + automatic trigger)
- **App linking protocol** — any app can register via REST API for monitoring and kill control
- **Process tray** — manually add exe paths for kill targeting
- **BSOD prevention** — dead-PID early bail, killed-names cleanup, 30s cooldown
- **Protected process list** — system-critical processes are never killed
- **Audit logging** — all kill events logged to JSONL
- **Startup sound** — customizable WAV sound on launch
- **Single-instance enforcement** — Windows named mutex prevents duplicates
- **Auto-elevation** — UAC admin prompt on launch (required for LHM access)

## Requirements

- Windows 10/11
- Python 3.12+ (3.14 tested)
- [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) v0.9.4+ (bundled in `vendor/lhm/`)
- Microsoft Edge (for app-mode dashboard window)
- Admin privileges (for WMI sensor access)

## Quick Start

```bash
pip install -r requirements.txt
python run_server.py
```

Or build the standalone exe:

```bash
python -m PyInstaller "Hot Rod Tuner.spec" --noconfirm
# Output: dist/Hot Rod Tuner.exe
```

## API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server health check |
| `/api/sensors` | GET | Current sensor readings |
| `/ws/sensors` | WS | Live sensor stream (~1s updates) |
| `/link` | POST | Register an app for monitoring/kill |
| `/link` | GET | List linked apps |
| `/api/estop` | POST | Emergency kill all linked + named targets |
| `/api/kill` | POST | Kill a process by name |
| `/api/kill-pid` | POST | Kill a process by PID |
| `/api/processes` | GET | List running processes |
| `/api/protected` | GET | List protected process names |
| `/status` | GET | Governor status and uptime |

## Linking Your App

Any application can register with HRT for thermal protection:

```bash
curl -X POST http://127.0.0.1:8080/link \
  -H "Content-Type: application/json" \
  -d '{"app_name": "MyApp", "exe_path": "C:/path/to/myapp.exe", "pid": 12345}'
```

When temps hit red, HRT kills all linked apps automatically.

## Project Structure

```
run_server.py           # Entry point: splash, server thread, Edge window
src/hotrod_tuner/
  app.py                # FastAPI app, E-STOP, kill logic, linking
  sensors.py            # WMI/LHM sensor polling
  metrics.py            # Metrics storage
  policies.py           # Policy/decision engine
  scheduler.py          # Job scheduler
  sound.py              # Startup sound manager
  splash.py             # Tkinter splash screen
static/
  index.html            # Dashboard UI (single-page)
vendor/lhm/             # LibreHardwareMonitor binaries
```

## License

MIT
