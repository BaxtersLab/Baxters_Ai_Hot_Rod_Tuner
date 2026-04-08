"""Splash screen for Hot Rod Tuner — displays banner while server boots."""
import sys
import time
import tkinter as tk
from pathlib import Path
from threading import Event


def _get_assets_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent.parent.parent / "assets"


def show_splash(ready_event: Event, done_event: Event = None, banner_name: str = "Hot rod tuner banner.png"):
    """Show a centered borderless splash with the banner and a progress bar.
    Closes automatically 5s after `ready_event` is set.
    If `done_event` is provided, sets it when splash closes."""
    assets = _get_assets_dir()
    banner_path = assets / banner_name

    root = tk.Tk()
    root.withdraw()  # hide until positioned
    root.overrideredirect(True)  # borderless
    root.attributes("-topmost", True)
    root.configure(bg="#111")

    # Load banner image
    try:
        img = tk.PhotoImage(file=str(banner_path))
        # Scale down if wider than 520px (keep aspect ratio using subsample)
        w, h = img.width(), img.height()
        max_w = 520
        if w > max_w:
            factor = max(1, round(w / max_w))
            img = img.subsample(factor, factor)
            w, h = img.width(), img.height()
    except Exception:
        # Fallback: just a text label
        img = None
        w, h = 400, 100

    # Banner label
    if img:
        banner_lbl = tk.Label(root, image=img, bg="#111", bd=0)
        banner_lbl.image = img  # prevent GC
        banner_lbl.pack(padx=0, pady=(6, 0))
    else:
        banner_lbl = tk.Label(root, text="Ai Hot Rod Tuner", font=("Segoe UI", 18, "bold"),
                              fg="#f97316", bg="#111")
        banner_lbl.pack(padx=20, pady=(12, 0))

    # Progress area
    prog_frame = tk.Frame(root, bg="#111")
    prog_frame.pack(fill="x", padx=12, pady=(8, 10))

    status_lbl = tk.Label(prog_frame, text="Starting server...", font=("Segoe UI", 9),
                          fg="#888", bg="#111", anchor="w")
    status_lbl.pack(fill="x")

    # Progress bar (canvas)
    bar_h = 4
    bar_canvas = tk.Canvas(prog_frame, height=bar_h, bg="#2a2a2a", highlightthickness=0)
    bar_canvas.pack(fill="x", pady=(3, 0))
    bar_fill = bar_canvas.create_rectangle(0, 0, 0, bar_h, fill="#f97316", outline="")

    # Center on screen
    root.update_idletasks()
    win_w = root.winfo_reqwidth()
    win_h = root.winfo_reqheight()
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    x = (scr_w - win_w) // 2
    y = (scr_h - win_h) // 2
    root.geometry(f"+{x}+{y}")
    root.deiconify()

    # Animate progress bar and check ready_event
    progress = [0.0]
    ready_at = [None]

    def tick():
        # Once server is ready, track when it became ready
        if ready_event.is_set():
            if ready_at[0] is None:
                ready_at[0] = time.time()
                status_lbl.config(text="Ready!", fg="#22c55e")
                bar_w = bar_canvas.winfo_width()
                bar_canvas.coords(bar_fill, 0, 0, bar_w, bar_h)

            # Stay visible for 5 full seconds after "Ready!"
            if time.time() - ready_at[0] >= 5.0:
                root.destroy()
                return

            root.after(100, tick)
            return

        # Ease progress toward 90% while waiting
        progress[0] = min(progress[0] + (90 - progress[0]) * 0.08, 90)
        bar_w = bar_canvas.winfo_width()
        fill_w = bar_w * progress[0] / 100
        bar_canvas.coords(bar_fill, 0, 0, fill_w, bar_h)

        # Update status text based on progress
        if progress[0] < 20:
            status_lbl.config(text="Starting server...")
        elif progress[0] < 50:
            status_lbl.config(text="Loading sensors...")
        elif progress[0] < 80:
            status_lbl.config(text="Initializing dashboard...")
        else:
            status_lbl.config(text="Almost ready...")

        root.after(80, tick)

    root.after(100, tick)
    root.mainloop()
    # Signal that splash is closed so the floater can open
    if done_event:
        done_event.set()
