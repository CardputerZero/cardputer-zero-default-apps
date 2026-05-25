from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from czero_apps.ui.gtk import Gdk, Gtk


@dataclass
class Tile:
    title: str
    value: str
    subtitle: str = ""
    percent: int | None = None
    action: Callable[[], None] | None = None
    danger: bool = False


class DashboardPage(Gtk.Box):
    def __init__(self, tiles: list[Tile], columns: int = 2) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.tiles = tiles
        self.columns = max(1, columns)
        self.cards: list[Gtk.Box] = []
        self.selected = 0

        rows: list[Gtk.Box] = []
        for index, tile in enumerate(tiles):
            if index % self.columns == 0:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                self.append(row)
                rows.append(row)
            card = self._build_card(tile)
            rows[-1].append(card)
            self.cards.append(card)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)
        self.set_focusable(True)
        self._sync_selection()

    def _build_card(self, tile: Tile) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        card.add_css_class("zero-card")
        if tile.danger:
            card.add_css_class("zero-card-danger")
        card.set_hexpand(True)

        title = Gtk.Label(label=tile.title.upper(), xalign=0)
        title.add_css_class("zero-card-title")
        card.append(title)

        value = Gtk.Label(label=tile.value, xalign=0)
        value.add_css_class("zero-hero-value")
        card.append(value)

        if tile.percent is not None:
            meter = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            meter.add_css_class("zero-meter")
            fill = Gtk.Box()
            fill.add_css_class("zero-meter-fill")
            fill.set_size_request(max(2, min(100, tile.percent)), 6)
            meter.append(fill)
            card.append(meter)
        elif tile.subtitle:
            subtitle = Gtk.Label(label=tile.subtitle, xalign=0)
            subtitle.add_css_class("zero-card-subtitle")
            card.append(subtitle)
        return card

    def focus_first(self) -> None:
        self.grab_focus()

    def activate(self) -> None:
        if not self.tiles:
            return
        action = self.tiles[self.selected].action
        if action:
            action()

    def move(self, delta: int) -> None:
        if not self.tiles:
            return
        self.selected = max(0, min(len(self.tiles) - 1, self.selected + delta))
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
