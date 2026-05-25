from __future__ import annotations

import time
from collections.abc import Callable

from czero_apps.ui.gtk import Gdk, GLib, Gtk
from czero_apps.ui.theme import load_css


class ZeroAppWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, title: str, subtitle: str = "") -> None:
        super().__init__(application=app, title=title)
        load_css()
        self.set_default_size(320, 170)
        self.set_size_request(320, 170)
        self.set_resizable(False)
        self.set_decorated(False)

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root.add_css_class("zero-root")
        self.set_child(self.root)

        self.topbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.topbar.add_css_class("zero-topbar")
        self.root.append(self.topbar)

        self.title_label = Gtk.Label(label=title.upper(), xalign=0)
        self.title_label.add_css_class("zero-title")
        self.title_label.set_hexpand(True)
        self.topbar.append(self.title_label)

        self.status_label = Gtk.Label(label=subtitle.upper(), xalign=1)
        self.status_label.add_css_class("zero-status")
        self.topbar.append(self.status_label)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.content.add_css_class("zero-content")
        self.content.set_vexpand(True)
        self.root.append(self.content)

        self.bottombar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.bottombar.add_css_class("zero-bottombar")
        self.root.append(self.bottombar)

        self.hint_label = Gtk.Label(label="ENTER SELECT   ESC BACK", xalign=0)
        self.hint_label.add_css_class("zero-status")
        self.hint_label.set_hexpand(True)
        self.bottombar.append(self.hint_label)

        self.error_label = Gtk.Label(label="", xalign=1)
        self.error_label.add_css_class("zero-warn")
        self.bottombar.append(self.error_label)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

        GLib.timeout_add_seconds(5, self._tick_time)
        self._tick_time()

    def set_content(self, widget: Gtk.Widget) -> None:
        child = self.content.get_first_child()
        while child is not None:
            self.content.remove(child)
            child = self.content.get_first_child()
        self.content.append(widget)

    def set_hint(self, text: str) -> None:
        self.hint_label.set_text(text.upper())

    def set_error(self, text: str) -> None:
        self.error_label.set_text(text.upper())

    def show_error(self, text: str, timeout_ms: int = 4000) -> None:
        self.set_error(text)
        if timeout_ms:
            GLib.timeout_add(timeout_ms, self._clear_error)

    def _clear_error(self) -> bool:
        self.set_error("")
        return False

    def _tick_time(self) -> bool:
        if not self.status_label.get_text() or ":" in self.status_label.get_text():
            self.status_label.set_text(time.strftime("%H:%M"))
        return True

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_BackSpace):
            if self.on_back():
                return True
        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            self.close()
            return True
        return False

    def on_back(self) -> bool:
        self.close()
        return True


class ZeroApplication(Gtk.Application):
    def __init__(self, app_id: str, title: str, build: Callable[[ZeroAppWindow], None]) -> None:
        super().__init__(application_id=app_id)
        self.title = title
        self.build = build

    def do_activate(self) -> None:
        window = ZeroAppWindow(self, self.title)
        self.build(window)
        window.present()
