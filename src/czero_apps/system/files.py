from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from czero_apps.system import command


def default_locations() -> list[Path]:
    home = Path.home()
    names = ["Downloads", "Music", "Pictures", "Documents"]
    locations = [home]
    locations.extend(home / name for name in names)
    locations.extend(path for path in (Path("/media"), Path("/mnt")) if path.exists())
    return locations


def list_dir(path: Path) -> list[Path]:
    try:
        return sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []


def describe(path: Path) -> str:
    if path.is_dir():
        return "DIR"
    kind, _ = mimetypes.guess_type(path.name)
    if kind:
        return kind.split("/", 1)[-1].upper()[:8]
    try:
        return f"{path.stat().st_size}B"
    except OSError:
        return "FILE"


def open_path(path: Path):
    if command.available("gio"):
        return command.spawn(["gio", "open", str(path)])
    if command.available("xdg-open"):
        return command.spawn(["xdg-open", str(path)])
    return command.CommandResult(["gio", "open", str(path)], 127, "", "gio/xdg-open not installed")


def trash_path(path: Path):
    if command.available("gio"):
        return command.run(["gio", "trash", str(path)])
    return command.CommandResult(["gio", "trash", str(path)], 127, "", "gio not installed")
