# Hot Rod Tuner — Development Roadmap

Last updated: May 5, 2026

---

## Current Architecture Status

### Fan Control Dual-Path System ✅ (code complete, pending hardware test)

HRT now supports two fan control backends, auto-detected at runtime:

| Backend | Shim | Library | Works on |
|---|---|---|---|
| **LHM** (Path A) | `HrtFanControl.exe` | `LibreHardwareMonitorLib.dll` | ASUS / MSI / Gigabyte / most generic boards that expose `SensorType.Control` fan sensors |
| **Dell SMM** (Path B) | `HrtDellFanControl.exe` | `DellSmbiosBzhLib.dll` + `bzh_dell_smm_io_x64.sys` | Dell Precision / Latitude / XPS where LHM returns 0 controllable fan sensors |

Detection runs once on first `apply_once()` call and caches the result:
1. Probe LHM shim with `pct=0` — exit 0 (≥1 sensor set) → use LHM
2. Probe Dell shim with `pct=0` — exit 0 → use Dell SMM
3. Neither works → log warning, slider becomes a no-op (no crash, no zombie)

Re-detection can be forced via `POST /api/fans/backend/reset` (useful after enabling the Dell driver at runtime).

---

## Completed Items ✅

| # | Item | Notes |
|---|---|---|
| 1 | Fan optimizer slider (UI) | `static/index.html` — above toolbar |
| 2 | `FanManager` service | `src/hotrod_tuner/fan_manager.py` |
| 3 | REST endpoints | `GET /api/fans`, `POST /api/fans/optimize`, `GET /api/fans/backend`, `POST /api/fans/backend/reset` |
| 4 | LHM shim (generic boards) | `vendor/lhm/HrtFanControl.exe` — compiles from `HrtFanControl.cs`, `.NET 4.0` |
| 5 | Dell SMM shim | `vendor/lhm/HrtDellFanControl.exe` — `DellSmbiosBzhLib` + kernel driver |
| 6 | Auto-detect backend | `_detect_backend()` in `fan_manager.py` — probes both, caches result |
| 7 | Policy auto-raise hook | `recommend_fan_aggressiveness()` in `policies.py` — raises fans on high CPU temp |
| 8 | Fan icon in title bar | 🌀 appears right of HRT logo when fans detected; spins when aggressiveness > 0 |
| 9 | Zombie process fix | Heartbeat watchdog — server `os._exit(0)` if no UI ping for 15 s |
| 10 | `fans_connected` in API | `/api/fans` returns count of non-GPU fan sensors visible to LHM |
| 11 | 10/10 unit tests | All passing after every change |

---

## Pending — Ordered by Priority

### P0 — Must resolve before fan control works on this machine

**Gate: Dell kernel driver signature**

The `bzh_dell_smm_io_x64.sys` driver is signed by a cert that expired Jan 2020. Windows rejects it with default settings.

**Fix (one-time, run as admin, then reboot):**
```powershell
bcdedit /set testsigning on
```
This puts Windows into test-signing mode, which trusts expired/self-signed kernel drivers. It adds a "Test Mode" watermark to the desktop — cosmetic only.

**To undo later:**
```powershell
bcdedit /set testsigning off
# then reboot
```

**Alternative (no reboot needed):** Find or compile a properly signed version of `bzh_dell_smm_io_x64.sys`. AaronKelley may have a newer release — check https://github.com/AaronKelley/DellFanManagement/releases.

---

### P1 — After reboot

**Step-by-step:**

1. Confirm Dell shim now works:
   ```powershell
   cd "c:\Users\Baxter\Desktop\HRT\Baxters Ai Hot Rod Tuner\vendor\lhm"
   .\HrtDellFanControl.exe 50
   # Expected: "[HrtDellFanControl] Set fans to Level1 (50%)"
   ```

2. Rebuild exe:
   ```powershell
   cd "c:\Users\Baxter\Desktop\HRT\Baxters Ai Hot Rod Tuner"
   Stop-Process -Name "Hot Rod Tuner" -Force -ErrorAction SilentlyContinue
   python -m PyInstaller "Hot Rod Tuner.spec" --noconfirm --distpath dist_new
   Copy-Item "dist_new\Hot Rod Tuner.exe" "dist\Hot Rod Tuner.exe" -Force
   ```

3. Human test checklist:
   - [ ] Slider at 0 → fans return to BIOS auto (quiet baseline)
   - [ ] Slider at ~35 → audible step up (Dell Level1)
   - [ ] Slider at ~70 → louder step (Dell Level2)
   - [ ] Slider at 100 → full blast (Dell Level2)
   - [ ] 🌀 fan icon appears on load; spins when slider > 0
   - [ ] Red X window → process exits cleanly within 15 s (no zombie)
   - [ ] GPU fans unchanged throughout

---

### P2 — Fan control: portability improvements

**Fan level granularity display**

Dell SMM only has 3 levels (low / medium / full), not continuous PWM. The slider shows 0-100 but maps to only 4 states. Plan:
- Surface `backend` from `GET /api/fans/backend` in the UI
- Show "Dell 3-level" or "PWM continuous" label next to the slider so the user knows what they're actually getting

**Detect and surface `backend` in `/api/fans`**

Currently `GET /api/fans` doesn't include backend info. Add `backend` key to `fan_manager.get_state()` so the frontend knows without a separate call.

---

### P3 — General hardening

| Item | Detail |
|---|---|
| Fan icon tooltip shows backend | "3 fans detected (LHM)" or "Dell SMM — 3 levels" |
| Test for Dell path in unit tests | Monkeypatch `_detect_backend` to return `'dell'`; assert shim called with correct exe |
| Write `CONTRIBUTING.md` note on adding backends | Document how to add a 3rd fan backend (e.g. IPMI for servers) |

---

### P4 — Publish to public repo

Once P0–P1 are verified with working fan control:

```powershell
cd "c:\Users\Baxter\Desktop\HRT\Baxters Ai Hot Rod Tuner"
git add -A
git commit -m "feat: Fan Optimizer — dual-path LHM+Dell SMM, fan icon, zombie fix"
git push
```

---

## Architecture Notes for Future Backends

To add a third fan control backend (e.g. IPMI for server boards, or ASUS AuraSync):

1. Add a new exe shim in `vendor/lhm/`
2. Add a probe branch in `_detect_backend()` in `fan_manager.py`
3. Add the exe reference to `_apply_pct_windows()` dispatch
4. No changes needed to `FanManager`, `app.py`, or the UI

The slider always sends 0-100. The backend maps that to whatever granularity the hardware supports.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| Dell SMM: 3 speed levels only | `BzhFanLevel.Level0 / Level1 / Level2` — not continuous PWM |
| Dell SMM: requires test-signing or expired cert workaround | One-time reboot needed |
| Fan detection (`fans_connected`) uses LHM RPM sensors, not backend | Even on Dell, LHM can read fan RPMs — so the icon still appears correctly |
| macOS / Linux | Fan control paths are Windows-only; server runs but slider is a no-op |
