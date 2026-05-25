from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from czero_apps.system import command, desktop


INDEX_PATH = Path("/var/lib/cardputer-zero/app-store/index.json")


@dataclass
class StoreApp:
    id: str
    name: str
    package: str
    summary: str = ""
    category: str = ""


def installed_entries() -> list[desktop.DesktopEntry]:
    return desktop.scan_app_entries()


def load_index(path: Path = INDEX_PATH) -> list[StoreApp]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    apps = []
    for item in data.get("apps", []):
        apps.append(
            StoreApp(
                id=item.get("id", ""),
                name=item.get("name", item.get("id", "")),
                package=item.get("package", ""),
                summary=item.get("summary", ""),
                category=item.get("category", ""),
            )
        )
    return apps


def package_installed(package: str) -> bool:
    if not package:
        return False
    result = command.run(["dpkg-query", "-W", "-f=${Status}", package], timeout=5)
    return result.ok and "install ok installed" in result.stdout


def apt_install(package: str):
    return command.spawn(["pkexec", "apt-get", "install", "-y", package])


def apt_remove(package: str):
    return command.spawn(["pkexec", "apt-get", "remove", "-y", package])


def apt_update():
    return command.spawn(["pkexec", "apt-get", "update"])
