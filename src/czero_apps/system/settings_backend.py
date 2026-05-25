from __future__ import annotations

import json
import os
import platform
import socket
from pathlib import Path

from czero_apps import __version__
from czero_apps.system import command


def about_lines() -> list[str]:
    os_name = "Unknown OS"
    os_release = Path("/etc/os-release")
    if os_release.exists():
        data = {}
        for line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                data[key] = value.strip('"')
        os_name = data.get("PRETTY_NAME", os_name)

    uptime = "unknown"
    try:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
        uptime = f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
    except Exception:
        pass

    ip_result = command.run(["sh", "-lc", "ip -4 addr show scope global | awk '/inet / {print $2; exit}'"])
    ip = ip_result.stdout.strip() or "none"

    return [
        f"Device: Cardputer Zero",
        f"OS: {os_name}",
        f"Kernel: {platform.release()}",
        f"Arch: {platform.machine()}",
        f"Host: {socket.gethostname()}",
        f"Session: {os.environ.get('XDG_SESSION_TYPE', 'unknown')}",
        f"Default apps: {__version__}",
        f"IP: {ip}",
        f"Uptime: {uptime}",
    ]


def command_status(name: str) -> str:
    return "available" if command.available(name) else "not installed"


def user_preferences_path() -> Path:
    return Path.home() / ".config" / "cardputer-zero" / "default-apps" / "settings.json"


def load_preferences() -> dict:
    path = user_preferences_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_preferences(data: dict) -> None:
    path = user_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
