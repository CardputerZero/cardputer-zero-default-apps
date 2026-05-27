from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from gi.repository import Gdk, Gtk


@dataclass(frozen=True)
class ImeCursor:
    x: int
    y: int
    width: int = 1
    height: int = 12


class InputMethodBridge:
    def __init__(
        self,
        widget: Gtk.Widget,
        text_provider: Callable[[], str],
        cursor_provider: Callable[[], ImeCursor],
        commit_handler: Callable[[str], None],
        preedit_handler: Callable[[str], None] | None = None,
    ) -> None:
        self.widget = widget
        self.text_provider = text_provider
        self.cursor_provider = cursor_provider
        self.commit_handler = commit_handler
        self.preedit_handler = preedit_handler
        self.preedit = ""
        self.enabled = False
        self.attach_client_target = os.environ.get("CZERO_IME_ATTACH_CLIENT_TARGET", "1") != "0"
        self.context = Gtk.IMMulticontext.new()
        self.context.set_use_preedit(True)
        self._set_client_target()
        if hasattr(widget, "connect") and not hasattr(self.context, "set_client_widget"):
            widget.connect("realize", self._on_widget_realize)
        self.context.connect("commit", self._on_commit)
        self.context.connect("preedit-changed", self._on_preedit_changed)

    def focus_in(self) -> None:
        self.enabled = True
        self._set_client_target()
        self.context.focus_in()
        self.update()

    def focus_out(self) -> None:
        if self.enabled:
            self.context.focus_out()
        self.enabled = False
        self.set_preedit("")

    def reset(self) -> None:
        self.context.reset()
        self.set_preedit("")
        if self.enabled:
            self.update()

    def update(self) -> None:
        if not self.enabled:
            return
        text_value = self.text_provider()
        cursor = len(text_value)
        self.context.set_surrounding(text_value, -1, cursor)
        rect_value = self.cursor_provider()
        rect = Gdk.Rectangle()
        rect.x = rect_value.x
        rect.y = rect_value.y
        rect.width = rect_value.width
        rect.height = rect_value.height
        self.context.set_cursor_location(rect)

    def filter_key_event(self, event: object | None) -> bool:
        if event is None:
            return False
        self.focus_in()
        try:
            return bool(self.context.filter_keypress(event))
        except TypeError:
            return False

    def filter_controller_key(self, controller: Gtk.EventControllerKey) -> bool:
        if hasattr(controller, "get_current_event"):
            return self.filter_key_event(controller.get_current_event())
        return False

    def _set_client_target(self) -> None:
        if not self.attach_client_target:
            return
        if hasattr(self.context, "set_client_widget"):
            self.context.set_client_widget(self.widget)
            return
        if not hasattr(self.context, "set_client_window") or not hasattr(self.widget, "get_window"):
            return
        window = self.widget.get_window()
        if window is not None:
            self.context.set_client_window(window)

    def _on_widget_realize(self, *_args: object) -> None:
        self._set_client_target()

    def set_preedit(self, value: str) -> None:
        if self.preedit == value:
            return
        self.preedit = value
        if self.preedit_handler:
            self.preedit_handler(value)

    def _on_commit(self, _context: Gtk.IMContext, text_value: str) -> None:
        if text_value:
            self.commit_handler(text_value)
        self.set_preedit("")
        self.update()

    def _on_preedit_changed(self, context: Gtk.IMContext) -> None:
        preedit, _attrs, _cursor = context.get_preedit_string()
        self.set_preedit(preedit or "")
