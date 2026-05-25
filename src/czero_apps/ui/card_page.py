from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from czero_apps.ui.gtk import Gdk, Gtk


@dataclass
class CardItem:
    title: str
    subtitle: str = ""
    badge: str = ""
    action: Callable[[], None] | None = None
    danger: bool = False
    muted: bool = False


class CardGridPage(Gtk.ScrolledWindow):
    def __init__(self, items: list[CardItem], columns: int = 2) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.items = items
        self.columns = max(1, columns)
        self.cards: list[Gtk.Box] = []
        self.selected = 0

        self.grid = Gtk.Grid()
        self.grid.set_column_spacing(5)
        self.grid.set_row_spacing(5)
        self.grid.add_css_class("zero-card-grid")
        self.set_child(self.grid)

        for index, item in enumerate(items):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.add_css_class("zero-card")
            if item.danger:
                card.add_css_class("zero-card-danger")
            if item.muted:
                card.add_css_class("zero-card-muted")
            card.set_hexpand(True)
            card.set_vexpand(False)

            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            title = Gtk.Label(label=item.title.upper(), xalign=0)
            title.add_css_class("zero-card-title")
            title.set_hexpand(True)
            top.append(title)
            if item.badge:
                badge = Gtk.Label(label=item.badge.upper(), xalign=1)
                badge.add_css_class("zero-badge")
                top.append(badge)
            card.append(top)

            if item.subtitle:
                subtitle = Gtk.Label(label=item.subtitle, xalign=0)
                subtitle.add_css_class("zero-card-subtitle")
                subtitle.set_wrap(True)
                card.append(subtitle)

            self.grid.attach(card, index % self.columns, index // self.columns, 1, 1)
            self.cards.append(card)

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
        for index, card in enumerate(self.cards):
            if index == self.selected:
                card.add_css_class("zero-card-active")
            else:
                card.remove_css_class("zero-card-active")

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Tab):
            self.move(1)
            return True
        if keyval == Gdk.KEY_Left:
            self.move(-1)
            return True
        if keyval == Gdk.KEY_Down:
            self.move(self.columns)
            return True
        if keyval == Gdk.KEY_Up:
            self.move(-self.columns)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate()
            return True
        return False
