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
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0] if hasattr(sys, 'argv') and sys.argv else __file__)), 'data')
os.makedirs(_LOG_DIR, exist_ok=True)
_run_log = logging.getLogger('hrt_run')
_run_log.setLevel(logging.DEBUG)
_run_fh = logging.FileHandler(os.path.join(_LOG_DIR, 'hrt_main_thread.log'), mode='a', encoding='utf-8')
_run_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
_run_fh.stream.reconfigure(write_through=True)  # auto-flush every write
_run_log.addHandler(_run_fh)

# ── DO NOT redirect stdout/stderr — asyncio writes from non-main
#    threads and a replaced file object causes crashes at ~20s ────

# ── Console ctrl handler — MUST live in __main__ module to avoid GC ──
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


def _open_app_window(url: str, width: int = 200, height: int = 450, wait_splash: bool = True):
    """Open HRT in a compact app-mode window (no address bar, no tabs)."""
    # Wait for splash to fully close before opening Edge
    if wait_splash:
        _splash_done.wait(timeout=25)

    # Nuke cached Edge/Chrome window geometry so our size flags are always respected
    cache_dir = os.path.join(os.environ.get('TEMP', '.'), 'hrt-app-window')
    try:
        import shutil as _sh
        _sh.rmtree(cache_dir, ignore_errors=True)
    except Exception:
        pass

    edge = shutil.which("msedge") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome = shutil.which("chrome") or shutil.which("google-chrome")
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    # Position at bottom-right corner of desktop
    try:
        import ctypes
        user32 = ctypes.windll.user32
        scr_w = user32.GetSystemMetrics(0)
        scr_h = user32.GetSystemMetrics(1)
        x = scr_w - width - 12
        y = scr_h - height - 48  # above taskbar
    except Exception:
        x, y = 1800, 740

    app_flags = [
        f"--app={url}",
        f"--window-size={width},{height}",
        f"--window-position={x},{y}",
        "--disable-extensions",
        f"--user-data-dir={os.path.join(os.environ.get('TEMP', '.'), 'hrt-app-window')}",
    ]

    if os.path.isfile(edge):
        subprocess.Popen([edge] + app_flags)
        return
    if chrome and os.path.isfile(chrome):
        subprocess.Popen([chrome] + app_flags)
        return
    for cp in chrome_paths:
        if os.path.isfile(cp):
            subprocess.Popen([cp] + app_flags)
            return

    import webbrowser
    webbrowser.open(url)


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


if __name__ == "__main__":
    import sys
    import ctypes

    # ── Single-instance enforcement via Windows named mutex ──────────
    _MUTEX_NAME = "Global\\BaxtersAiHotRodTuner_SingleInstance"
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    _last_error = ctypes.windll.kernel32.GetLastError()
    _ERROR_ALREADY_EXISTS = 183

    host = os.getenv("HOTROD_HOST", "127.0.0.1")
    port = int(os.getenv("HOTROD_PORT", "8080"))
    url = f"http://{host}:{port}"

    if _last_error == _ERROR_ALREADY_EXISTS:
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

    # Play startup sound immediately (background thread)
    sound_manager.play_startup_sound(blocking=False)

    # Start server in background
    threading.Thread(target=_run_server, args=(host, port), daemon=True).start()

    # Open floater window once server is ready (background)
    threading.Thread(target=_open_app_window, args=(url,), daemon=True).start()

    print(f"Hot Rod Tuner -> {url}")

    # Splash runs on main thread (tkinter requirement), blocks until done
    show_splash(_server_ready, _splash_done)

    # Hide the console window now that startup is complete
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
