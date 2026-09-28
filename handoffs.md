# handoffs — Baxters Ai Hot Rod Tuner

_Append-only. Newest entry at the top._

## [2026-09-28] — Owner review: the suite committed, the Linux Sound Folder, and the GUI shipped at last (1.0.3)

Five commits on `linux`, not pushed. The fresh-clone gate agrees at each one
(listed = JUnit XML = passed): `88f98af` 25, `78a8795` 27, `f50eb28` 33,
`d9ea7b9` 34. The working tree is also 34.

### What changed

- **`f2e3845`**: state goes under XDG (`src/hotrod_tuner/paths.py`:
  `HOTROD_STATE_DIR` > `$XDG_DATA_HOME/hot-rod-tuner` >
  `~/.local/share/hot-rod-tuner`). `run_server.py` is packaged, and the .deb is
  named from its control (1.0.2).
- **`88f98af`**: `.gitignore` no longer hides `tests/`, so the suite is in git.
  A clean clone had 0 tests before this.
- **`78a8795`**: two fan tests that mutation showed were missing:
  - the RPM backstop, exercised through `_apply_pct_linux`;
  - the baseline keeping the busiest firmware state.
- **`f50eb28`**: the Sound Folder button ran `explorer`, which exists only on
  Windows, so it failed on every Linux install. Off Windows it now opens
  `<state dir>/sounds` with `xdg-open` and creates the folder on first use.
  SoundManager reads that folder before the bundled chime. Windows is
  unchanged.
- **`d9ea7b9`**: `static/` had never been in `build_deb.sh`'s payload list.
  Every installed copy through 1.0.2 opened a window reading
  `{"error": "GUI not found ..."}` instead of the tuner. The packager now ships
  it and refuses to build without `static/index.html`. Version 1.0.3.

### Verified

- **Clean VM**, from the harness's lean baseline (HRT 1.0.2 installed):
  - on 1.0.2, the window showed only the error JSON, and `POST
    /api/sound-folder/open` returned `No such file or directory: 'explorer'`;
  - after upgrading to 1.0.3 the full GUI renders, and Sound Folder opens an
    empty `~/.local/share/hot-rod-tuner/sounds` in Files;
  - a `.wav` dropped there is listed first, plays on demand and at the next
    startup, and shows in the Sound label.
- **Mutation**, 29 mutants, all killed:
  - fans: 15 (2 survived until `78a8795` added the tests above);
  - state paths: 3;
  - sound folder: 11.
- **Packaging guard**: a copy with `static` dropped from the list exits 1 with
  `FATAL: static/index.html is not in the payload`. The unmutated copy builds.

### Fan safety: run the suite with /sys read-only

The installed udev rule (`60-baxters-hot-rod-tuner-fans.rules`) makes the
real `pwm*` and `pwm*_enable` nodes writable by the desktop user, with no sudo.
Any code path that does not redirect `fan_manager._HWMON_ROOT` can drive the
real fans. That includes a test that forgets the fixture, a mutant, or
importing `app.py`. So run every test and mutant like this:

    bwrap --dev-bind / / --ro-bind /sys /sys .venv/bin/python -m pytest -q tests

Check first that `os.access('/sys/class/hwmon/hwmon0/pwm1_enable', os.W_OK)`
is False inside the sandbox. Throughout this review, `pwm*_enable` read 2
(BIOS auto) before and after every run.

### Found, not changed

- Two backup files are tracked in the repo:
  `build_deb.sh.pre-hygiene-2026-09-24.bak` and
  `run.sh.pre-venv-fix-2026-09-25.bak`.
- `tests/test_policy.py::test_sound_manager` plays the real chime through the
  speakers on every gate run, and asserts only that the result is a bool.
- The floater is kept above other windows by design, so a maximized HRT hides
  the Files window the button opens. At normal floater size, Files is visible
  around it.
- The "GUI not found" reply is HTTP 200, and its em dash renders as mojibake
  in the floater. It is unreachable now that `static/` ships.
- Three version strings disagree: `pyproject.toml` says 0.1.0, `__version__`
  says 0.0.1, and the .deb is 1.0.3.

## [2026-08-05] — White titlebar fixed: snap schema shadowing made GTK fall back to Adwaita

Operator: *"the title bar should be gray not white."*

Not a styling bug. `hrt_floater.py` builds a plain decorated `Gtk.Window`, so its
titlebar is painted by whatever GTK theme resolves — and the wrong one was
resolving.

### The chain

Ubuntu makes Yaru the default through a schema **override**, not a user setting:

```
/usr/share/glib-2.0/schemas/10_ubuntu-settings.gschema.override
    gtk-theme = "Yaru"

dconf read /org/gnome/desktop/interface/gtk-theme   ->  (empty)
```

With no user value in dconf, **the schema default decides**. VS Code's snap
exports `GSETTINGS_SCHEMA_DIR=/home/baxter/snap/code/<rev>/.local/share/glib-2.0/schemas`,
which ships its own compiled `org.gnome.desktop.interface` **without** Ubuntu's
override. It is searched first, so it wins and the default reverts to upstream
**Adwaita** — whose titlebar is white where Yaru's is gray.

Measured both ways:

| environment | `gtk-theme` | titlebar |
| --- | --- | --- |
| inherited from a VS Code terminal | `'Adwaita'` | **white** |
| snap vars scrubbed | `'Yaru'` | **gray** |

The same contamination also reports *"No such key `color-scheme`"*, another tell
that the snap's schema set is shadowing the system one.

This reached the window because `run_server.py` launches the floater with
`child_env` = the whole inherited environment, so anything leaked into `run.sh`
lands in the GTK process.

### Fix

`run.sh` now scrubs snap contamination **before any python is invoked** —
ordering matters, because `LOCPATH` points into snap locales built against a
different glibc and kills the interpreter outright with
`symbol lookup error: ... undefined symbol: __libc_pthread_init`.

Scrubbed by rule rather than a hand-picked list (a VS Code terminal leaks 21).
`XDG_DATA_DIRS` is **filtered**, not unset — it legitimately holds system paths,
and `/var/lib/snapd/desktop` is `snapd`, not `/snap/`.

`GSETTINGS_SCHEMA_DIR` is unset rather than redirected at a schema-shim. HRT
does not need one: the system and snap schema sets **both** lack
`org.gnome.settings-daemon.plugins.xsettings 'antialiasing'`, so removing the
snap's set changes nothing about the WebKitGTK abort that AiSmartGuy shims
around. Checked explicitly, because scrubbing blindly could have traded a
cosmetic bug for a startup crash. If the floater ever dies with a
`GLib-GIO-ERROR` about a missing key, that assumption has changed — copy
AiSmartGuy's `schema-shim/`.

### Verified

* `bash -n run.sh` clean.
* Ran the new scrub block and queried GTK directly:
  `gtk-theme-name = Yaru` (was `Adwaita`).
* **Not visually confirmed.** `hrt_floater.py` calls `set_keep_above(True)`, and
  CLAUDE.md forbids testing always-on-top surfaces on the live session, so the
  window was not launched. The theme resolution is proven; the operator seeing
  a gray titlebar is not yet.

### Notes

* HRT is **not** a Tauri app, despite the question arriving in that context —
  FastAPI/uvicorn with a WebKitGTK floater. The stack underneath (GTK3 +
  WebKitGTK 2.52.3) is the same, which is why the class of bug is shared.
* No Chromium-family browser is installed, so the `--app=` path never runs and
  the floater is always used. If chromium is ever installed it takes priority,
  and its titlebar is Chromium's — coloured from `<meta name="theme-color">`,
  which `static/index.html` does not currently set.
* Fan logic untouched (Article: fans may be tuned up, never down).
* Not committed.

## [2026-08-03] — Linux migration: full app running, real hardware telemetry

Ported the **real** app to Linux. It now runs on Ubuntu 26.04 with live sensor
data from this machine's own hardware.

### First, the thing to know: `Baxters_Ai_Hot_Rod_Tuner_Linux` is not this app

There is a second folder on the transfer drive named
`Baxters_Ai_Hot_Rod_Tuner_Linux`, and the SOC Master Widget's first button was
pointed at it. It is **930 LOC against this app's 2734**, and what is missing is
the entire point of a hardware tuner:

| removed | what it did |
| --- | --- |
| `sensors.py` | all sensor acquisition |
| `fan_manager.py` | all fan control |
| `telemetry_pipe.py` | telemetry transport |
| `splash.py` | startup splash |
| `static/`, `assets/` | **the whole web UI** |

Its own `linux_migration_notes.md` claims "No Windows-specific imports detected
— app appears fully Linux-compatible". That is true only because everything
Windows-specific was deleted rather than ported. What remains is a headless REST
governor that ingests telemetry pushed from elsewhere; it has no `GET /` route
at all, so the Master Widget button opened `http://127.0.0.1:8085` and got a
404. **That is why HRT had never been seen running on this box.**

The registry now points at this folder. The fork is left in place, untouched —
it may be wanted as a governor service, but it is not the tuner.

### What this hardware gives us

This is a Dell, and the mainline `dell_smm` driver is already loaded:

* 4 fans with true RPM, 4 chassis/DIMM temps, plus `coretemp` per-core
* GTX 1660 SUPER temperature via `nvidia-smi`
* `pwm1`–`pwm4` — **writable fan control exposed by the kernel**

Notably, PATH B of the Windows fan backend ships `HrtDellFanControl.exe` plus a
`bzh_dell_smm_io_x64.sys` ring-0 driver, and fights signing/AV quarantine, to
reach exactly the interface Linux hands over in sysfs for free.

### Done

**`run_server.py` aborted at import.** Line 29 called `ctypes.WINFUNCTYPE` at
module scope — that name does not exist off Windows, so the process died before
any application code ran. This was the single hard blocker. Now gated behind
`IS_WIN`, along with the console-ctrl handler, the single-instance mutex, and
the hide-console call.

**Single instance** uses a non-blocking `fcntl.flock` in `XDG_RUNTIME_DIR` on
POSIX. The kernel releases it on crash, where a PID file would strand the app.

**Browser launch** was Edge/Chrome absolute Windows paths plus `ctypes.windll.
user32` for screen metrics. Now: Chromium-family probe via `shutil.which`, a
Firefox fallback, `%TEMP%` → `tempfile.gettempdir()`, and screen size read from
`/sys/class/drm/*/modes` — chosen over `xrandr`/`xdpyinfo` because those are
X11-only and return nothing under Wayland, and because reading sysfs cannot
perturb the display configuration.

**`ELECTRON_RUN_AS_NODE` is stripped from the browser child's environment.**
VS Code's extension host exports it, every terminal inside VS Code inherits it,
and a Chromium binary that sees it boots as a bare Node runtime and rejects its
own flags, so the window silently never appears.

**GC stays enabled on Linux.** `gc.disable()` works around the *Windows* asyncio
proactor loop's cross-thread `__del__` abort. Keeping it off here would trade a
bug that does not occur on this platform for an unbounded heap in a server that
runs for days holding cyclic asyncio and deque structures.

**LHM is a no-op off Windows.** `launch_lhm()` is called unconditionally from
the startup event and would have hit `sc.exe` and `ShellExecuteW`.

**Sound**: added a subprocess player (`pw-play`, `paplay`, `aplay`, `ffplay`)
ahead of `playsound`, which on Linux has no native backend and reaches audio
through GStreamer/PyGObject — a binding stack pip cannot install on a PEP 668
system. Verified playing through PipeWire.

**Fixed a data-loss bug in sensor naming (affects Windows too).** Sensor *names*
are the dedup key and must be unique; sensor *labels* come from the kernel and
are not. `dell_smm` labels three DIMM probes `SODIMM` and three fans `Other
Fan`, so they collided and the dedup pass kept only the first of each. In
practice it **kept the empty 0.0 °C DIMM slot and discarded the real 34 °C and
33 °C readings, and dropped two fans spinning at 2959 and 2969 RPM**. Sensor
count went 21 → 25. `_uniq()` suffixes on collision only, so existing names are
unchanged.

**Fixed the backend-detection cache.** The startup warm-up thread called
`_detect_backend()` and discarded the result, so `_BACKEND` stayed `None` and
`/api/fans/backend` reported `"unknown"` until the operator first moved the
slider — precisely when a clear answer matters least. `_detect_backend()` now
caches.

**Fixed a double startup sound.** `app.py` played it at module *import* and
`run_server.py` played it again; anything that merely imported the app (tests,
`run.sh check`) also triggered it. Now fired once from the FastAPI startup
event, which is the event it is meant to signal.

**New Linux fan backend (`hwmon`)** in `fan_manager.py`, driving
`pwmN`/`pwmN_enable` directly. Safety properties, in priority order:

* GPU chips (`amdgpu`, `nouveau`, `nvidia`, `radeon`) are never touched — GPU
  thermal firmware reacts far faster than a 2 s poll loop.
* Detection tests **writability**, not mere presence. Reporting a backend when
  the nodes are unwritable would give the UI a live slider that does nothing.
* Duty is floored at 1/255, so engaging the slider can never stop a fan the
  firmware was running.
* Any failed write reverts that fan to automatic rather than leaving it latched.
* `stop()`, an `atexit` hook, and an explicit call before `os._exit()` in
  `_watch_browser_and_exit` all restore `pwmN_enable = 2`. That last one
  matters: `os._exit()` runs no atexit handlers, so closing the app window
  would otherwise leave a laptop latched in manual duty with the EC no longer
  ramping under load.

### Verification

* `run_server.py` imports on Linux; `_screen_size_linux()` → `(1920, 1080)`;
  flock acquires.
* `./run.sh check` → Python 3.14.4, temp chips `dell_smm, coretemp`, fan chip
  `dell_smm`, backend `none` **with reason**.
* Full launch under `systemd-run --user`: startup sound once, `GET /` **200**
  (34217 bytes), `/assets/HRT_ICON.png` 200, `WebSocket /ws/sensors` accepted
  and streaming **25 sensors per frame at ~1 Hz**, `/api/heartbeat` posting
  every 3 s from the page.
* Master Widget: all 5 registry entries resolve; `test_master_widget.py`
  37 passed, 8 skipped.

### The floater window — `hrt_floater.py` (new)

The compact always-there window is HRT's whole shape. Windows gets it from
`--app=<url>`; on Linux that needs a Chromium-family browser and this box has
only Firefox, which removed site-specific-browser support. Opening in Firefox
drags in the full browser chrome, and **that chrome — not HRT's layout — sets
the minimum window size**, which is what the operator hit when trying to shrink
it. The page is a `100vh` flex column and shrinks to anything.

`hrt_floater.py` hosts the same URL in a bare WebKitGTK WebView: no tab bar, no
address bar, opens at 200x450, `set_size_request(120, 120)`. No new packages and
no root — WebKitGTK's GI bindings arrived with the Tauri dependencies. GTK 3
deliberately: WebKit2-4.1 pairs with it, and GTK 4's Vulkan renderer is unstable
on this box's NVIDIA 595. `run_server.py` prefers it, then Chromium, then
Firefox. Decorations stay on — an undecorated window on Wayland gets no border,
grip or close button from the compositor, the same trap the Audio Suite Master
Panel fell into; `--undecorated` is available for anyone who wants it.

**This also restored close-to-exit**, which Firefox made impossible: Firefox
hands the URL to the already-running instance and its subprocess exits at once,
so `_watch_browser_and_exit`'s 3-second grace rule correctly classified every
launch as a handoff and never watched anything. The floater is a real long-lived
child, so closing it now shuts the server down. Verified: killing the floater
ended the server, released :8085 and took the unit inactive.

### Fan safety invariant — never slower than firmware

Operator requirement, stated directly: **"never allow them to be turned down
below default, only turned up."** They had also moved the BIOS profile from
quiet to medium noise, of unknown velocity.

The first cut of `_apply_pct_linux` violated this. `FanManager.apply_once`
computes `pct = max(20, effective)` and the backend wrote that as an *absolute*
duty — so with the BIOS on medium, a slider at 20% would have written 20% PWM
and slowed the fans down. Exactly the prohibited behaviour.

What makes it non-trivial: in automatic mode `dell_smm` returns **ENODATA for
pwmN**, so the firmware's current duty cannot be read back. Any absolute write
is a blind write, and no hardcoded floor is safe either, since the operator can
change the BIOS profile at any time. `fanN_input` (RPM) however is readable in
both modes — the baseline is unknowable in PWM but knowable in RPM.

The invariant is now enforced structurally:

1. Sample RPM while the firmware is still in charge -> `baseline_rpm` per fan,
   keeping the **highest** seen (the floor must clear the busiest observed
   state, not the idlest).
2. On first engage go straight to **duty 255**. Full speed is unambiguously at
   or above whatever the firmware was doing, so the invariant holds *through the
   handover itself* — the calibration happens while the fans are at maximum,
   never while they are guessing downward.
3. Measure RPM at 255 -> `rpm_max`. RPM is monotonic and roughly affine in PWM
   above stall, so the duty reproducing baseline is estimated as
   `255 * baseline/rpm_max`, inflated by `_FLOOR_MARGIN` 1.15 and `_FLOOR_PAD`
   12 because the real curve is concave and that estimate errs low.
4. Every applied duty is `max(requested, duty_floor)`. The floor only ever
   rises within a session.
5. Closed-loop backstop each cycle: any fan measured below 98% of its baseline
   raises the floor by 16/255. A bad estimate converges **upward**.
6. No usable RPM feedback -> floor pinned at 255. Loud, but there is no evidence
   any lower duty is safe and the invariant is not negotiable.
7. Release resets calibration entirely, so the next engage re-measures. A floor
   calibrated against "quiet" would sit below the real baseline under "medium".

Measured on this machine under the operator's current BIOS medium profile:
baseline **2801 / 2970 / 2938 RPM**, which derives a duty floor of roughly
**70-76%**. The slider therefore operates in the ~70-100% band; requests below
that are raised and logged, not obeyed.

**ENABLED AND VERIFIED ON REAL HARDWARE (2026-08-03, operator-approved).**

Two root-owned files were installed via `pkexec`; neither lives in this repo:

* `/etc/modprobe.d/dell-smm-hwmon.conf` -> `options dell_smm_hwmon restricted=0`
* `/etc/udev/rules.d/60-hrt-fan.rules` -> chgrp `baxter` + `g+w` on
  `/sys/class/hwmon/*/pwm*`, scoped to the `dell_smm` chip only

Both are required and neither suffices alone: `restricted` gates fan control
behind CAP_SYS_ADMIN, which is a *capability* check that file permissions cannot
satisfy, and `restricted=0` on its own still leaves the nodes `root:root 0644`.
It is load-time-only (absent from `/sys/module/dell_smm_hwmon/parameters`), so it
needs modprobe.d plus a driver reload. Revert steps are in both file headers.

Live test — BIOS on medium noise, **requesting 20%, the case that must not slow
anything**:

| fan | baseline | minimum observed | result |
| --- | --- | --- | --- |
| pwm1 | 2797 RPM | **4383 RPM** | never slower |
| pwm3 | 2981 RPM | **5034 RPM** | never slower |
| pwm4 | 2948 RPM | **4971 RPM** | never slower |

Duty floor calibrated to **198/255 (78%)**, so the 20% request was raised to 78%
and the fans went up. **0 violations.** Release restored `pwmN_enable = 2` on all
four and RPM returned to 2799 / 2978 / 2938 against a 2797 / 2981 / 2948
baseline. The operator confirmed both audibly ("sounds like max", then "now
lowering") — the brief max is the calibration pass at duty 255, which is exactly
what keeps the invariant true through the handover.

Consequence worth stating: with the BIOS baseline already at ~2800-2950 RPM, the
floor is 78%, so the slider's useful range is compressed to roughly 78-100%.
That is the honest cost of "never below default" when the default is already
medium; a quieter BIOS profile lowers the baseline, the floor, and widens the
range.

`tests/test_fan_safety.py` (new, 12 tests) drives the backend against a fake
sysfs tree whose RPM follows commanded duty. It covers the headline case (BIOS
medium + 20% request must not slow any fan), full-speed-first ordering, floor
monotonicity, the RPM backstop, GPU chips never being driven, release restoring
mode 2, and no-feedback pinning at 255. This is deliberately tested against a
fake rather than real hardware — the failure being guarded against is one you do
not reproduce on a real laptop to find out whether it works.

### UI sizing

* **Width.** The fan row was the one element that could not shrink — a hardcoded
  `width:240px` slider plus 34px and 120px cells, ~394px in total, while every
  other row already used `min-width: 0` flex. It alone set the usable minimum
  width. Now fully flexible (`flex: 1 1 40px` on the slider, ellipsised label and
  status), with the label hidden below 260px.
* **Height**, roughly 25% off the fixed chrome: title bar 22→17, E-STOP and gear
  buttons 22→18, `.lanes` padding 4→2, fan row and toolbar padding 6→3. The
  lanes area is `flex: 1` with `overflow-y: auto`, so everything else is free.
* Title bar recoloured `#111` → `#3a3a3a` at the operator's request.

### Remaining / needs the operator

* **Fan control is inactive and needs a decision.** All 4 pwm nodes are
  `root:root 0644`, so uid 1000 cannot write them. Enabling it means a udev rule
  granting group write on `/sys/class/hwmon/*/pwm*`, and on Dell hardware
  possibly `dell-smm-hwmon restricted=0`. Both are system-level changes with
  thermal consequences, so they were **not** made unattended. Monitoring is
  fully working meanwhile; the UI now states the reason.
* ~~No compact floater window.~~ **Resolved** by `hrt_floater.py` — see above.
  Chromium is no longer needed for this.
* Dependencies are in a local `.venv` (`--system-site-packages`). apt has
  suitable versions of all four (`python3-fastapi` 0.118, `python3-uvicorn`
  0.38, `python3-pydantic` 2.12.5, `python3-websockets` 15.0.1) and would be
  preferable, but installing them needs sudo.
* Not copied to the file cabinet yet.
* `/api/processes` returns 0 tracked processes — the process-tuning side of the
  app is unexercised.
* Not committed.

### Decisions

* **Ported the real app rather than adopting the `_Linux` fork.** The fork is
  the shape a migration takes when the hard parts are deleted; the mandate is a
  real app with solid functionality.
* **Kept one cross-platform codebase** instead of forking again — the existing
  fork is exactly the failure mode being avoided.
* **Did not enable fan control.** Requires system changes with thermal risk,
  while the operator is away.
