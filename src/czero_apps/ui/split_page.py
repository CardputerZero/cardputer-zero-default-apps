from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from czero_apps.ui.gtk import Gdk, Gtk


@dataclass
class SplitItem:
    title: str
    lines: list[str]
    action: Callable[[], None] | None = None


class SplitPage(Gtk.Box):
    def __init__(self, items: list[SplitItem]) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.add_css_class("zero-split-page")
        self.items = items
        self.rows: list[Gtk.Label] = []
        self.selected = 0

        self.rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.rail.add_css_class("zero-rail")
        self.rail.set_size_request(98, -1)
        self.append(self.rail)

        for item in items:
            row = Gtk.Label(label=item.title.upper(), xalign=0)
            row.add_css_class("zero-rail-row")
            self.rail.append(row)
            self.rows.append(row)

        self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.preview.add_css_class("zero-preview")
        self.preview.set_hexpand(True)
        self.append(self.preview)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        self.set_focusable(True)
        self._sync()

    def focus_first(self) -> None:
        self.grab_focus()

    def activate(self) -> None:
        if not self.items:
            return
        action = self.items[self.selected].action
        if action:
            action()

    def move(self, delta: int) -> None:
        if not self.items:
            return
        self.selected = max(0, min(len(self.items) - 1, self.selected + delta))
        self._sync()

    def _sync(self) -> None:
        for index, row in enumerate(self.rows):
            if index == self.selected:
                row.add_css_class("zero-rail-row-active")
            else:
                row.remove_css_class("zero-rail-row-active")

        child = self.preview.get_first_child()
        while child is not None:
            self.preview.remove(child)
            child = self.preview.get_first_child()

        if not self.items:
            return

        item = self.items[self.selected]
        title = Gtk.Label(label=item.title.upper(), xalign=0)
        title.add_css_class("zero-preview-title")
        self.preview.append(title)

        for line in item.lines[:5]:
            label = Gtk.Label(label=line, xalign=0)
            label.add_css_class("zero-preview-line")
            label.set_wrap(True)
            self.preview.append(label)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab, Gdk.KEY_Right):
            self.move(1)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Left):
            self.move(-1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate()
            return True
        return False
