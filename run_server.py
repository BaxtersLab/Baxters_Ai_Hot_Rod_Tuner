import uvicorn
import os
import subprocess
import threading
import shutil
import time
from threading import Event
from hotrod_tuner.sound import sound_manager
from hotrod_tuner.splash import show_splash

_server_ready = Event()
_splash_done = Event()


def _open_app_window(url: str, width: int = 200, height: int = 400):
    """Open HRT in a compact app-mode window (no address bar, no tabs)."""
    # Wait for splash to fully close before opening Edge
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


if __name__ == "__main__":
    print("Starting Hot Rod Tuner...")

    # Play startup sound immediately (background thread)
    sound_manager.play_startup_sound(blocking=False)

    host = os.getenv("HOTROD_HOST", "127.0.0.1")
    port = int(os.getenv("HOTROD_PORT", "8080"))
    url = f"http://{host}:{port}"

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

    # Keep main thread alive for the server
    try:
        _server_ready.wait()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
