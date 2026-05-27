from __future__ import annotations

import os

import gi

if os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("GDK_BACKEND", "wayland")
os.environ.setdefault("GSK_RENDERER", "cairo")
os.environ.setdefault("GDK_GL", "disable")
os.environ.setdefault("GTK_A11Y", "none")

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

__all__ = ["Gdk", "GLib", "Gtk", "Pango", "PangoCairo"]
