# Baxter's AI Hot Rod Tuner — User Manual

## Table of Contents
1. [Introduction](#introduction)
2. [System Requirements](#system-requirements)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Dashboard Guide](#dashboard-guide)
6. [Temperature Thresholds](#temperature-thresholds)
7. [E-Stop & Process Kill](#e-stop--process-kill)
8. [App Linking](#app-linking)
9. [Sound System](#sound-system)
10. [Troubleshooting](#troubleshooting)
11. [Developer API Reference](#developer-api-reference)

---

## Introduction

Baxter's AI Hot Rod Tuner (HRT) is a compact, always-on hardware monitor for Windows. It sits in the bottom-right corner of your screen and shows real-time CPU, GPU, and RAM usage alongside temperatures. When things get too hot, it warns you with audible beeps and can automatically kill processes to protect your hardware.

HRT is designed for homelab users running heavy AI workloads — local LLMs, image generators, training jobs — where thermal runaway is a real risk and you want a kill switch that acts faster than you can.

### What It Does
- Monitors every CPU core (usage + temperature) and GPU (usage + temperature)
- Three-tier alert system: Warning, Throttle, E-Stop
- Automatic process termination when temps breach the E-Stop threshold
- Links with other Baxter apps (AiSmartGuy, GGUF Chatbox) so HRT can kill them remotely
- Single-instance enforcement — only one HRT can run at a time

---

## System Requirements

- **OS:** Windows 10 or 11
- **CPU:** Any multi-core processor
- **RAM:** 2 GB free (HRT itself uses ~50 MB)
- **GPU monitoring:** NVIDIA GPU with nvidia-smi on PATH, or any GPU visible to LibreHardwareMonitor
- **Browser engine:** Microsoft Edge (used internally for the GUI window)
- **Admin privileges:** Required on first launch so LibreHardwareMonitor can read hardware sensors

---

## Installation

### End Users (exe)

1. Download the release package.
2. Place the folder anywhere on your system. Example:
   ```
   C:\BaxtersApps\Hot Rod Tuner\
   ```
3. Inside the folder you need:
   ```
   Hot Rod Tuner.exe
   assets\              (sound files go here, optional)
   ```
4. Double-click **Hot Rod Tuner.exe** to launch.
5. Windows may prompt for admin elevation (required for temperature sensors). Click Yes.

### Developers (from source)

1. Clone the repository.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run:
   ```
   run.bat
   ```
   Or manually:
   ```
   set PYTHONPATH=src
   python run_server.py
   ```

### Building the Exe

```
python -m PyInstaller "Hot Rod Tuner.spec" --noconfirm
```
Output lands in `dist/Hot Rod Tuner.exe`. Copy the `assets/` folder next to it before distributing.

---

## Quick Start

1. Run **Hot Rod Tuner.exe**.
2. A splash screen appears briefly, then a compact window opens in the bottom-right corner.
3. A startup sound plays (if a .wav file is in the assets/ folder).
4. Live sensor bars begin streaming within 1-2 seconds.

That's it. HRT is now monitoring your hardware.

---

## Dashboard Guide

The HRT window is a narrow 200x450 pixel panel. From top to bottom:

### Title Bar

| Element | What It Does |
|---------|--------------|
| **HRT** (blue text, left side) | **Reset button.** Click this to completely reset the dashboard. It disconnects the data stream, clears all sensor bars, dismisses any active alert, plays the startup sound, and reconnects from scratch. **Use this whenever the app appears frozen or stops updating.** |
| **Green/Red dot + text** (right side) | Connection status. Green "Live" = data streaming. Red = disconnected (auto-reconnects every 2 seconds). "Reconnecting..." = watchdog detected a stale connection and is recovering. |

> **Important:** The HRT button is the only non-obvious control in the app. It is NOT just a logo — it is your manual recovery button. If the app freezes or bars stop moving, click it.

### Sensor Lanes (main area)

The scrollable center of the window shows one group per hardware component:

- **Top bar** — Usage (%, green/yellow/orange/red based on load)
- **Bottom bar** — Temperature (degrees C, colored by your threshold settings)

Each group is labeled on the left:

| Label | Meaning |
|-------|---------|
| CPU 0 through CPU 11 | Individual CPU cores (logical cores, including hyperthreads) |
| CPU Total | Overall CPU usage |
| GPU 0 | Primary GPU |
| RAM | System memory usage |

Bar colors change dynamically based on temperature thresholds (see next section).

### Alert Banner

When a temperature threshold is breached, a colored banner slides in below the title bar:

| Color | Level | What Happens |
|-------|-------|--------------|
| Yellow | **Warning** | Banner shows temp reading. Short beep. |
| Orange | **Throttle** | Banner shows "THROTTLE" + temp. Louder beep. |
| Red | **E-Stop** | Banner shows "E-STOP" + temp. Alarm beep. All monitored and linked processes are automatically killed. |

The banner shows which component triggered it (e.g. "CPU 78C" or "GPU 92C"). The alert fires immediately when temps cross the threshold — no delay.

### Bottom Toolbar

| Button | Function |
|--------|----------|
| **E-STOP** | Manual emergency stop. Asks for confirmation, then kills all Process Tray entries and Linked Apps. |
| **Gear icon** | Opens/closes the Settings panel. |

### Settings Panel

Click the gear icon to expand. The panel drops up from the toolbar and contains five sections:

#### CPU Thresholds (degrees C)
Three inputs: **Warn**, **Throttle**, **E-Stop**. Default: 70 / 82 / 95.
Changes take effect instantly. If current temps already exceed a new threshold, the alert fires immediately.

#### GPU Thresholds (degrees C)
Same three tiers. Default: 75 / 85 / 97.

#### Process Tray
Manually add exe paths (e.g. C:\path\to\heavy_app.exe). These processes are:
- Shown with a green/grey dot indicating whether they are currently running
- Killed when E-Stop fires (manual or automatic)

Click the X button to remove an entry. Entries persist in browser localStorage across sessions.

#### Linked Apps
Shows external apps that registered themselves with HRT via the /link API (e.g. AiSmartGuy, GGUF Chatbox). These appear automatically — you do not add them manually. Each entry shows the app name and PID. Linked apps are killed on E-Stop just like Process Tray entries.

#### Sound
- **Sound Folder button** — Opens the assets/ folder in Explorer. Drop any .wav file here. The first .wav file found is used as the startup and reset sound.
- Shows the current sound file name, or "No .wav file found".

### Close Behavior

- If any processes are in the tray or linked, a confirmation dialog asks if you really want to close.
- When the window closes, the server shuts down automatically.

---

## Temperature Thresholds

### How They Work

HRT checks every sensor reading once per second against your thresholds. The highest CPU core temp is compared against CPU thresholds. The highest GPU temp is compared against GPU thresholds. The worse of the two determines the overall alert level.

| Threshold | Default (CPU) | Default (GPU) | Effect |
|-----------|---------------|---------------|--------|
| Warn | 70C | 75C | Yellow banner + beep |
| Throttle | 82C | 85C | Orange banner + louder beep |
| E-Stop | 95C | 97C | Red banner + alarm + automatic process kill |

### Changing Thresholds

Open Settings (gear icon), adjust the number inputs. Changes are saved to localStorage and persist across restarts. The alert system re-evaluates instantly when you change a value — if your current temps already exceed the new threshold, the alert fires immediately without waiting for the next sensor tick.

### Testing Thresholds

To test without actually overheating your system: lower the E-Stop threshold to just below your current CPU or GPU temperature. The red alert should fire immediately, and any linked or monitored processes should be terminated.

---

## E-Stop & Process Kill

### What Gets Killed

When E-Stop fires (automatically from temperature or manually via the E-STOP button):

1. **Linked Apps** — killed by PID first (fast, reliable), then by exe path (catches new instances)
2. **Process Tray entries** — killed by exe path matching

HRT does NOT kill itself. It stays running so you can see the alert and monitor recovery.

### Kill Mechanism

- Uses psutil to send a graceful terminate signal to the process
- Waits up to 5 seconds for the process to exit
- Every kill is logged to audit/hotrod_audit.jsonl

### Manual E-Stop

Click the E-STOP button in the toolbar. A confirmation dialog appears. On confirm, all processes are killed immediately regardless of temperature.

---

## App Linking

### Overview

External apps can register themselves with HRT so they are automatically included in E-Stop kills. The link is one-way: the external app sends a single HTTP POST to HRT. HRT holds the registration in memory.

### How It Works

1. External app sends a POST request to http://127.0.0.1:8080/link with:
   ```json
   {
     "app_name": "AiSmartGuy",
     "exe_path": "C:\\path\\to\\AiSmartGuy.exe",
     "pid": 12345
   }
   ```
2. HRT stores the entry. It appears in the Linked Apps section within a few seconds.
3. On E-Stop, HRT kills the app by PID and by exe path.

### Re-registration

- If HRT restarts, all links are lost. External apps must re-register.
- If the external app restarts (new PID), it should re-register.
- Posting the same app_name replaces the previous entry (deduplication by name).

### Currently Supported Apps

- **AiSmartGuy** — links automatically on startup via Tauri invoke
- **GGUF Chatbox** — links automatically on startup

See devs/DEV_NOTES_APP_LINKING.txt for implementation details if you want to add HRT link support to your own app.

---

## Sound System

### Setup

1. Click the gear icon, then click the Sound Folder button to open the assets/ folder.
2. Drop any .wav file into that folder.
3. HRT uses the first .wav file it finds (alphabetical order).

### When Sound Plays

- **App startup** — immediately after the splash screen
- **HRT reset** — when you click the blue HRT text in the title bar
- **Threshold alerts** — short synthesized beeps (not the .wav file) for warn, throttle, and e-stop levels

### Requirements

- WAV format (uncompressed)
- Any sample rate and channel count
- Keep files reasonably small (under 5 MB) for fast loading

---

## Troubleshooting

### App Appears Frozen (bars not updating)

1. Click the **HRT** text in the title bar. This resets the entire dashboard and reconnects.
2. If that does not help, check the connection dot. If red, the server may have crashed. Close and relaunch the exe.
3. A built-in watchdog automatically reconnects if no data arrives for 5 seconds.

### No Temperature Data (bars show 0C or are missing)

- LibreHardwareMonitor needs admin elevation to read hardware sensors. If you clicked "No" on the Windows UAC prompt, restart HRT and click "Yes".
- LHM is bundled in vendor/lhm/. It launches automatically — you do not need to install it separately.
- Temperature data takes 2-3 seconds to appear after startup.

### Only 6 CPU Core Temps (but 12 cores shown)

This is normal. If you have a 6-core/12-thread CPU (hyperthreading), only 6 physical cores have temperature sensors. HRT automatically duplicates the physical core temps to their corresponding hyperthreaded logical cores.

### No Beep on Threshold Breach

- Click anywhere in the HRT window first. Browsers require a user gesture before playing audio. One click anywhere unlocks audio for the entire session.
- Check that your system volume is not muted.

### E-Stop Did Not Kill the Process

- Verify the linked app's PID is still valid (check Linked Apps in Settings).
- If the external app restarted since linking, it has a new PID. It needs to re-register with HRT.
- Path-based kill is case-insensitive but requires an exact full path match.

### "Another instance is already running"

HRT enforces single-instance via a Windows mutex. Close the existing instance first, or check Task Manager for a leftover Hot Rod Tuner.exe process and end it.

### Port 8080 Already in Use

Another application is using port 8080. Close it, or find and kill the process:
```
netstat -ano | findstr :8080
taskkill /PID <pid_number> /F
```

---

## Developer API Reference

HRT runs a FastAPI server on http://127.0.0.1:8080. All endpoints accept and return JSON.

### Sensor Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| WebSocket | /ws/sensors | Streams sensor snapshots at 1 Hz |
| GET | /api/sensors | Single sensor snapshot (REST fallback) |

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Returns status and uptime in seconds |
| GET | /status | Full status: governor, scheduler, current metrics |

### App Linking

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /link | Register an external app. Body: {app_name, exe_path, pid} |
| GET | /link | List all currently linked apps |

### Process Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/kill | Kill by exe path. Body: {path, dry_run, actor, scope} |
| POST | /api/kill-pid | Kill by PID. Body: {pid, actor, scope} |
| POST | /api/shutdown | Shut down HRT itself (no body required) |
| GET | /api/processes | List all running exe paths on the system |

### Sound

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /sound/play | Play the startup sound |
| GET | /sound/available | List available .wav files |
| GET | /api/sound-folder | Get the assets folder path |
| POST | /api/sound-folder/open | Open assets folder in Explorer |

### GUI

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | / | Serves the HTML dashboard |

---

*Baxter's AI Hot Rod Tuner — built to keep your hardware alive while you push it hard.*