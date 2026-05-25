from __future__ import annotations

from czero_apps.ui.gtk import Gtk


def message_box(title: str, body: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.add_css_class("zero-dialog")
    title_label = Gtk.Label(label=title.upper(), xalign=0)
    title_label.add_css_class("zero-title")
    body_label = Gtk.Label(label=body, xalign=0)
    body_label.set_wrap(True)
    box.append(title_label)
    box.append(body_label)
    return box
