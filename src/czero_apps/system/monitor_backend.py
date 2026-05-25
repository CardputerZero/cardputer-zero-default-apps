from __future__ import annotations

from pathlib import Path

from czero_apps.system import command


def overview_lines() -> list[str]:
    lines: list[str] = []
    try:
        load = Path("/proc/loadavg").read_text().split()[:3]
        lines.append(f"Load: {' '.join(load)}")
    except Exception:
        lines.append("Load: unavailable")

    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            mem[key] = int(value.split()[0])
        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", 0)
        used = total - available
        pct = int(used * 100 / total) if total else 0
        lines.append(f"RAM: {pct}% {used//1024}/{total//1024}M")
    except Exception:
        lines.append("RAM: unavailable")

    df = command.run(["df", "-h", "/"])
    if df.ok:
        parts = df.stdout.splitlines()[-1].split()
        if len(parts) >= 5:
            lines.append(f"Disk: {parts[4]} {parts[2]}/{parts[1]}")

    temp = temperature()
    lines.append(f"Temp: {temp}")

    ip = command.run(["sh", "-lc", "ip -4 addr show scope global | awk '/inet / {print $2; exit}'"])
    lines.append(f"IP: {ip.stdout.strip() or 'none'}")

    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
        lines.append(f"Uptime: {int(up//3600)}h {int((up%3600)//60)}m")
    except Exception:
        pass
    return lines


def temperature() -> str:
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            value = int(path.read_text().strip()) / 1000
            return f"{value:.1f}C"
        except Exception:
            continue
    if command.available("vcgencmd"):
        result = command.run(["vcgencmd", "measure_temp"])
        return result.stdout.strip() or "unavailable"
    return "unavailable"


def processes_lines() -> list[str]:
    result = command.run(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"], timeout=5)
    return result.stdout.splitlines()[:8] if result.ok else [result.stderr or "ps failed"]


def services_lines() -> list[str]:
    names = ["NetworkManager", "pipewire", "bluetooth", "ssh", "systemd-logind", "dbus"]
    lines = []
    for name in names:
        result = command.run(["systemctl", "is-active", name], timeout=3)
        lines.append(f"{name}: {result.stdout.strip() or result.stderr.strip()}")
    return lines
