from __future__ import annotations

from dataclasses import dataclass

from czero_apps.ui.gtk import Gtk


@dataclass
class Page:
    title: str
    widget: Gtk.Widget
    hint: str = "ENTER SELECT   ESC BACK"


class PageStack:
    def __init__(self, window) -> None:
        self.window = window
        self.pages: list[Page] = []

    def push(self, page: Page) -> None:
        self.pages.append(page)
        self._show(page)

    def pop(self) -> bool:
        if len(self.pages) <= 1:
            return False
        self.pages.pop()
        self._show(self.pages[-1])
        return True

    def replace(self, page: Page) -> None:
        self.pages = [page]
        self._show(page)

    def _show(self, page: Page) -> None:
        self.window.title_label.set_text(page.title.upper())
        self.window.set_hint(page.hint)
        self.window.set_content(page.widget)
        if hasattr(page.widget, "focus_first"):
            page.widget.focus_first()
