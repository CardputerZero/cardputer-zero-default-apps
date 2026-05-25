from __future__ import annotations

from czero_apps.ui.gtk import Gtk, Pango


class DetailPage(Gtk.ScrolledWindow):
    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("zero-content")
        self.set_child(box)
        for line in lines:
            label = Gtk.Label(label=line, xalign=0)
            label.set_wrap(True)
            label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            box.append(label)
