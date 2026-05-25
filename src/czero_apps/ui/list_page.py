from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from czero_apps.ui.gtk import Gdk, Gtk


@dataclass
class ListItem:
    title: str
    subtitle: str = ""
    action: Callable[[], None] | None = None


class ListPage(Gtk.ScrolledWindow):
    def __init__(self, items: list[ListItem]) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.items = items
        self.rows: list[Gtk.Box] = []
        self.selected = 0

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_child(self.list_box)

        for item in items:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            row.add_css_class("zero-row")
            title = Gtk.Label(label=item.title, xalign=0)
            title.add_css_class("zero-row-title")
            row.append(title)
            if item.subtitle:
                subtitle = Gtk.Label(label=item.subtitle, xalign=0)
                subtitle.add_css_class("zero-row-subtitle")
                row.append(subtitle)
            self.list_box.append(row)
            self.rows.append(row)

        self._sync_selection()
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        self.set_focusable(True)

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
        self._sync_selection()

    def _sync_selection(self) -> None:
        for index, row in enumerate(self.rows):
            if index == self.selected:
                row.add_css_class("zero-row-active")
            else:
                row.remove_css_class("zero-row-active")

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self.move(1)
            return True
        if keyval == Gdk.KEY_Up:
            self.move(-1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate()
            return True
        return False
