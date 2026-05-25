from __future__ import annotations

from czero_apps.apps.files.view import FilesCanvas
from czero_apps.ui.gtk import GLib, Gtk
from czero_apps.ui.theme import load_css


class FilesWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Files")
        load_css()
        self.set_default_size(320, 170)
        self.set_size_request(320, 170)
        self.set_resizable(False)
        self.set_decorated(False)
        self.canvas = FilesCanvas()
        self.set_child(self.canvas)


class FilesApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="dev.cardputerzero.defaultapps.files")

    def do_activate(self) -> None:
        window = FilesWindow(self)
        window.present()
        GLib.idle_add(window.canvas.grab_focus)


def run(argv: list[str] | None = None) -> int:
    app = FilesApplication()
    return app.run(argv or [])
