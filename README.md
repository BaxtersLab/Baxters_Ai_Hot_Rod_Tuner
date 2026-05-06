![Baxter's AI Hot Rod Tuner](assets/Hot%20rod%20tuner%20banner.png)

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
| `/api/fans` | GET | Fan optimizer state |
| `/api/fans/optimize` | POST | Set fan aggressiveness (0-100) |

## Fan Optimizer

The **Optimize Fans** slider (above the toolbar in the dashboard) ramps CPU and case fans beyond their idle baseline when you're running heavy workloads.

- Slide right to push fans harder. Slide back to zero to restore hardware defaults.
- Fan speed is **never reduced below the measured baseline** — the optimizer only raises fans.
- **GPU fans are never touched** — GPU drivers manage their own thermal curves.

### Policy auto-raise

When CPU temps enter the orange zone (≥75 °C by default) the policy engine automatically raises fan aggressiveness without affecting your manual slider. Your manual setting always wins if it is set higher.

| CPU peak temp | Auto aggressiveness |
|---|---|
| < 75 °C | 0 (no change) |
| 75–79 °C | 40 |
| 80–89 °C | 70 |
| ≥ 90 °C | 100 |

### Hardware backend

HRT auto-detects which fan control backend your machine supports:

| Backend | Hardware | Status |
|---|---|---|
| **Dell SMM** (`HrtDellFanControl.exe`) | Dell workstations / laptops | ✅ Tested (Dell Precision, Xeon) |
| **LHM** (`HrtFanControl.exe`) | Generic boards (ASUS, MSI, Gigabyte, etc.) | ⚠️ Coded, not yet tested on non-Dell hardware |

The correct backend is probed automatically on first fan write — no configuration required.

#### Dell SMM setup (one-time, requires reboot)

Dell locks fan control away from LibreHardwareMonitor. The Dell backend uses [FanControl.DellPlugin](https://github.com/Rem0o/FanControl.DellPlugin) (BZH kernel driver). Two admin steps are required before first use:

1. From an **elevated 64-bit PowerShell** (Win+X → PowerShell Admin):
```powershell
bcdedit /set testsigning on
```
2. Also from elevated PowerShell:
```powershell
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy" -Name "UpgradedSystem" -Value 0 -Type DWord -Force
```
3. Reboot.

The app itself self-elevates via UAC on every launch (required for the kernel driver).

## Linking Your App

Any application can register with HRT for thermal protection:

```bash
curl -X POST http://127.0.0.1:8090/link \
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
