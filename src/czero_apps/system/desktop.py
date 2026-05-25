from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path("/usr/share/APPLaunch/applications")


@dataclass
class DesktopEntry:
    path: Path
    name: str
    exec: str
    icon: str = ""
    package: str = ""
    app_id: str = ""


def scan_app_entries(app_dir: Path = APP_DIR) -> list[DesktopEntry]:
    entries: list[DesktopEntry] = []
    if not app_dir.exists():
        return entries
    for path in sorted(app_dir.glob("*.desktop")):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        try:
            parser.read(path, encoding="utf-8")
            section = parser["Desktop Entry"]
        except Exception:
            continue
        name = section.get("Name", path.stem)
        exec_value = section.get("Exec", "")
        entries.append(
            DesktopEntry(
                path=path,
                name=name,
                exec=exec_value,
                icon=section.get("Icon", ""),
                package=section.get("X-Zero-Package", ""),
                app_id=section.get("X-Zero-AppId", ""),
            )
        )
    return entries
