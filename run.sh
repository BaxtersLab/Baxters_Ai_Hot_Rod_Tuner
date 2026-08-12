#!/usr/bin/env bash
# Baxters Ai Hot Rod Tuner — Linux launcher (counterpart to run.bat).
#
# Uses a local .venv because Ubuntu 26.04 ships an externally-managed (PEP 668)
# system Python that pip refuses to write into, and gnome-shell depends on that
# interpreter. The venv is created with --system-site-packages so the apt build
# of psutil is reused rather than compiled again.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

# ── Snap contamination scrub — MUST run before any python is invoked ─────────
#
# Two separate failures, both traced 2026-08-05.
#
# 1. THE WHITE TITLEBAR. Ubuntu makes Yaru the default GTK theme through a
#    schema OVERRIDE, not a user setting:
#      /usr/share/glib-2.0/schemas/10_ubuntu-settings.gschema.override
#        gtk-theme = "Yaru"
#      dconf read /org/gnome/desktop/interface/gtk-theme -> (empty)
#    With no user value, the schema default decides. VS Code's snap exports
#    GSETTINGS_SCHEMA_DIR pointing at its OWN compiled schema set, which ships
#    org.gnome.desktop.interface WITHOUT Ubuntu's override. Searched first, it
#    wins, the default reverts to upstream "Adwaita", and hrt_floater.py draws
#    an Adwaita (WHITE) titlebar instead of Yaru (GRAY).
#    Measured: gtk-theme resolves to 'Adwaita' contaminated, 'Yaru' clean.
#
#    It matters here specifically because run_server.py hands the floater
#    `child_env` = the whole inherited environment, so anything leaked into
#    this script reaches the GTK window.
#
# 2. LOCPATH KILLS PYTHON OUTRIGHT. It points into the snap's locales, built
#    against a different glibc, and produces
#      symbol lookup error: ... undefined symbol: __libc_pthread_init
#    That is why this block runs before `python3 -m venv`, not after.
#
# Scrub by rule, not by a hand-picked list — a VS Code terminal leaks 21 of
# these. XDG_DATA_DIRS is FILTERED rather than unset: it legitimately holds
# system paths (and /var/lib/snapd/desktop, which is snapd, not /snap/).
#
# NOTE: GSETTINGS_SCHEMA_DIR is unset rather than redirected at a schema-shim.
# HRT does not need one — the system and snap schema sets BOTH lack
# org.gnome.settings-daemon.plugins.xsettings 'antialiasing', so removing the
# snap's set changes nothing about the WebKitGTK abort that AiSmartGuy shims
# around. If the floater ever starts dying with a GLib-GIO-ERROR about a
# missing key, that assumption has changed — copy AiSmartGuy's schema-shim/.
for _var in $(env | grep -o '^[A-Za-z_][A-Za-z0-9_]*=/snap/[^:]*' | cut -d= -f1); do
    [[ "$_var" == "XDG_DATA_DIRS" ]] && continue
    unset "$_var"
done
for _var in GSETTINGS_SCHEMA_DIR GTK_PATH GTK_IM_MODULE_FILE GTK_EXE_PREFIX \
            GIO_MODULE_DIR LOCPATH GDK_PIXBUF_MODULEDIR GDK_PIXBUF_MODULE_FILE \
            XDG_DATA_HOME XDG_CONFIG_HOME XDG_CACHE_HOME; do
    [[ "${!_var:-}" == *"/snap/"* ]] && unset "$_var"
done
unset _var
# ELECTRON_RUN_AS_NODE makes a Chromium binary start as a bare Node runtime.
# run_server.py already strips it for the browser child; clear it here too so
# the floater and every other child sees a clean environment.
unset ELECTRON_RUN_AS_NODE
if [[ "${XDG_DATA_DIRS:-}" == *"/snap/"* ]]; then
    _clean=""
    IFS=':' read -ra _parts <<< "$XDG_DATA_DIRS"
    for _p in "${_parts[@]}"; do
        [[ -z "$_p" || "$_p" == */snap/* ]] && continue
        _clean="${_clean:+$_clean:}$_p"
    done
    export XDG_DATA_DIRS="${_clean:-/usr/local/share:/usr/share}"
    unset _clean _parts _p
fi

VENV=".venv"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "[HRT] Creating virtualenv…"
    python3 -m venv --system-site-packages "$VENV"
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r requirements.txt
fi

# requirements.txt marks wmi as win32-only, so this stays a no-op reinstall here.
if ! "$PY" - <<'EOF'
import importlib.util, sys       # importing importlib alone does not bind .util
missing = [m for m in ("fastapi", "uvicorn", "pydantic", "psutil", "websockets")
           if not importlib.util.find_spec(m)]
sys.exit(1 if missing else 0)
EOF
then
    echo "[HRT] Installing missing dependencies…"
    "$PY" -m pip install --quiet -r requirements.txt
fi

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
export HOTROD_PORT="${HOTROD_PORT:-8090}"

case "${1:-}" in
    server)
        # Headless: no splash, no browser. For remote access or debugging.
        exec "$PY" -m uvicorn hotrod_tuner.app:app \
            --host "${HOTROD_HOST:-127.0.0.1}" --port "$HOTROD_PORT"
        ;;
    check)
        exec "$PY" - <<'EOF'
import platform, psutil
print("python  :", platform.python_version())
print("system  :", platform.system(), platform.release())
t = psutil.sensors_temperatures() or {}
f = psutil.sensors_fans() or {}
print("temp chips:", ", ".join(t) or "none")
print("fan chips :", ", ".join(f) or "none")
import hotrod_tuner.fan_manager as fm
print("fan backend:", fm._detect_backend())
if fm._linux_detect_reason:
    print("  reason:", fm._linux_detect_reason)
EOF
        ;;
    *)
        exec "$PY" run_server.py
        ;;
esac
