#!/usr/bin/env python3
"""Compact chrome-less window hosting the Hot Rod Tuner UI.

WHY THIS EXISTS
---------------
HRT is designed as a small always-there floater — the Windows build gets that by
launching Edge/Chrome with `--app=<url>`, which yields a window with no tab bar,
no address bar and no menu. On Linux that trick needs a Chromium-family browser,
and this machine has only Firefox, which removed site-specific-browser support
years ago. Opening the UI in Firefox therefore drags in the full browser chrome,
and *that* chrome — not HRT's own layout — sets the window's minimum width and
height. The page itself is a 100vh flex column and shrinks to anything.

WebKitGTK is already present (it arrived as a Tauri dependency), so hosting the
page in a bare WebView costs no new packages and no root.

GTK 3 rather than GTK 4 is deliberate: WebKit2-4.1 pairs with GTK 3, and GTK 4's
Vulkan renderer is unstable on this box's NVIDIA 595 driver.

The window keeps its decorations by default. An undecorated window on
GTK/Wayland gets no border, no resize grip and no close button from the
compositor, which turns a too-small or too-large window into a trap the operator
cannot escape; `--undecorated` is available for anyone who wants it anyway.

Usage:
    hrt_floater.py [URL] [--width N] [--height M] [--undecorated] [--quit-on-close]
"""
from __future__ import annotations

import argparse
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2, Gdk  # noqa: E402

# Must match the .desktop basename and its StartupWMClass, or the shell shows a
# generic icon because it cannot pair the window with the launcher.
APP_ID = "baxters-hot-rod-tuner"


def build_window(url: str, width: int, height: int,
                 undecorated: bool, quit_on_close: bool) -> Gtk.Window:
    # Dark titlebar.
    #
    # This is a GTK 3 window with client-side decorations, so GTK draws the
    # titlebar itself using the app's own theme — the session's gtk-theme is
    # already 'Yaru', and Yaru's LIGHT headerbar is near-white. That is the
    # white titlebar; nothing was overriding the theme, the light variant was
    # simply being used as intended.
    #
    # Asking for the dark variant here rather than changing a session setting
    # is why this sticks: it is a property of this window, set at construction,
    # and it does not depend on the desktop's colour-scheme or on which shell
    # launched the app. HRT's page is dark (#1e1e1e); a white bar above it was
    # the only light element on screen.
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    # Identity: WM_CLASS and icon.
    #
    # Without this the window's WM_CLASS comes from the script name, so the
    # shell cannot match it to baxters-hot-rod-tuner.desktop and falls back to a
    # generic icon in the dock and switcher. set_prgname must run before the
    # first window is realised, and the .desktop file carries a matching
    # StartupWMClass so the pairing works from both ends.
    GLib.set_prgname(APP_ID)
    Gtk.Window.set_default_icon_name(APP_ID)
    _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "HRT_ICON.png")
    if os.path.exists(_icon):
        # Belt and braces: the themed name covers a proper install, the file
        # covers running straight from the source tree with nothing installed.
        try:
            Gtk.Window.set_default_icon_from_file(_icon)
        except Exception:
            pass

    win = Gtk.Window(title="Hot Rod Tuner")
    win.set_default_size(width, height)
    # Let the operator shrink it to essentially nothing; the page is designed to
    # cope and the point of this window is to be small.
    win.set_size_request(120, 120)
    if undecorated:
        win.set_decorated(False)
    win.set_keep_above(True)          # a monitoring floater belongs on top

    view = WebKit2.WebView()
    settings = view.get_settings()
    settings.set_enable_developer_extras(True)
    # No right-click "Reload"/"Back" chrome and no text selection dragging the
    # layout around — this is an appliance window, not a browser tab.
    settings.set_enable_back_forward_navigation_gestures(False)
    view.load_uri(url)
    win.add(view)

    def on_destroy(*_):
        if quit_on_close:
            Gtk.main_quit()
        else:
            Gtk.main_quit()
    win.connect("destroy", on_destroy)

    # Ctrl+R reload, Ctrl+Q quit — the only two browser affordances worth keeping.
    def on_key(_w, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if not ctrl:
            return False
        key = Gdk.keyval_name(event.keyval) or ""
        if key.lower() == "r":
            view.reload()
            return True
        if key.lower() == "q":
            win.destroy()
            return True
        return False
    win.connect("key-press-event", on_key)

    return win


def main() -> int:
    ap = argparse.ArgumentParser(description="Hot Rod Tuner floating window")
    ap.add_argument("url", nargs="?",
                    default=os.environ.get("HOTROD_URL")
                    or f"http://127.0.0.1:{os.environ.get('HOTROD_PORT', '8090')}")
    ap.add_argument("--width", type=int, default=200)
    ap.add_argument("--height", type=int, default=450)
    ap.add_argument("--undecorated", action="store_true")
    ap.add_argument("--quit-on-close", action="store_true",
                    help="exit with status 0 when the window closes "
                         "(run_server watches this to shut the server down)")
    args = ap.parse_args()

    win = build_window(args.url, args.width, args.height,
                       args.undecorated, args.quit_on_close)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
