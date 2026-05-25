from __future__ import annotations

from czero_apps.system import appstore_backend
from czero_apps.ui.app_window import ZeroApplication
from czero_apps.ui.card_page import CardGridPage, CardItem
from czero_apps.ui.detail_page import DetailPage
from czero_apps.ui.page_stack import Page, PageStack
from czero_apps.ui.split_page import SplitItem, SplitPage


def build(window) -> None:
    stack = PageStack(window)
    window.on_back = stack.pop

    def show_lines(title: str, lines: list[str]) -> None:
        stack.push(Page(title, DetailPage(lines), "ESC BACK"))

    def installed() -> None:
        entries = appstore_backend.installed_entries()
        if not entries:
            show_lines("Installed", ["No APPLaunch apps found"])
            return
        items = [
            CardItem(entry.name, entry.package or entry.exec, "APP", lambda e=entry: show_lines(e.name, [f"Exec: {e.exec}", f"Icon: {e.icon}", f"File: {e.path}"]))
            for entry in entries
        ]
        stack.push(Page("Installed", CardGridPage(items), "ENTER DETAILS   ESC BACK"))

    def indexed() -> None:
        apps = appstore_backend.load_index()
        if not apps:
            show_lines("Sources", ["/var/lib/cardputer-zero/app-store/index.json not found"])
            return
        items = []
        for app in apps:
            state = "installed" if appstore_backend.package_installed(app.package) else "available"
            items.append(CardItem(app.name, f"{state} {app.package}", "PKG", lambda a=app: show_lines(a.name, [a.summary, f"Package: {a.package}", f"Category: {a.category}"])))
        stack.push(Page("Featured", CardGridPage(items), "ENTER DETAILS   ESC BACK"))

    def update() -> None:
        result = appstore_backend.apt_update()
        if result.ok:
            window.show_error("apt update started")
        else:
            window.show_error(result.stderr or "apt failed")

    installed_count = len(appstore_backend.installed_entries())
    indexed_count = len(appstore_backend.load_index())
    items = [
        SplitItem("Featured", [f"{indexed_count} indexed apps", "Remote index catalog", "Enter opens app list"], indexed),
        SplitItem("Installed", [f"{installed_count} APPLaunch apps", "Local desktop entries", "Enter opens details"], installed),
        SplitItem("Updates", ["Refresh package metadata", "Uses pkexec apt-get", "Polkit owns auth"], update),
        SplitItem("Categories", ["Category browser", "Backed by index.json"], indexed),
        SplitItem("Sources", [str(appstore_backend.INDEX_PATH), "Cardputer Zero app index"], lambda: show_lines("Sources", [str(appstore_backend.INDEX_PATH)])),
    ]
    stack.replace(Page("App Store", SplitPage(items), "TAB MOVE   ENTER OPEN   ESC BACK"))


def run(argv: list[str] | None = None) -> int:
    app = ZeroApplication("dev.cardputerzero.defaultapps.store", "App Store", build)
    return app.run(argv or [])
