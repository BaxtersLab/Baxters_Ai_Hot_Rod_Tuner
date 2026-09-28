import uvicorn
import os
import subprocess
import threading
import shutil
import time
import logging
import sys
import traceback
from threading import Event
from hotrod_tuner.sound import sound_manager
from hotrod_tuner.splash import show_splash

# ── File-based crash logger (independent of app.py's logger) ─────────
# NOT beside this file: installed, that directory is /opt/baxters/hot-rod-tuner
# and is root-owned, so makedirs() raised PermissionError before the app started.
from hotrod_tuner.paths import data_dir as _data_dir
_LOG_DIR = str(_data_dir())
os.makedirs(_LOG_DIR, exist_ok=True)
_run_log = logging.getLogger('hrt_run')
_run_log.setLevel(logging.DEBUG)
_run_fh = logging.FileHandler(os.path.join(_LOG_DIR, 'hrt_main_thread.log'), mode='a', encoding='utf-8')
_run_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_run_fh.stream.reconfigure(write_through=True)  # auto-flush every write
_run_log.addHandler(_run_fh)

# ── DO NOT redirect stdout/stderr — asyncio writes from non-main
#    threads and a replaced file object causes crashes at ~20s ────

IS_WIN = sys.platform == "win32"

# ── Console ctrl handler — MUST live in __main__ module to avoid GC ──
# Windows only: ctypes.WINFUNCTYPE and ctypes.windll do not exist on POSIX,
# so touching them at module scope aborted the import before anything ran.
# POSIX has no console-control-event concept; SIGINT/SIGTERM already arrive
# as ordinary signals and are handled by the KeyboardInterrupt path below.
if IS_WIN:
    import ctypes as _ct
    _HANDLER_ROUTINE = _ct.WINFUNCTYPE(_ct.c_int, _ct.c_uint)
    @_HANDLER_ROUTINE
    def _main_console_handler(event):
        _run_log.warning(f'[run_server] Console control event: {event}')
        return 1  # Block ExitProcess
    # Store globally so it can NEVER be garbage collected
    _PREVENT_GC_CONSOLE_HANDLER = _main_console_handler
    _ct.windll.kernel32.SetConsoleCtrlHandler(_main_console_handler, 1)
    _run_log.info('Console ctrl handler installed in __main__')

# ── atexit: last-resort logging before process exit ──────────────────
import atexit as _atexit
def _on_atexit():
    _run_log.critical('atexit handler fired — process exiting')
    _run_fh.flush()
_atexit.register(_on_atexit)

# ── Override os._exit to log before dying ────────────────────────────
import os as _os_mod
_real_os_exit = os._exit
def _logged_os_exit(code):
    _run_log.critical(f'os._exit({code}) called!\n{traceback.format_stack()}')
    _run_fh.flush()
    _real_os_exit(code)
_os_mod._exit = _logged_os_exit

# ── Catch unhandled exceptions in ANY thread ─────────────────────────
def _thread_excepthook(args):
    _run_log.critical(
        f'Unhandled exception in thread "{args.thread.name if args.thread else "?"}":\n'
        f'{"\n".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))}'
    )
    _run_fh.flush()
threading.excepthook = _thread_excepthook

# ── Catch unhandled exceptions on the main thread ────────────────────
_orig_excepthook = sys.excepthook
def _sys_excepthook(exc_type, exc_value, exc_tb):
    _run_log.critical(
        f'Unhandled main-thread exception:\n'
        f'{"\n".join(traceback.format_exception(exc_type, exc_value, exc_tb))}'
    )
    _run_fh.flush()
    _orig_excepthook(exc_type, exc_value, exc_tb)
sys.excepthook = _sys_excepthook

_server_ready = Event()
_splash_done = Event()

# Reference to the browser app-mode process so we can watch it for exit
_browser_proc: subprocess.Popen | None = None


def _watch_browser_and_exit(proc: subprocess.Popen) -> None:
    """Block until the app-mode browser window closes, then hard-exit.

    When the user clicks the red X on the HRT floating window the browser
    process terminates.  We detect that here and call os._exit() so that
    every thread — uvicorn, sensor poller, LHM, the main keep-alive loop —
    is killed immediately.  Nothing is left behind as a zombie.

    Grace-period: if the subprocess exits in under 3 seconds it most likely
    handed the URL off to an already-running (non-elevated) Edge/Chrome
    instance and immediately returned — that is NOT a user-initiated close.
    In that case we leave the server alive so the handed-off window can
    connect normally.
    """
    _t0 = time.monotonic()
    proc.wait()  # blocks until browser exits (red X, or any other close)
    elapsed = time.monotonic() - _t0

    if elapsed < 3.0:
        # Fast exit — browser handed URL to existing instance (common when
        # HRT runs elevated and Edge/Chrome runs at normal privilege).
        # The real window is still open; keep the server alive.
        _run_log.warning(
            f'Browser subprocess exited in {elapsed:.2f}s — treated as '
            f'handoff to existing instance; server stays alive.'
        )
        _run_fh.flush()
        return

    _run_log.info('HRT browser window closed — shutting down all processes')
    _run_fh.flush()

    # os._exit() runs no atexit handlers and no FastAPI shutdown event, so any
    # fan we switched to manual would stay latched at that duty with the EC no
    # longer ramping it. Release before exiting; this is the one cleanup that
    # cannot be skipped.
    try:
        from hotrod_tuner.fan_manager import release_fans_now
        release_fans_now()
    except Exception as _e:
        _run_log.critical(f'Fan release before exit failed: {_e}')
    _run_fh.flush()

    # Hard-exit: kills all daemon threads (uvicorn, sensor poller, LHM)
    # in one shot.  No need to call stop_lhm() separately — process death
    # is the cleanest shutdown.
    import os as _os
    _os._exit(0)


def _webkit_available() -> bool:
    """True if the GTK3 + WebKit2 bindings the floater needs are importable.

    Checked in a subprocess: importing Gtk in this process would initialise GTK
    inside the server, and the splash already owns a Tk main loop here.
    """
    probe = ("import gi; gi.require_version('Gtk','3.0'); "
             "gi.require_version('WebKit2','4.1'); "
             "from gi.repository import Gtk, WebKit2")
    try:
        return subprocess.run([sys.executable, "-c", probe],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,
                              timeout=20).returncode == 0
    except Exception:
        return False


def _screen_size_linux(default=(1920, 1080)) -> tuple[int, int]:
    """Primary display size on Linux, read from sysfs.

    Deliberately does NOT shell out to xrandr/xdpyinfo: those are X11-only and
    return nothing under a Wayland session. /sys/class/drm is a read-only
    kernel interface that reports the same modes either way, and reading it
    cannot perturb the display configuration.
    """
    import glob
    for status_path in sorted(glob.glob('/sys/class/drm/card*/status')):
        try:
            with open(status_path) as fh:
                if fh.read().strip() != 'connected':
                    continue
            with open(os.path.join(os.path.dirname(status_path), 'modes')) as fh:
                first = fh.readline().strip()
            w, _, h = first.partition('x')
            return int(w), int(h)
        except (OSError, ValueError):
            continue
    return default


def _open_app_window(url: str, width: int = 200, height: int = 450, wait_splash: bool = True):
    """Open HRT in a compact app-mode window (no address bar, no tabs).

    Stores the browser process in _browser_proc and starts a watcher thread
    so that closing the window (red X) kills the entire server process.
    """
    global _browser_proc

    # Wait for splash to fully close before opening Edge
    if wait_splash:
        _splash_done.wait(timeout=25)

    # Nuke cached Edge/Chrome window geometry so our size flags are always respected
    import tempfile as _tf
    cache_dir = os.path.join(_tf.gettempdir(), 'hrt-app-window')
    try:
        import shutil as _sh
        _sh.rmtree(cache_dir, ignore_errors=True)
    except Exception:
        pass

    # Chromium-family browsers, in preference order. shutil.which() covers the
    # PATH-installed Linux builds; the absolute paths are the Windows installs,
    # which never appear on PATH.
    if IS_WIN:
        candidates = [
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            shutil.which("chrome"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        candidates = [shutil.which(b) for b in (
            "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
            "brave-browser", "microsoft-edge", "microsoft-edge-stable",
        )]

    # Position at bottom-right corner of desktop.
    try:
        if IS_WIN:
            import ctypes
            user32 = ctypes.windll.user32
            scr_w = user32.GetSystemMetrics(0)
            scr_h = user32.GetSystemMetrics(1)
        else:
            scr_w, scr_h = _screen_size_linux()
        x = scr_w - width - 12
        y = scr_h - height - 48  # above taskbar
    except Exception:
        x, y = 1800, 740

    app_flags = [
        f"--app={url}",
        f"--window-size={width},{height}",
        f"--window-position={x},{y}",
        "--disable-extensions",
        f"--user-data-dir={cache_dir}",
    ]

    # VS Code's extension host exports ELECTRON_RUN_AS_NODE=1, and it is
    # inherited by everything launched from a terminal inside it. A Chromium
    # binary that sees it starts as a bare Node runtime and rejects its own
    # browser flags, so the window never appears. Strip it for the child.
    child_env = {k: v for k, v in os.environ.items() if k != 'ELECTRON_RUN_AS_NODE'}

    proc = None
    for cand in candidates:
        if cand and os.path.isfile(cand):
            proc = subprocess.Popen([cand] + app_flags, env=child_env)
            _run_log.info(f'App-mode browser: {cand}')
            break

    # WebKitGTK floater — the Linux equivalent of Chromium's --app mode.
    # Preferred over Firefox because Firefox dropped site-specific-browser
    # support, so its window carries the full browser chrome and *that* chrome,
    # not HRT's layout, sets the minimum window size. hrt_floater.py hosts the
    # same URL in a bare WebView, which shrinks to the 200x450 this UI is drawn
    # for. WebKitGTK is already installed as a Tauri dependency.
    if proc is None and not IS_WIN:
        floater = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "hrt_floater.py")
        if os.path.isfile(floater) and _webkit_available():
            # GDK_BACKEND=x11 routes the floater through XWayland.
            #
            # On Wayland this GTK window draws client-side decorations, and
            # its invisible ~26px resize shadow offsets every click target in
            # the titlebar -- the close button is drawn in one place and
            # responds in another, so pressing the X does nothing. The same
            # offset is documented on this box for other GTK CSD windows.
            #
            # Under XWayland the frame is server-side and the X lands where it
            # is drawn. It also makes set_keep_above() work, which this floater
            # asks for and Wayland silently ignores.
            #
            # XWayland is NOT Xorg. It is a rootless X server inside the
            # Wayland session, already running here, and nothing about this
            # starts or configures an Xorg session.
            floater_env = dict(child_env)
            if floater_env.get('WAYLAND_DISPLAY') and floater_env.get('DISPLAY'):
                floater_env['GDK_BACKEND'] = 'x11'
            proc = subprocess.Popen(
                [sys.executable, floater, url,
                 f"--width={width}", f"--height={height}"],
                env=floater_env)
            _run_log.info(f'WebKitGTK floater: {floater} ({width}x{height})')

    # Firefox fallback, when WebKitGTK is unavailable. --new-window at least
    # gives HRT its own window rather than a tab buried in an existing session.
    if proc is None and not IS_WIN:
        ff = shutil.which("firefox")
        if ff:
            proc = subprocess.Popen([ff, "--new-window", url], env=child_env)
            _run_log.info(f'Firefox fallback: {ff} — no app-mode, so the window '
                          f'cannot shrink to {width}x{height}')

    if proc is not None:
        _browser_proc = proc
        # Watcher thread: when the browser exits, kill the whole server
        threading.Thread(
            target=_watch_browser_and_exit,
            args=(proc,),
            name='hrt-browser-watcher',
            daemon=True,
        ).start()
        _run_log.info(f'Browser launched (pid={proc.pid}); watcher active')
    else:
        # Fallback: no watchable process — open in default browser
        import webbrowser
        webbrowser.open(url)
        _run_log.warning('No Edge/Chrome found; opened in default browser — close-to-exit not available')


def _run_server(host: str, port: int):
    """Start uvicorn in a background thread, signal ready once listening."""
    import urllib.request

    # Start uvicorn in its own thread
    srv_thread = threading.Thread(
        target=uvicorn.run,
        args=("hotrod_tuner.app:app",),
        kwargs={"host": host, "port": port, "reload": False},
        daemon=True,
    )
    srv_thread.start()

    # Poll health endpoint until server responds
    url = f"http://{host}:{port}/health"
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=1)
            _server_ready.set()
            return
        except Exception:
            time.sleep(0.25)

    # Timeout — set ready anyway so splash closes
    _server_ready.set()


def _already_running(host: str, port: int) -> bool:
    """Return True if an HRT server is already listening on host:port."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1)
        return True
    except Exception:
        return False


_lock_file = None  # POSIX: module-global so the flock is held for the process lifetime


def _acquire_single_instance() -> bool:
    """True if this process is the only HRT instance.

    Windows uses a named kernel mutex. POSIX has no equivalent, so this takes a
    non-blocking exclusive flock on a file in XDG_RUNTIME_DIR; the kernel drops
    it when the process dies, including after a crash, where a PID file would
    strand the app.
    """
    global _lock_file

    if IS_WIN:
        import ctypes
        _MUTEX_NAME = "Global\\BaxtersAiHotRodTuner_SingleInstance"
        ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS

    import fcntl
    import tempfile as _tf
    base = os.environ.get('XDG_RUNTIME_DIR') or _tf.gettempdir()
    try:
        fh = open(os.path.join(base, f'hot_rod_tuner_{os.getuid()}.lock'), 'w')
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    fh.write(str(os.getpid()))
    fh.flush()
    _lock_file = fh  # keep open; closing releases the lock
    return True


if __name__ == "__main__":
    import sys

    _is_first_instance = _acquire_single_instance()

    host = os.getenv("HOTROD_HOST", "127.0.0.1")
    port = int(os.getenv("HOTROD_PORT", "8090"))  # 8080 is reserved for LLM backend (GGUF Chatbox)
    url = f"http://{host}:{port}"

    if not _is_first_instance:
        # Another instance owns the mutex — just open a window to it
        print("HRT is already running — bringing window to front.")
        # Wait briefly for the server to become reachable (the other instance
        # may still be starting up).
        for _i in range(20):
            if _already_running(host, port):
                break
            time.sleep(0.5)
        _open_app_window(url, wait_splash=False)
        sys.exit(0)

    print("Starting Hot Rod Tuner...")

    # Startup sound now belongs to the server's startup event (see app.py) so it
    # plays exactly once; playing it here as well produced two overlapping copies.

    # Start server in background
    threading.Thread(target=_run_server, args=(host, port), daemon=True).start()

    # Open floater window once server is ready (background)
    threading.Thread(target=_open_app_window, args=(url,), daemon=True).start()

    print(f"Hot Rod Tuner -> {url}")

    # Splash runs on main thread (tkinter requirement), blocks until done
    show_splash(_server_ready, _splash_done)

    # Hide the console window now that startup is complete.
    # Windows-only: a POSIX terminal is owned by the shell, not the process,
    # and there is no equivalent "hide my console" call.
    if IS_WIN:
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    _run_log.info('Splash done, entering main keep-alive loop')
    _run_fh.flush()

    # ── CRITICAL FIX: disable cyclic garbage collector on the main thread.
    # Python's GC can collect asyncio handles created in the uvicorn daemon
    # thread. When their __del__ runs on the main thread, asyncio detects
    # "wrong thread" and fatally exits at the C level (~20s after startup).
    # With GC disabled, asyncio objects are freed by reference counting in
    # their own thread, which is thread-safe.
    # Kept Windows-only: the crash it works around is the Windows asyncio
    # proactor loop's cross-thread __del__ check. Leaving the collector off on
    # Linux would trade a bug that does not occur here for an unbounded heap in
    # a server that runs for days and holds cyclic asyncio/deque structures.
    if IS_WIN:
        import gc
        gc.disable()
        _run_log.info('Cyclic GC disabled on main thread to prevent asyncio cross-thread __del__')
        _run_fh.flush()

    # Keep main thread alive for the server
    try:
        _server_ready.wait()
        _run_log.info('Server ready, main loop running')
        _run_fh.flush()
        _heartbeat = 0
        while True:
            time.sleep(1)
            _heartbeat += 1
            if _heartbeat % 5 == 0:  # log every 5s for diagnosis
                _run_log.debug(f'heartbeat #{_heartbeat}')
                _run_fh.flush()
    except KeyboardInterrupt:
        _run_log.info('Main thread: KeyboardInterrupt received')
    except SystemExit as se:
        _run_log.critical(f'Main thread: SystemExit code={se.code}')
    except BaseException as ex:
        _run_log.critical(f'Main thread: UNEXPECTED {type(ex).__name__}: {ex}\n{traceback.format_exc()}')
    finally:
        _run_log.critical('Main thread EXITING — this kills all daemon threads (server dies)')
